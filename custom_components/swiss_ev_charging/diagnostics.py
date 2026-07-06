"""Diagnostics support for the Swiss EV Charging integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import SwissEvChargingConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SwissEvChargingConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "options": dict(entry.options),
        "tracked_ids": coordinator.tracked_ids,
        "tracked": {
            evse_id: {
                "state": tracked.state,
                "distance_m": tracked.distance_m,
                "is_pinned": tracked.is_pinned,
                "point": asdict(tracked.point),
            }
            for evse_id, tracked in (coordinator.data or {}).items()
        },
    }
