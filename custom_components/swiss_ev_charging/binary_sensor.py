"""'Is free' binary sensors for the Swiss EV Charging integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwissEvChargingConfigEntry
from .const import STATE_AVAILABLE
from .coordinator import SwissEvChargingCoordinator
from .entity import SwissEvChargingEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwissEvChargingConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one 'is free' binary sensor per tracked charging point."""
    coordinator = entry.runtime_data
    async_add_entities(
        SwissEvIsFreeBinarySensor(coordinator, evse_id)
        for evse_id in coordinator.data
    )


class SwissEvIsFreeBinarySensor(SwissEvChargingEntity, BinarySensorEntity):
    """Binary sensor that is on when the charging point is available (free)."""

    _attr_translation_key = "is_free"

    def __init__(
        self, coordinator: SwissEvChargingCoordinator, evse_id: str
    ) -> None:
        """Initialise the is-free binary sensor."""
        super().__init__(coordinator, evse_id)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{evse_id}_is_free"

    @property
    def is_on(self) -> bool | None:
        """Return True when the charging point is available."""
        tracked = self._tracked
        if tracked is None:
            return None
        return tracked.state == STATE_AVAILABLE

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the configured tag, if any."""
        if self.coordinator.tag:
            return {"tag": self.coordinator.tag}
        return {}
