"""Client and parsing for the SFOE ich-tanke-strom open-data endpoints.

The service publishes two country-wide JSON files in the OICP 2.3 format:

* ``EVSEData``   - static master data (location, operator, plugs, power)
* ``EVSEStatus`` - live availability per charging point (EVSE)

Both are plain HTTP downloads (no key). The individual charging points are joined
across the two files by their ``EvseID``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import EVSE_DATA_URL, EVSE_STATUS_URL, OICP_STATUS_MAP, STATE_UNKNOWN

_LOGGER = logging.getLogger(__name__)

# The status file is a few MB; give the download generous headroom.
_REQUEST_TIMEOUT = ClientTimeout(total=120)


class SwissEvChargingApiError(Exception):
    """Raised when the open-data endpoints cannot be fetched or parsed."""


@dataclass(slots=True)
class ChargingPoint:
    """Normalised static master data for a single EVSE (charging point)."""

    evse_id: str
    name: str | None = None
    operator: str | None = None
    plugs: list[str] = field(default_factory=list)
    max_power_kw: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None


class SwissEvChargingApi:
    """Fetch and parse the two OICP files into normalised structures."""

    def __init__(self, session: ClientSession) -> None:
        """Initialise with a shared aiohttp session."""
        self._session = session

    async def async_get_master_data(self) -> dict[str, ChargingPoint]:
        """Download EVSEData and return a ``{evse_id: ChargingPoint}`` mapping."""
        payload = await self._async_fetch_json(EVSE_DATA_URL)
        return parse_evse_data(payload)

    async def async_get_status(self) -> dict[str, str]:
        """Download EVSEStatus and return a ``{evse_id: normalised_state}`` mapping."""
        payload = await self._async_fetch_json(EVSE_STATUS_URL)
        return parse_evse_status(payload)

    async def _async_fetch_json(self, url: str) -> dict:
        """Fetch and decode a JSON document, translating errors to a common type."""
        try:
            async with self._session.get(url, timeout=_REQUEST_TIMEOUT) as response:
                response.raise_for_status()
                # content_type=None: the CDN may not send an application/json header.
                return await response.json(content_type=None)
        except ClientError as err:
            raise SwissEvChargingApiError(f"Error fetching {url}: {err}") from err
        except ValueError as err:  # JSON decoding failure
            raise SwissEvChargingApiError(f"Invalid JSON from {url}: {err}") from err


def parse_evse_data(payload: dict) -> dict[str, ChargingPoint]:
    """Parse an OICP EVSEData document into ``{evse_id: ChargingPoint}``."""
    points: dict[str, ChargingPoint] = {}
    for operator_block in payload.get("EVSEData", []):
        operator_name = operator_block.get("OperatorName")
        for record in operator_block.get("EVSEDataRecord", []):
            evse_id = record.get("EvseID")
            if not evse_id:
                continue
            latitude, longitude = _parse_coordinates(record.get("GeoCoordinates"))
            points[evse_id] = ChargingPoint(
                evse_id=evse_id,
                name=_first_localized(record.get("ChargingStationNames")),
                operator=operator_name,
                plugs=list(record.get("Plugs", [])),
                max_power_kw=_max_power(record.get("ChargingFacilities")),
                latitude=latitude,
                longitude=longitude,
                address=_format_address(record.get("Address")),
            )
    return points


def parse_evse_status(payload: dict) -> dict[str, str]:
    """Parse an OICP EVSEStatus document into ``{evse_id: normalised_state}``."""
    statuses: dict[str, str] = {}
    for operator_block in payload.get("EVSEStatuses", []):
        for record in operator_block.get("EVSEStatusRecord", []):
            evse_id = record.get("EvseID")
            if not evse_id:
                continue
            statuses[evse_id] = OICP_STATUS_MAP.get(
                record.get("EVSEStatus"), STATE_UNKNOWN
            )
    return statuses


def _first_localized(names: list | None) -> str | None:
    """Return the first value from an OICP list of localised strings."""
    if not names:
        return None
    first = names[0]
    if isinstance(first, dict):
        return first.get("value")
    return str(first)


def _max_power(facilities: list | None) -> float | None:
    """Return the highest ``Power`` (kW) across the charging facilities."""
    if not facilities:
        return None
    powers = [
        facility["Power"]
        for facility in facilities
        if isinstance(facility, dict) and isinstance(facility.get("Power"), (int, float))
    ]
    return float(max(powers)) if powers else None


def _parse_coordinates(geo: dict | None) -> tuple[float | None, float | None]:
    """Extract ``(latitude, longitude)`` from an OICP GeoCoordinates object.

    OICP allows several representations; we support the two common in this feed:
    ``Google`` ("lat lng" string) and ``DecimalDegree`` ({Latitude, Longitude}).
    """
    if not geo:
        return None, None

    google = geo.get("Google")
    if isinstance(google, str):
        parts = google.replace(",", " ").split()
        if len(parts) == 2:
            try:
                return float(parts[0]), float(parts[1])
            except ValueError:
                pass

    decimal = geo.get("DecimalDegree")
    if isinstance(decimal, dict):
        lat = decimal.get("Latitude")
        lon = decimal.get("Longitude")
        try:
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        except (TypeError, ValueError):
            pass

    return None, None


def _format_address(address: dict | None) -> str | None:
    """Build a human-readable single-line address from an OICP Address object."""
    if not address:
        return None
    street = address.get("Street")
    house = address.get("HouseNum")
    postal = address.get("PostalCode")
    city = address.get("City")
    line = " ".join(part for part in (street, house) if part)
    locality = " ".join(part for part in (postal, city) if part)
    full = ", ".join(part for part in (line, locality) if part)
    return full or None
