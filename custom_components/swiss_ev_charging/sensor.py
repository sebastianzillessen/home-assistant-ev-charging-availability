"""Availability sensors for the Swiss EV Charging integration."""

from __future__ import annotations

from urllib.parse import quote

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwissEvChargingConfigEntry
from .const import (
    AVAILABILITY_STATES,
    STATE_AVAILABLE,
    STATE_MAINTENANCE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_RESERVED,
)
from .coordinator import SwissEvChargingCoordinator
from .entity import SwissEvChargingEntity

# Marker colour per availability state, used when the user opts into colouring
# map markers by availability. Named CSS colours keep the SVG data URI free of
# the ``#`` that would otherwise be read as a URI fragment.
_MARKER_COLORS: dict[str, str] = {
    STATE_AVAILABLE: "limegreen",
    STATE_OCCUPIED: "red",
    STATE_RESERVED: "orange",
    STATE_OUT_OF_SERVICE: "gray",
    STATE_MAINTENANCE: "mediumpurple",
}
_MARKER_COLOR_UNKNOWN = "lightgray"


def marker_picture(state: str | None) -> str:
    """Return a ``data:`` URI of a coloured dot for an availability ``state``."""
    color = _MARKER_COLORS.get(state, _MARKER_COLOR_UNKNOWN)
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24'>"
        f"<circle cx='12' cy='12' r='11' fill='{color}'/></svg>"
    )
    return "data:image/svg+xml," + quote(svg)


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
    def entity_picture(self) -> str | None:
        """Colour the map marker by availability, when the option is enabled.

        A HA map marker shows the entity's ``entity_picture``; returning a
        state-coloured dot here paints the marker (and, unavoidably, the entity's
        icon elsewhere). Disabled by default so the normal icon is kept.
        """
        tracked = self._tracked
        if tracked is None or not self.coordinator.color_map_markers:
            return None
        return marker_picture(tracked.state)

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
        attributes = {
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
        if self.coordinator.tag:
            attributes["tag"] = self.coordinator.tag
        return attributes
