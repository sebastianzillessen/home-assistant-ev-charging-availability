"""Base entity for the Swiss EV Charging integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SwissEvChargingCoordinator, TrackedEvse


class SwissEvChargingEntity(CoordinatorEntity[SwissEvChargingCoordinator]):
    """Base entity tied to a single tracked EVSE (charging point)."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SwissEvChargingCoordinator, evse_id: str
    ) -> None:
        """Initialise for a specific EVSE ID."""
        super().__init__(coordinator)
        self._evse_id = evse_id
        point = coordinator.data[evse_id].point
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, evse_id)},
            name=point.name or evse_id,
            manufacturer=point.operator or "ich-tanke-strom",
            model="EV charging point",
            configuration_url="https://www.ich-tanke-strom.ch",
        )

    @property
    def _tracked(self) -> TrackedEvse | None:
        """Return the current tracked record for this EVSE, if present."""
        return self.coordinator.data.get(self._evse_id)

    @property
    def available(self) -> bool:
        """Entity is available when the coordinator has data for this EVSE."""
        return super().available and self._tracked is not None
