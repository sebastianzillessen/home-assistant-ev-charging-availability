"""Tests for the Swiss EV Charging config flow."""

from __future__ import annotations

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.swiss_ev_charging.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PINNED_EVSE_IDS,
    CONF_RADIUS,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_user_flow_creates_entry_with_location(hass) -> None:
    """A location-only submission creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LATITUDE: 47.3769,
            CONF_LONGITUDE: 8.5417,
            CONF_RADIUS: 1000,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LATITUDE] == 47.3769


@pytest.mark.asyncio
async def test_user_flow_accepts_pinned_only(hass) -> None:
    """Pinned IDs alone (no location) are accepted and normalised to a list."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LATITUDE: None,
            CONF_LONGITUDE: None,
            CONF_PINNED_EVSE_IDS: "CH*ABC*E1001, CH*XYZ*E5001",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PINNED_EVSE_IDS] == [
        "CH*ABC*E1001",
        "CH*XYZ*E5001",
    ]


@pytest.mark.asyncio
async def test_user_flow_requires_selection(hass) -> None:
    """Submitting neither a location nor pinned IDs shows an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LATITUDE: None,
            CONF_LONGITUDE: None,
            CONF_PINNED_EVSE_IDS: "",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_selection"}
