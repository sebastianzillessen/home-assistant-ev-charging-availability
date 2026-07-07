"""Best-effort live status for Move stations via Move's public app backend.

The SFOE ich-tanke-strom OICP status feed reports ``Unknown`` for a share of
**Move** charging points (operator ids ``CH*CCI`` and ``CH*CCC``) even though
Move itself knows the live state. The Move mobile app is backed by a key-less
JSON endpoint that exposes per-EVSE availability:

* ``GET https://app.move.ch/search?latitude=..&longitude=..&radius=<km>``

Each returned station's ``Id`` is exactly the OICP ``EvseID`` used in the SFOE
feed, so the join is direct and authoritative - no coordinate matching needed.

Everything here is best-effort: any network or parsing failure yields an empty
result, leaving the affected stations ``unknown`` exactly as before.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
import logging

from aiohttp import ClientError, ClientSession, ClientTimeout

from .api import normalize_evse_id
from .const import (
    STATE_AVAILABLE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)

# Public, key-less Move app backend (same call the MOVE mobile app makes).
MOVE_SEARCH_URL = "https://app.move.ch/search"

# Operator ids (SFOE ``EvseID`` prefixes) whose live status the Move ``/search``
# endpoint carries. Move's own points are ``CH*CCI`` / ``CH*CCC``; the endpoint
# also returns roaming networks near the queried point, and a few operators the
# SFOE feed leaves ``Unknown`` have accurate live status there, joined by the
# exact EvseID: Repower / PLUG N ROLL (``CH*REP``), AVIA VOLT (``CH*AVI``) and
# Power Up (``CH*POW``).
_MOVE_KEY_PREFIXES = ("CHCCI", "CHCCC", "CHREP", "CHAVI", "CHPOW")

# Query radius (km) is grown to cover all tracked targets, plus this margin.
_RADIUS_MARGIN_KM = 0.5
# Cap the single-query radius so a spread-out set of pinned stations cannot pull
# the whole European roaming dataset; targets beyond it simply stay ``unknown``.
_MAX_RADIUS_KM = 25.0

_TIMEOUT = ClientTimeout(total=30)

# Move availability value -> this integration's normalised availability states.
# ``partiallyAvailable`` only appears at the hub level, never per-EVSE, so the
# per-station values below are the full set we act on.
_AVAILABILITY_MAP: dict[str, str] = {
    "available": STATE_AVAILABLE,
    "occupied": STATE_OCCUPIED,
    "outOfService": STATE_OUT_OF_SERVICE,
    "unknown": STATE_UNKNOWN,
}


def is_move_search_evse_id(evse_id: str) -> bool:
    """Return True if ``evse_id``'s live status is resolvable via Move ``/search``.

    Covers Move's own points plus the roaming networks (Repower/PLUG N ROLL,
    AVIA VOLT, Power Up) the endpoint reports with accurate live status.
    """
    key = normalize_evse_id(evse_id)
    return key.startswith(_MOVE_KEY_PREFIXES)


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


def parse_search(payload: object) -> dict[str, str]:
    """Parse a Move ``/search`` response into ``{EvseID: normalised_state}``.

    Only concrete, mappable availabilities are returned; ``unknown`` and any
    unrecognised value are omitted so they never override the SFOE state.
    """
    states: dict[str, str] = {}
    if not isinstance(payload, dict) or payload.get("Status") != "success":
        return states
    for hub in payload.get("State") or []:
        if not isinstance(hub, dict):
            continue
        for station in hub.get("Stations") or []:
            if not isinstance(station, dict):
                continue
            evse_id = station.get("Id")
            state = _AVAILABILITY_MAP.get(station.get("Availability"))
            if isinstance(evse_id, str) and state is not None and state != STATE_UNKNOWN:
                states[evse_id] = state
    return states


async def async_resolve_move_states(
    session: ClientSession, targets: list[tuple[str, float, float]]
) -> dict[str, str]:
    """Resolve live states for Move EVSEs the SFOE feed left ``unknown``.

    ``targets`` is a list of ``(evse_id, latitude, longitude)`` for Move EVSEs
    with known coordinates. Returns ``{evse_id: state}`` for those resolved to a
    concrete (non-``unknown``) state; unresolved ids are omitted. Never raises:
    any failure yields ``{}``.
    """
    points = [(e, la, lo) for e, la, lo in targets if la is not None and lo is not None]
    if not points:
        return {}

    lats = [la for _, la, _ in points]
    lons = [lo for _, _, lo in points]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    # Radius that covers every target from the centre, plus a small margin.
    span_m = max(
        _distance_m(center_lat, center_lon, la, lo) for _, la, lo in points
    )
    radius_km = min(span_m / 1000 + _RADIUS_MARGIN_KM, _MAX_RADIUS_KM)

    try:
        payload = await _async_fetch_search(session, center_lat, center_lon, radius_km)
    except (ClientError, ValueError, TimeoutError) as err:
        _LOGGER.debug("Move search query failed: %s", err)
        return {}

    by_evse_id = parse_search(payload)
    # Only return states for the EVSEs we were actually asked about.
    wanted = {evse_id for evse_id, _, _ in points}
    return {
        evse_id: state for evse_id, state in by_evse_id.items() if evse_id in wanted
    }


async def _async_fetch_search(
    session: ClientSession, latitude: float, longitude: float, radius_km: float
) -> object:
    """GET the Move search endpoint for a centre point and radius (km)."""
    # aiohttp only accepts str/int query values across versions, so stringify.
    params = {
        "latitude": repr(latitude),
        "longitude": repr(longitude),
        "radius": repr(radius_km),
    }
    async with session.get(MOVE_SEARCH_URL, params=params, timeout=_TIMEOUT) as response:
        response.raise_for_status()
        return await response.json(content_type=None)
