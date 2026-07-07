"""Best-effort live status for eCarUp stations via eCarUp's own public map API.

The SFOE ich-tanke-strom OICP status feed reports ``Unknown`` for a large share
of eCarUp charging points (``CH*ECU...``) even though eCarUp itself knows the
live state. eCarUp runs a public map (https://www.ecarup.com/map) backed by two
key-less JSON endpoints:

* ``POST /api/map/stations`` - stations (guid, name, lat/lon) in a bounding box
* ``GET  /api/stations?id=`` - station detail incl. per-connector live ``State``

This module fills the gaps by matching each still-unresolved eCarUp EVSE to an
eCarUp station and reading the connector state:

1. authoritatively, when a connector exposes ``Hubject.ID`` equal to the OICP
   ``EvseID`` (only a minority of stations expose it publicly); otherwise
2. by nearest station coordinate, using the state only when that station's
   connectors unanimously agree - so an ambiguous multi-connector site stays
   ``unknown`` instead of showing a guessed state.

Everything here is best-effort: any network or parsing failure yields an empty
result, leaving the affected stations ``unknown`` exactly as before.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt
import logging

from aiohttp import ClientError, ClientSession, ClientTimeout

from .api import normalize_evse_id
from .const import (
    STATE_AVAILABLE,
    STATE_MAINTENANCE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_RESERVED,
    STATE_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)

# Public, key-less eCarUp map backend (same calls the web map at
# https://www.ecarup.com/map makes).
ECARUP_MAP_URL = "https://www.ecarup.com/api/map/stations"
ECARUP_STATION_URL = "https://www.ecarup.com/api/stations"

# eCarUp EVSEs carry the operator id ``CH*ECU`` in the SFOE feed.
_ECARUP_KEY_PREFIX = "CHECU"

# Ask for individual stations, not clusters: the backend only clusters at low
# zoom levels, so a high zoom returns every station in the bounding box.
_MAP_ZOOM = 18
# Bounding-box padding around the tracked coordinates, in degrees (~0.4 km); wide
# enough to catch a station whose eCarUp coordinate differs slightly from SFOE.
_BBOX_PAD_DEG = 0.004

# A station this close to the tracked coordinate is treated as the same site.
_MATCH_RADIUS_M = 30.0
# Fetch station details for candidates within this distance of any target.
_DETAIL_RADIUS_M = 70.0
# Hard cap on detail requests per refresh, so a dense area cannot fan out.
_DETAIL_FETCH_CAP = 30

_TIMEOUT = ClientTimeout(total=30)

# eCarUp connector ``State`` enum (from the public map's own rendering) mapped to
# this integration's normalised availability states.
_CONNECTOR_STATE_MAP: dict[int, str] = {
    0: STATE_OUT_OF_SERVICE,  # Not active / Offline
    1: STATE_AVAILABLE,  # Free
    2: STATE_OCCUPIED,  # Occupied
    3: STATE_MAINTENANCE,  # Maintenance
    4: STATE_RESERVED,  # Reserved
    5: STATE_UNKNOWN,  # Unknown
    6: STATE_OCCUPIED,  # Car connected
}


@dataclass(slots=True)
class _Connector:
    """A single eCarUp connector: its live state and optional roaming id."""

    state: str
    hubject_id: str | None


@dataclass(slots=True)
class _Station:
    """An eCarUp map station; ``connectors`` is filled once details are fetched."""

    station_id: str
    latitude: float
    longitude: float
    connectors: list[_Connector] = field(default_factory=list)


def is_ecarup_evse_id(evse_id: str) -> bool:
    """Return True if ``evse_id`` belongs to the eCarUp operator (``CH*ECU``)."""
    return normalize_evse_id(evse_id).startswith(_ECARUP_KEY_PREFIX)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    r = 6_371_000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * r * asin(sqrt(a))


def match_state(
    evse_id: str, lat: float, lon: float, stations: list[_Station]
) -> str | None:
    """Resolve one EVSE to a state from populated eCarUp stations, or ``None``.

    Precedence: an exact ``Hubject.ID`` match wins (authoritative, per-connector);
    otherwise the single nearest station within :data:`_MATCH_RADIUS_M` is used,
    but only when its connectors unanimously report the same state. A conflicting
    multi-connector site returns ``None`` rather than guessing.
    """
    target_key = normalize_evse_id(evse_id)

    # 1) Authoritative: a connector whose roaming id equals this EvseID.
    for station in stations:
        for connector in station.connectors:
            if (
                connector.hubject_id
                and normalize_evse_id(connector.hubject_id) == target_key
            ):
                return connector.state

    # 2) Nearest station within the match radius, if its connectors agree.
    nearest: _Station | None = None
    best = _MATCH_RADIUS_M
    for station in stations:
        dist = _distance_m(lat, lon, station.latitude, station.longitude)
        if dist <= best:
            best = dist
            nearest = station

    if nearest is not None and nearest.connectors:
        # An ``unknown`` connector neither resolves nor blocks the site; only the
        # concrete states must agree.
        states = {c.state for c in nearest.connectors if c.state != STATE_UNKNOWN}
        if len(states) == 1:
            return next(iter(states))

    return None


async def async_resolve_ecarup_states(
    session: ClientSession, targets: list[tuple[str, float, float]]
) -> dict[str, str]:
    """Resolve live states for eCarUp EVSEs the SFOE feed left ``unknown``.

    ``targets`` is a list of ``(evse_id, latitude, longitude)`` for eCarUp EVSEs
    with known coordinates. Returns ``{evse_id: state}`` for those confidently
    resolved to a concrete (non-``unknown``) state; unresolved ids are omitted.
    Never raises: any failure yields ``{}``.
    """
    points = [(e, la, lo) for e, la, lo in targets if la is not None and lo is not None]
    if not points:
        return {}

    try:
        stations = await _async_fetch_map(session, points)
    except (ClientError, ValueError, TimeoutError) as err:
        _LOGGER.debug("eCarUp map query failed: %s", err)
        return {}

    # Only fetch details for stations near at least one target, capped.
    candidates = [
        station
        for station in stations
        if any(
            _distance_m(la, lo, station.latitude, station.longitude) <= _DETAIL_RADIUS_M
            for _, la, lo in points
        )
    ]
    candidates = candidates[:_DETAIL_FETCH_CAP]

    details = await asyncio.gather(
        *(_async_fetch_detail(session, station.station_id) for station in candidates),
        return_exceptions=True,
    )
    populated: list[_Station] = []
    for station, connectors in zip(candidates, details):
        if isinstance(connectors, BaseException) or not connectors:
            continue
        station.connectors = connectors
        populated.append(station)

    resolved: dict[str, str] = {}
    for evse_id, lat, lon in points:
        state = match_state(evse_id, lat, lon, populated)
        if state is not None and state != STATE_UNKNOWN:
            resolved[evse_id] = state
    return resolved


async def _async_fetch_map(
    session: ClientSession, points: list[tuple[str, float, float]]
) -> list[_Station]:
    """POST the bounding box of all targets and parse the returned stations."""
    lats = [la for _, la, _ in points]
    lons = [lo for _, _, lo in points]
    # aiohttp only accepts str/int query values across versions, so stringify.
    params = {
        "northEastLatitude": repr(max(lats) + _BBOX_PAD_DEG),
        "northEastLongitude": repr(max(lons) + _BBOX_PAD_DEG),
        "southWestLatitude": repr(min(lats) - _BBOX_PAD_DEG),
        "southWestLongitude": repr(min(lons) - _BBOX_PAD_DEG),
        "zoomLevel": str(_MAP_ZOOM),
    }
    body = {"ShowPlugTypeType2": True, "ShowPlugTypeCcs": True, "CustomTextFilter": ""}
    async with session.post(
        ECARUP_MAP_URL, params=params, json=body, timeout=_TIMEOUT
    ) as response:
        response.raise_for_status()
        payload = await response.json(content_type=None)
    return _parse_map(payload)


async def _async_fetch_detail(
    session: ClientSession, station_id: str
) -> list[_Connector] | None:
    """GET one station's detail and parse its connectors, or ``None`` on error."""
    try:
        async with session.get(
            ECARUP_STATION_URL,
            params={"id": station_id},
            timeout=_TIMEOUT,
        ) as response:
            if response.status == 403:
                return None  # station is not public
            response.raise_for_status()
            payload = await response.json(content_type=None)
    except (ClientError, ValueError, TimeoutError) as err:
        _LOGGER.debug("eCarUp detail query for %s failed: %s", station_id, err)
        return None
    return _parse_connectors(payload)


