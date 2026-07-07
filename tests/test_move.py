"""Tests for the Move public-API fallback (matching and parsing helpers).

These import only pure helpers, so they need no Home Assistant test environment.
"""

from __future__ import annotations

from custom_components.swiss_ev_charging.const import (
    STATE_AVAILABLE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
)
from custom_components.swiss_ev_charging.move import is_move_evse_id, parse_search


def test_is_move_evse_id() -> None:
    """Only Move operator prefixes (CCI / CCC, any separator/case) are matched."""
    assert is_move_evse_id("CH*CCI*E22078")
    assert is_move_evse_id("CH*CCC*E50084")
    assert is_move_evse_id("ch-cci-e1")
    assert not is_move_evse_id("CH*ECUE123")  # eCarUp
    assert not is_move_evse_id("CH*EWZ*E130046")
    assert not is_move_evse_id("CH*SOC*E1")  # a Move prefix absent from this backend


def test_parse_search_maps_availability_by_evse_id() -> None:
    """Stations are keyed by their OICP EvseID with the availability mapped."""
    payload = {
        "Status": "success",
        "State": [
            {
                "Id": "hub1",
                "Availability": "partiallyAvailable",
                "Stations": [
                    {"Id": "CH*CCI*E1", "Availability": "available"},
                    {"Id": "CH*CCI*E2", "Availability": "occupied"},
                ],
            },
            {
                "Id": "hub2",
                "Stations": [
                    {"Id": "CH*CCC*E3", "Availability": "outOfService"},
                    {"Id": "CH*CCI*E4", "Availability": "unknown"},  # dropped
                    {"Id": "CH*CCI*E5", "Availability": "weird"},  # unmapped -> dropped
                    {"Availability": "available"},  # no id -> dropped
                ],
            },
        ],
    }
    states = parse_search(payload)
    assert states == {
        "CH*CCI*E1": STATE_AVAILABLE,
        "CH*CCI*E2": STATE_OCCUPIED,
        "CH*CCC*E3": STATE_OUT_OF_SERVICE,
    }


def test_parse_search_ignores_non_success_and_junk() -> None:
    """A non-success status or malformed payload yields an empty mapping."""
    assert parse_search({"Status": "error", "State": []}) == {}
    assert parse_search({"Status": "success"}) == {}
    assert parse_search(None) == {}
    assert parse_search("nope") == {}
    assert parse_search({"Status": "success", "State": [{"Stations": None}]}) == {}
