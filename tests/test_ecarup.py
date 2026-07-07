"""Tests for the eCarUp public-API fallback (matching and parsing helpers).

These import only pure helpers, so they need no Home Assistant test environment.
"""

from __future__ import annotations

from custom_components.swiss_ev_charging.const import (
    STATE_AVAILABLE,
    STATE_MAINTENANCE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_RESERVED,
    STATE_UNKNOWN,
)
from custom_components.swiss_ev_charging.ecarup import (
    _Connector,
    _parse_connectors,
    _parse_map,
    _Station,
    is_ecarup_evse_id,
    match_state,
)

# A real eCarUp EVSE near Zürich (Pflegeheim Salem), coordinates from the feed.
_EVSE = "CH*ECUEDR654CLPY9WN3HBTTGEYKFKTVS"
_LAT = 47.380003
_LON = 8.552967


def test_is_ecarup_evse_id() -> None:
    """Only the eCarUp operator prefix (any separator/case) is recognised."""
    assert is_ecarup_evse_id("CH*ECUEDR654CLPY9WN3HBTTGEYKFKTVS")
    assert is_ecarup_evse_id("ch-ecu-e1234")
    assert not is_ecarup_evse_id("CH*EWZ*E130046")
    assert not is_ecarup_evse_id("CH*CCI*E22078")


def test_match_via_hubject_id_is_authoritative() -> None:
    """An exact Hubject.ID match returns that connector's state, ignoring distance."""
    stations = [
        # Far away, but carries the exact roaming id -> wins.
        _Station(
            station_id="a",
            latitude=46.0,
            longitude=7.0,
            connectors=[_Connector(state=STATE_OCCUPIED, hubject_id=_EVSE)],
        ),
    ]
    assert match_state(_EVSE, _LAT, _LON, stations) == STATE_OCCUPIED


def test_match_via_nearest_station_when_connectors_agree() -> None:
    """Without a Hubject.ID, the nearest station's unanimous state is used."""
    stations = [
        _Station(
            station_id="near",
            latitude=_LAT,
            longitude=_LON,
            connectors=[
                _Connector(state=STATE_AVAILABLE, hubject_id=None),
                _Connector(state=STATE_AVAILABLE, hubject_id=None),
            ],
        ),
    ]
    assert match_state(_EVSE, _LAT, _LON, stations) == STATE_AVAILABLE


def test_no_match_when_nearest_station_connectors_conflict() -> None:
    """A multi-connector site with mixed states is left unresolved, never guessed."""
    stations = [
        _Station(
            station_id="near",
            latitude=_LAT,
            longitude=_LON,
            connectors=[
                _Connector(state=STATE_AVAILABLE, hubject_id=None),
                _Connector(state=STATE_OCCUPIED, hubject_id=None),
            ],
        ),
    ]
    assert match_state(_EVSE, _LAT, _LON, stations) is None


def test_no_match_when_no_station_within_radius() -> None:
    """A station too far from the tracked coordinate does not resolve the EVSE."""
    stations = [
        _Station(
            station_id="far",
            latitude=_LAT + 0.01,  # ~1.1 km away
            longitude=_LON,
            connectors=[_Connector(state=STATE_AVAILABLE, hubject_id=None)],
        ),
    ]
    assert match_state(_EVSE, _LAT, _LON, stations) is None


def test_parse_map_extracts_stations() -> None:
    """The map response is parsed into stations with coordinates."""
    payload = {
        "Stations": [
            {"Id": "g1", "Name": "A", "Latitude": 47.38, "Longitude": 8.55},
            {"Id": None, "Name": "bad"},  # dropped: no id
        ],
        "Clusters": [],
    }
    stations = _parse_map(payload)
    assert len(stations) == 1
    assert stations[0].station_id == "g1"
    assert stations[0].latitude == 47.38


def test_parse_connectors_maps_state_enum_and_hubject() -> None:
    """Connector State ints map to normalised states; Hubject.ID is extracted."""
    payload = {
        "Connectors": [
            {"State": 1, "Hubject": {"ID": _EVSE, "IsEnabled": True}},
            {"State": 2, "Hubject": {"ID": None}},
            {"State": 0, "Hubject": None},  # Offline -> out_of_service
            {"State": 3},  # Maintenance -> maintenance
            {"State": 4},  # Reserved -> reserved
            {"State": 5},  # Unknown -> kept as unknown
            {"State": 99},  # unmapped -> dropped
        ]
    }
    connectors = _parse_connectors(payload)
    assert [c.state for c in connectors] == [
        STATE_AVAILABLE,
        STATE_OCCUPIED,
        STATE_OUT_OF_SERVICE,
        STATE_MAINTENANCE,
        STATE_RESERVED,
        STATE_UNKNOWN,
    ]
    assert connectors[0].hubject_id == _EVSE
    assert connectors[1].hubject_id is None


def test_unknown_connector_does_not_block_unanimous_match() -> None:
    """An ``unknown`` connector is ignored when the concrete ones all agree."""
    stations = [
        _Station(
            station_id="near",
            latitude=_LAT,
            longitude=_LON,
            connectors=[
                _Connector(state=STATE_AVAILABLE, hubject_id=None),
                _Connector(state=STATE_UNKNOWN, hubject_id=None),
            ],
        ),
    ]
    assert match_state(_EVSE, _LAT, _LON, stations) == STATE_AVAILABLE


def test_parse_handles_junk_payloads() -> None:
    """Non-dict / missing-key payloads parse to empty lists, not errors."""
    assert _parse_map(None) == []
    assert _parse_map({}) == []
    assert _parse_connectors("nope") == []
    assert _parse_connectors({}) == []
