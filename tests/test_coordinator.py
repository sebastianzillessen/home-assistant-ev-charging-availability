"""Tests for the Swiss EV Charging coordinator selection and merge logic.

These require the Home Assistant test environment
(``pytest-homeassistant-custom-component``).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.swiss_ev_charging.api import (
    ChargingPoint,
    parse_evse_data,
    parse_evse_status,
)
from custom_components.swiss_ev_charging.const import (
    CONF_ALERT_RADIUS,
    CONF_DISPLAY_RADIUS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAP_MARKER_STYLE,
    CONF_MAX_STATIONS,
    CONF_MIN_POWER,
    CONF_NAME_WITH_POWER,
    CONF_NOTIFY_ON_AVAILABLE,
    CONF_PINNED_EVSE_IDS,
    CONF_RADIUS,
    CONF_TAG,
    DOMAIN,
    MARKER_STYLE_GLYPH,
    MARKER_STYLE_OFF,
    MARKER_STYLE_PIP,
    STATE_AVAILABLE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_UNKNOWN,
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
async def test_tag_is_trimmed(hass) -> None:
    """The tag option is exposed trimmed (blank -> None)."""
    entry = _make_entry(
        hass, {CONF_PINNED_EVSE_IDS: ["CH*ABC*E1001"], CONF_TAG: "  Home  "}
    )
    coordinator = SwissEvChargingCoordinator(hass, entry)
    assert coordinator.tag == "Home"

    blank = _make_entry(hass, {CONF_PINNED_EVSE_IDS: ["CH*ABC*E1001"], CONF_TAG: "  "})
    assert SwissEvChargingCoordinator(hass, blank).tag is None


@pytest.mark.asyncio
async def test_map_marker_style_option(hass) -> None:
    """The marker-style option defaults off, honours a choice, and migrates."""
    pin = ["CH*ABC*E1001"]

    # Unset -> off (default).
    default = _make_entry(hass, {CONF_PINNED_EVSE_IDS: pin})
    assert (
        SwissEvChargingCoordinator(hass, default).map_marker_style
        == MARKER_STYLE_OFF
    )

    # An explicit style is used verbatim.
    chosen = _make_entry(
        hass, {CONF_PINNED_EVSE_IDS: pin, CONF_MAP_MARKER_STYLE: MARKER_STYLE_GLYPH}
    )
    assert SwissEvChargingCoordinator(hass, chosen).map_marker_style == MARKER_STYLE_GLYPH

    # Legacy boolean (color_map_markers=True) migrates to the plug + pip style.
    legacy = _make_entry(
        hass, {CONF_PINNED_EVSE_IDS: pin, "color_map_markers": True}
    )
    assert SwissEvChargingCoordinator(hass, legacy).map_marker_style == MARKER_STYLE_PIP


@pytest.mark.asyncio
async def test_name_with_power_option_suffixes_device_name(hass) -> None:
    """The name-with-power option appends the rated power to the device name."""
    from custom_components.swiss_ev_charging.api import ChargingPoint
    from custom_components.swiss_ev_charging.entity import _device_name

    pin = ["CH*ABC*E1001"]
    point = ChargingPoint(
        evse_id="CH*ABC*E1001", name="Test Station", max_power_kw=224.0
    )

    off = _make_entry(hass, {CONF_PINNED_EVSE_IDS: pin})
    coord_off = SwissEvChargingCoordinator(hass, off)
    assert coord_off.name_with_power is False
    assert _device_name(coord_off, point) == "Test Station"

    on = _make_entry(hass, {CONF_PINNED_EVSE_IDS: pin, CONF_NAME_WITH_POWER: True})
    coord_on = SwissEvChargingCoordinator(hass, on)
    assert coord_on.name_with_power is True
    assert _device_name(coord_on, point) == "Test Station · 224 kW"


@pytest.mark.asyncio
async def test_notify_on_available_transition(hass) -> None:
    """A station transitioning to available triggers exactly one notification."""
    master = parse_evse_data(load_fixture("evse_data.json"))
    entry = _make_entry(
        hass,
        {
            CONF_PINNED_EVSE_IDS: ["CH*ABC*E1001"],
            CONF_NOTIFY_ON_AVAILABLE: True,
            CONF_TAG: "Home",
        },
    )
    coordinator = SwissEvChargingCoordinator(hass, entry)
    calls = async_mock_service(hass, "persistent_notification", "create")

    # First refresh (occupied): no previous data, so no notification.
    coordinator.data = await _run(
        hass, coordinator, master, {"CH*ABC*E1001": STATE_OCCUPIED}
    )
    await hass.async_block_till_done()
    assert len(calls) == 0

    # Transition to available: exactly one notification carrying the tag.
    coordinator.data = await _run(
        hass, coordinator, master, {"CH*ABC*E1001": STATE_AVAILABLE}
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert "[Home]" in calls[0].data["message"]

    # Still available: no duplicate notification.
    coordinator.data = await _run(
        hass, coordinator, master, {"CH*ABC*E1001": STATE_AVAILABLE}
    )
    await hass.async_block_till_done()
    assert len(calls) == 1


# Fixture distances from the origin 47.3769, 8.5417: E1001 = 0 m, E1002 = 2556 m.
_ORIGIN = {CONF_LATITUDE: 47.3769, CONF_LONGITUDE: 8.5417}


async def _transition_to_available(hass, coordinator, master):
    """Poll occupied then available for both Zürich stations; return notify calls."""
    calls = async_mock_service(hass, "persistent_notification", "create")
    both = ("CH*ABC*E1001", "CH*ABC*E1002")
    coordinator.data = await _run(
        hass, coordinator, master, {e: STATE_OCCUPIED for e in both}
    )
    await hass.async_block_till_done()
    coordinator.data = await _run(
        hass, coordinator, master, {e: STATE_AVAILABLE for e in both}
    )
    await hass.async_block_till_done()
    return calls


@pytest.mark.asyncio
async def test_alert_radius_gates_nearby_notifications(hass) -> None:
    """With no pins, only stations within the alert radius alert."""
    master = parse_evse_data(load_fixture("evse_data.json"))
    entry = _make_entry(
        hass,
        {
            **_ORIGIN,
            CONF_DISPLAY_RADIUS: 5000,  # both stations shown
            CONF_ALERT_RADIUS: 1000,  # only E1001 (0 m) may alert; E1002 is 2556 m
            CONF_NOTIFY_ON_AVAILABLE: True,
        },
    )
    coordinator = SwissEvChargingCoordinator(hass, entry)
    # Both are tracked/shown ...
    calls = await _transition_to_available(hass, coordinator, master)
    assert set(coordinator.data) == {"CH*ABC*E1001", "CH*ABC*E1002"}
    # ... but only the one inside the alert radius fires.
    assert len(calls) == 1
    assert "Bahnhofstrasse" in calls[0].data["message"]  # E1001
    assert "Seefeld" not in calls[0].data["message"]  # E1002 suppressed


@pytest.mark.asyncio
async def test_pinned_present_means_only_pinned_alert(hass) -> None:
    """Once any station is pinned, only pinned stations alert (radius ignored)."""
    master = parse_evse_data(load_fixture("evse_data.json"))
    entry = _make_entry(
        hass,
        {
            **_ORIGIN,
            CONF_DISPLAY_RADIUS: 5000,
            CONF_ALERT_RADIUS: 1000,
            CONF_PINNED_EVSE_IDS: ["CH*ABC*E1002"],  # far pin
            CONF_NOTIFY_ON_AVAILABLE: True,
        },
    )
    coordinator = SwissEvChargingCoordinator(hass, entry)
    calls = await _transition_to_available(hass, coordinator, master)
    # E1001 is within the alert radius but NOT pinned, so it is suppressed;
    # only the pinned E1002 alerts.
    assert len(calls) == 1
    assert "Seefeld" in calls[0].data["message"]  # E1002 (pinned)


@pytest.mark.asyncio
async def test_display_radius_drives_selection(hass) -> None:
    """The display radius (not the alert radius) decides which stations are shown."""
    master = parse_evse_data(load_fixture("evse_data.json"))
    status = parse_evse_status(load_fixture("evse_status.json"))

    narrow = SwissEvChargingCoordinator(
        hass, _make_entry(hass, {**_ORIGIN, CONF_DISPLAY_RADIUS: 2000})
    )
    data = await _run(hass, narrow, master, status)
    assert "CH*ABC*E1001" in data  # 0 m
    assert "CH*ABC*E1002" not in data  # 2556 m > 2000

    wide = SwissEvChargingCoordinator(
        hass, _make_entry(hass, {**_ORIGIN, CONF_DISPLAY_RADIUS: 5000})
    )
    data = await _run(hass, wide, master, status)
    assert "CH*ABC*E1002" in data  # now within the display radius


@pytest.mark.asyncio
async def test_legacy_radius_falls_back_for_both(hass) -> None:
    """A pre-split entry with only ``radius`` keeps the old behaviour."""
    master = parse_evse_data(load_fixture("evse_data.json"))
    entry = _make_entry(
        hass, {**_ORIGIN, CONF_RADIUS: 5000, CONF_NOTIFY_ON_AVAILABLE: True}
    )
    coordinator = SwissEvChargingCoordinator(hass, entry)
    # Legacy radius resolves to both display and alert.
    assert coordinator.display_radius == 5000
    assert coordinator.alert_radius == 5000
    # No pins + alert radius covering both -> both stations alert, as before.
    calls = await _transition_to_available(hass, coordinator, master)
    assert len(calls) == 2


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


@pytest.mark.asyncio
async def test_status_matches_across_evse_id_formats(hass) -> None:
    """A status whose EvseID is formatted differently still resolves (eCarUp)."""
    master = {
        "CH*ECU*E9": ChargingPoint(
            evse_id="CH*ECU*E9", latitude=47.0, longitude=8.0
        ),
        "CH*ABC*E5": ChargingPoint(evse_id="CH*ABC*E5"),
    }
    # eCarUp reports the same EVSE with a different id format; ABC is absent.
    status = {"checue9": STATE_AVAILABLE}
    entry = _make_entry(hass, {CONF_PINNED_EVSE_IDS: ["CH*ECU*E9", "CH*ABC*E5"]})
    coordinator = SwissEvChargingCoordinator(hass, entry)

    data = await _run(hass, coordinator, master, status)

    assert data["CH*ECU*E9"].state == STATE_AVAILABLE  # matched via normalization
    assert data["CH*ABC*E5"].state == STATE_UNKNOWN  # genuinely absent
    assert coordinator.unmatched_ids == ["CH*ABC*E5"]
    assert coordinator.status_feed_size == 1


@pytest.mark.asyncio
async def test_ecarup_fallback_fills_unknown_states(hass) -> None:
    """An eCarUp EVSE left unknown by SFOE is filled from the eCarUp public API."""
    master = {
        "CH*ECUE123": ChargingPoint(
            evse_id="CH*ECUE123", latitude=47.38, longitude=8.55
        ),
        "CH*ABC*E5": ChargingPoint(evse_id="CH*ABC*E5", latitude=47.38, longitude=8.55),
    }
    # SFOE knows nothing about either EVSE.
    status: dict[str, str] = {}
    entry = _make_entry(hass, {CONF_PINNED_EVSE_IDS: ["CH*ECUE123", "CH*ABC*E5"]})
    coordinator = SwissEvChargingCoordinator(hass, entry)

    with patch(
        "custom_components.swiss_ev_charging.coordinator.async_resolve_ecarup_states",
        return_value={"CH*ECUE123": STATE_AVAILABLE},
    ) as resolver:
        data = await _run(hass, coordinator, master, status)

    # Only the eCarUp EVSE (with coordinates) was offered to the resolver.
    targets = resolver.call_args.args[1]
    assert [t[0] for t in targets] == ["CH*ECUE123"]

    assert data["CH*ECUE123"].state == STATE_AVAILABLE  # filled from eCarUp
    assert data["CH*ABC*E5"].state == STATE_UNKNOWN  # non-eCarUp, still unknown
    assert coordinator.ecarup_resolved_ids == ["CH*ECUE123"]
    # The filled EVSE is no longer reported as unmatched.
    assert "CH*ECUE123" not in coordinator.unmatched_ids
    assert "CH*ABC*E5" in coordinator.unmatched_ids


@pytest.mark.asyncio
async def test_ecarup_fallback_failure_leaves_unknown(hass) -> None:
    """A failing eCarUp fallback never breaks the poll; states stay unknown."""
    master = {
        "CH*ECUE123": ChargingPoint(
            evse_id="CH*ECUE123", latitude=47.38, longitude=8.55
        ),
    }
    entry = _make_entry(hass, {CONF_PINNED_EVSE_IDS: ["CH*ECUE123"]})
    coordinator = SwissEvChargingCoordinator(hass, entry)

    with patch(
        "custom_components.swiss_ev_charging.coordinator.async_resolve_ecarup_states",
        side_effect=RuntimeError("boom"),
    ):
        data = await _run(hass, coordinator, master, {})

    assert data["CH*ECUE123"].state == STATE_UNKNOWN
    assert coordinator.ecarup_resolved_ids == []


@pytest.mark.asyncio
async def test_move_fallback_fills_unknown_states(hass) -> None:
    """A Move EVSE left unknown by SFOE is filled from the Move public API."""
    master = {
        "CH*CCI*E1": ChargingPoint(
            evse_id="CH*CCI*E1", latitude=47.38, longitude=8.55
        ),
        "CH*ABC*E5": ChargingPoint(evse_id="CH*ABC*E5", latitude=47.38, longitude=8.55),
    }
    status: dict[str, str] = {}
    entry = _make_entry(hass, {CONF_PINNED_EVSE_IDS: ["CH*CCI*E1", "CH*ABC*E5"]})
    coordinator = SwissEvChargingCoordinator(hass, entry)

    with patch(
        "custom_components.swiss_ev_charging.coordinator.async_resolve_move_states",
        return_value={"CH*CCI*E1": STATE_OCCUPIED},
    ) as resolver:
        data = await _run(hass, coordinator, master, status)

    # Only the Move EVSE (with coordinates) was offered to the resolver.
    targets = resolver.call_args.args[1]
    assert [t[0] for t in targets] == ["CH*CCI*E1"]

    assert data["CH*CCI*E1"].state == STATE_OCCUPIED  # filled from Move
    assert data["CH*ABC*E5"].state == STATE_UNKNOWN  # non-Move, still unknown
    assert coordinator.move_resolved_ids == ["CH*CCI*E1"]
    assert "CH*CCI*E1" not in coordinator.unmatched_ids
