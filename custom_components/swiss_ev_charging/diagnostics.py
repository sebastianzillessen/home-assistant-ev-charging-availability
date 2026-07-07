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
        # How many EVSEs the live-status feed carried, and which tracked stations
        # were absent from it (these surface as ``unknown``).
        "status_feed_size": coordinator.status_feed_size,
        "unmatched_ids": coordinator.unmatched_ids,
        # EVSEs the SFOE feed left unknown that were filled from an operator's
        # own public API.
        "ecarup_resolved_ids": coordinator.ecarup_resolved_ids,
        "move_resolved_ids": coordinator.move_resolved_ids,
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
