"""Tests for OICP parsing in the Swiss EV Charging API module.

These tests import only the parsing helpers, so they do not require a Home
Assistant test environment.
"""

from __future__ import annotations

from custom_components.swiss_ev_charging.api import (
    parse_evse_data,
    parse_evse_status,
)
from custom_components.swiss_ev_charging.const import (
    STATE_AVAILABLE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
)


def test_parse_evse_data_google_coordinates(evse_data: dict) -> None:
    """A record with Google-format coordinates is parsed correctly."""
    points = parse_evse_data(evse_data)

    point = points["CH*ABC*E1001"]
    assert point.name == "Zürich Bahnhofstrasse"
    assert point.operator == "Example Operator"
    assert point.latitude == 47.3769
    assert point.longitude == 8.5417
    # Max power is taken across all charging facilities.
    assert point.max_power_kw == 50.0
    assert "Type 2 Outlet" in point.plugs
    assert point.address == "Bahnhofstrasse 1, 8001 Zürich"


def test_parse_evse_data_decimal_degree_coordinates(evse_data: dict) -> None:
    """A record with DecimalDegree coordinates is parsed correctly."""
    points = parse_evse_data(evse_data)

    point = points["CH*ABC*E1002"]
    assert point.latitude == 47.355
    assert point.longitude == 8.552
    assert point.max_power_kw == 11.0


def test_parse_evse_data_covers_all_operators(evse_data: dict) -> None:
    """Records across multiple operator blocks are all collected."""
    points = parse_evse_data(evse_data)
    assert set(points) == {"CH*ABC*E1001", "CH*ABC*E1002", "CH*XYZ*E5001"}


def test_parse_evse_status_maps_states(evse_status: dict) -> None:
    """OICP status values map to the normalised states."""
    statuses = parse_evse_status(evse_status)
    assert statuses["CH*ABC*E1001"] == STATE_AVAILABLE
    assert statuses["CH*ABC*E1002"] == STATE_OCCUPIED
    assert statuses["CH*XYZ*E5001"] == STATE_OUT_OF_SERVICE


def test_parse_handles_empty_payload() -> None:
    """Missing top-level keys yield empty mappings rather than errors."""
    assert parse_evse_data({}) == {}
    assert parse_evse_status({}) == {}


def test_parse_evse_data_single_element_shapes() -> None:
    """The real feed collapses single elements to objects; parse without error.

    Regression test for the ``KeyError: 0`` crash: ``EVSEData``,
    ``EVSEDataRecord``, ``ChargingStationNames`` are single objects, ``Plugs`` a
    single string and ``ChargingFacilities`` a single object.
    """
    from .conftest import load_fixture

    points = parse_evse_data(load_fixture("evse_data_single.json"))

    point = points["CH*SGL*E1"]
    assert point.name == "Bern Single"
    assert point.operator == "Single Element Operator"
    # A single-string Plugs must become a one-element list, not per-character.
    assert point.plugs == ["CCS Combo 2 Plug (Cable Attached)"]
    assert point.max_power_kw == 75.0
    assert point.latitude == 46.9480


def test_first_localized_alternative_shapes() -> None:
    """_first_localized copes with dict/string/list and alternative key names."""
    from custom_components.swiss_ev_charging.api import _first_localized

    assert _first_localized({"lang": "de", "value": "A"}) == "A"
    assert _first_localized([{"lang": "de", "value": "B"}]) == "B"
    assert _first_localized({"@language": "de", "#text": "C"}) == "C"
    assert _first_localized("D") == "D"
    assert _first_localized(None) is None
