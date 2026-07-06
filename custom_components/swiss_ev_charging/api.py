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
    skipped = 0
    for operator_block in _as_list(payload.get("EVSEData")):
        operator_name = operator_block.get("OperatorName")
        for record in _as_list(operator_block.get("EVSEDataRecord")):
            try:
                evse_id = record.get("EvseID")
                if not evse_id:
                    continue
                latitude, longitude = _parse_coordinates(
                    record.get("GeoCoordinates")
                )
                points[evse_id] = ChargingPoint(
                    evse_id=evse_id,
                    name=_first_localized(record.get("ChargingStationNames")),
                    operator=operator_name,
                    plugs=[
                        p
                        for p in _as_list(record.get("Plugs"))
                        if isinstance(p, str)
                    ],
                    max_power_kw=_max_power(record.get("ChargingFacilities")),
                    latitude=latitude,
                    longitude=longitude,
                    address=_format_address(record.get("Address")),
                )
            except Exception:  # noqa: BLE001 - one bad record must not abort the parse
                skipped += 1
                _LOGGER.debug("Skipping unparseable EVSEDataRecord", exc_info=True)
    if skipped:
        _LOGGER.warning(
            "Parsed %d charging points, skipped %d unparseable records",
            len(points),
            skipped,
        )
    return points


def parse_evse_status(payload: dict) -> dict[str, str]:
    """Parse an OICP EVSEStatus document into ``{evse_id: normalised_state}``."""
    statuses: dict[str, str] = {}
    skipped = 0
    for operator_block in _as_list(payload.get("EVSEStatuses")):
        for record in _as_list(operator_block.get("EVSEStatusRecord")):
            try:
                evse_id = record.get("EvseID")
                if not evse_id:
                    continue
                statuses[evse_id] = OICP_STATUS_MAP.get(
                    record.get("EVSEStatus"), STATE_UNKNOWN
                )
            except Exception:  # noqa: BLE001 - one bad record must not abort the parse
                skipped += 1
                _LOGGER.debug("Skipping unparseable EVSEStatusRecord", exc_info=True)
    if skipped:
        _LOGGER.warning(
            "Parsed %d statuses, skipped %d unparseable records",
            len(statuses),
            skipped,
        )
    return statuses


def normalize_evse_id(evse_id: str) -> str:
    """Canonicalise an ``EvseID`` for tolerant matching across the two feeds.

    Master (EVSEData) and live (EVSEStatus) records are joined by ``EvseID``, but
    some operators - eCarUp (``CH*ECU*...``) in particular - format the same id
    differently between the files: varying case, or the ``*``/``-`` separators.
    Reducing to upper-case alphanumerics lets the merge fall back to a match when
    the exact strings differ, so those stations show live availability instead of
    ``unknown``.
    """
    return "".join(ch for ch in evse_id.upper() if ch.isalnum())


def index_status_by_normalized(statuses: dict[str, str]) -> dict[str, str]:
    """Index statuses by :func:`normalize_evse_id`, dropping ambiguous keys.

    If two differently-formatted ids collapse to the same normalized key but carry
    conflicting states, the key is dropped so the fallback never guesses.
    """
    index: dict[str, str] = {}
    ambiguous: set[str] = set()
    for evse_id, state in statuses.items():
        key = normalize_evse_id(evse_id)
        if key in index and index[key] != state:
            ambiguous.add(key)
        else:
            index.setdefault(key, state)
    for key in ambiguous:
        index.pop(key, None)
    return index


def _as_list(value: object) -> list:
    """Normalise an OICP value that may be a single object or a list into a list.

    The feed follows the XML-to-JSON convention where a single element is
    serialised as an object and multiple elements as an array; this collapses
    both shapes (and ``None``) to a list so callers can always iterate.
    """
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _first_localized(names: object) -> str | None:
    """Return the first usable string from an OICP localised-name value.

    Accepts a list, a single ``{lang, value}`` object, alternative key shapes
    such as ``{"@language", "#text"}`` or ``{lang: text}``, or a plain string.
    """
    lang_keys = {"lang", "language", "@language"}
    for item in _as_list(names):
        if isinstance(item, dict):
            for key in ("value", "#text", "text"):
                text = item.get(key)
                if isinstance(text, str) and text:
                    return text
            # Fallback: first string value whose key is not a language marker.
            for key, candidate in item.items():
                if key in lang_keys:
                    continue
                if isinstance(candidate, str) and candidate:
                    return candidate
        elif isinstance(item, str) and item:
            return item
    return None


def _max_power(facilities: object) -> float | None:
    """Return the highest power (kW) across the charging facilities.

    The real feed uses a lowercase ``power`` key whose value is a string
    (e.g. ``"22.0"``); older/other OICP variants use ``Power`` as a number.
    Both are handled.
    """
    powers = []
    for facility in _as_list(facilities):
        if not isinstance(facility, dict):
            continue
        power = _to_float(facility.get("power", facility.get("Power")))
        if power is not None:
            powers.append(power)
    return max(powers) if powers else None


def _to_float(value: object) -> float | None:
    """Coerce an int/float or numeric string into a float, else ``None``."""
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


def _parse_coordinates(geo: dict | None) -> tuple[float | None, float | None]:
    """Extract ``(latitude, longitude)`` from an OICP GeoCoordinates object.

    OICP allows several representations; we support the two common in this feed:
    ``Google`` ("lat lng" string) and ``DecimalDegree`` ({Latitude, Longitude}).
    """
    if not isinstance(geo, dict):
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
    if not isinstance(address, dict):
        return None
    street = address.get("Street")
    house = address.get("HouseNum")
    postal = address.get("PostalCode")
    city = address.get("City")
    line = " ".join(part for part in (street, house) if part)
    locality = " ".join(part for part in (postal, city) if part)
    full = ", ".join(part for part in (line, locality) if part)
    return full or None
