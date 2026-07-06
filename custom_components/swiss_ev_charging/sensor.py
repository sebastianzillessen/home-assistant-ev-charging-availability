"""Availability sensors for the Swiss EV Charging integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwissEvChargingConfigEntry
from .const import AVAILABILITY_STATES
from .coordinator import SwissEvChargingCoordinator
from .entity import SwissEvChargingEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwissEvChargingConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one availability sensor per tracked charging point."""
    coordinator = entry.runtime_data
    async_add_entities(
        SwissEvAvailabilitySensor(coordinator, evse_id)
        for evse_id in coordinator.data
    )


class SwissEvAvailabilitySensor(SwissEvChargingEntity, SensorEntity):
    """Enum sensor exposing the live availability of a charging point."""

    _attr_translation_key = "availability"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = AVAILABILITY_STATES

    def __init__(
        self, coordinator: SwissEvChargingCoordinator, evse_id: str
    ) -> None:
        """Initialise the availability sensor."""
        super().__init__(coordinator, evse_id)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{evse_id}"

    @property
    def native_value(self) -> str | None:
        """Return the normalised availability state."""
        tracked = self._tracked
        return tracked.state if tracked else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose master data and distance as attributes."""
        tracked = self._tracked
        if tracked is None:
            return {}
        point = tracked.point
        distance_km = (
            round(tracked.distance_m / 1000, 3)
            if tracked.distance_m is not None
            else None
        )
        return {
            "evse_id": point.evse_id,
            "operator": point.operator,
            "plug_types": point.plugs,
            "max_power_kw": point.max_power_kw,
            "distance_km": distance_km,
            "address": point.address,
            "latitude": point.latitude,
            "longitude": point.longitude,
            "is_pinned": tracked.is_pinned,
        }
