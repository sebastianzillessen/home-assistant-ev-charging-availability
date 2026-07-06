"""Tests for the Swiss EV Charging coordinator selection and merge logic.

These require the Home Assistant test environment
(``pytest-homeassistant-custom-component``).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swiss_ev_charging.api import parse_evse_data, parse_evse_status
from custom_components.swiss_ev_charging.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAX_STATIONS,
    CONF_MIN_POWER,
    CONF_PINNED_EVSE_IDS,
    CONF_RADIUS,
    DOMAIN,
    STATE_AVAILABLE,
    STATE_OUT_OF_SERVICE,
)
from custom_components.swiss_ev_charging.coordinator import SwissEvChargingCoordinator

from .conftest import load_fixture


def _make_entry(hass, data: dict) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    return entry


async def _run(hass, coordinator, master, status):
    with patch(
        "custom_components.swiss_ev_charging.coordinator.SwissEvChargingApi"
        ".async_get_master_data",
        return_value=master,
    ), patch(
        "custom_components.swiss_ev_charging.coordinator.SwissEvChargingApi"
        ".async_get_status",
        return_value=status,
    ):
        return await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_nearby_selection_orders_by_distance(hass) -> None:
    """Nearby stations within the radius are selected, closest first."""
    master = parse_evse_data(load_fixture("evse_data.json"))
    status = parse_evse_status(load_fixture("evse_status.json"))

    # Origin very close to the two Zürich chargers; Pany is ~150 km away.
    entry = _make_entry(
        hass,
        {
            CONF_LATITUDE: 47.3769,
            CONF_LONGITUDE: 8.5417,
            CONF_RADIUS: 5000,
            CONF_MAX_STATIONS: 5,
            CONF_MIN_POWER: 0,
        },
    )
    coordinator = SwissEvChargingCoordinator(hass, entry)
    data = await _run(hass, coordinator, master, status)

    assert list(data)[0] == "CH*ABC*E1001"
    assert "CH*XYZ*E5001" not in data  # outside the radius
    assert data["CH*ABC*E1001"].state == STATE_AVAILABLE


@pytest.mark.asyncio
async def test_pinned_included_regardless_of_distance(hass) -> None:
    """Pinned EVSE IDs are always tracked even when far from the origin."""
    master = parse_evse_data(load_fixture("evse_data.json"))
    status = parse_evse_status(load_fixture("evse_status.json"))

    entry = _make_entry(
        hass,
        {
            CONF_LATITUDE: 47.3769,
            CONF_LONGITUDE: 8.5417,
            CONF_RADIUS: 1000,
            CONF_MAX_STATIONS: 5,
            CONF_PINNED_EVSE_IDS: ["CH*XYZ*E5001"],
        },
    )
    coordinator = SwissEvChargingCoordinator(hass, entry)
    data = await _run(hass, coordinator, master, status)

    assert "CH*XYZ*E5001" in data
    assert data["CH*XYZ*E5001"].is_pinned is True
    assert data["CH*XYZ*E5001"].state == STATE_OUT_OF_SERVICE


@pytest.mark.asyncio
async def test_min_power_filter(hass) -> None:
    """A minimum-power filter excludes lower-power chargers from nearby results."""
    master = parse_evse_data(load_fixture("evse_data.json"))
    status = parse_evse_status(load_fixture("evse_status.json"))

    entry = _make_entry(
        hass,
        {
            CONF_LATITUDE: 47.3769,
            CONF_LONGITUDE: 8.5417,
            CONF_RADIUS: 5000,
            CONF_MAX_STATIONS: 5,
            CONF_MIN_POWER: 50,
        },
    )
    coordinator = SwissEvChargingCoordinator(hass, entry)
    data = await _run(hass, coordinator, master, status)

    assert "CH*ABC*E1001" in data  # 50 kW DC facility
    assert "CH*ABC*E1002" not in data  # only 11 kW