def _parse_map(payload: object) -> list[_Station]:
    """Parse a ``/api/map/stations`` response into stations with coordinates."""
    stations: list[_Station] = []
    if not isinstance(payload, dict):
        return stations
    for item in payload.get("Stations") or []:
        if not isinstance(item, dict):
            continue
        station_id = item.get("Id")
        lat = _to_float(item.get("Latitude"))
        lon = _to_float(item.get("Longitude"))
        if station_id and lat is not None and lon is not None:
            stations.append(_Station(station_id=station_id, latitude=lat, longitude=lon))
    return stations


def _parse_connectors(payload: object) -> list[_Connector]:
    """Parse a ``/api/stations`` detail response into connectors."""
    connectors: list[_Connector] = []
    if not isinstance(payload, dict):
        return connectors
    for item in payload.get("Connectors") or []:
        if not isinstance(item, dict):
            continue
        state = _CONNECTOR_STATE_MAP.get(item.get("State"))
        if state is None:
            continue
        hubject = item.get("Hubject")
        hubject_id = hubject.get("ID") if isinstance(hubject, dict) else None
        connectors.append(
            _Connector(
                state=state,
                hubject_id=hubject_id if isinstance(hubject_id, str) else None,
            )
        )
    return connectors


def _to_float(value: object) -> float | None:
    """Coerce a number or numeric string to float, else ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None
