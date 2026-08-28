"""Base entity for the Swiss EV Charging integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ChargingPoint
from .const import DOMAIN
from .coordinator import SwissEvChargingCoordinator, TrackedEvse
from .map_link import station_map_url


def _format_power(kw: float) -> str:
    """Render a power in kW without a trailing ``.0`` (e.g. ``"224 kW"``)."""
    return f"{kw:g} kW"


def _device_name(coordinator: SwissEvChargingCoordinator, point: ChargingPoint) -> str:
    """Device name, optionally suffixed with the rated power for map labels."""
    base = point.name or point.evse_id
    if coordinator.name_with_power and point.max_power_kw is not None:
        return f"{base} · {_format_power(point.max_power_kw)}"
    return base


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
            name=_device_name(coordinator, point),
            manufacturer=point.operator or "ich-tanke-strom",
            model="EV charging point",
            configuration_url=station_map_url(
                point.latitude, point.longitude, evse_id
            ),
        )

    @property
    def _tracked(self) -> TrackedEvse | None:
        """Return the current tracked record for this EVSE, if present."""
        return self.coordinator.data.get(self._evse_id)

    @property
    def available(self) -> bool:
        """Entity is available when the coordinator has data for this EVSE."""
        return super().available and self._tracked is not None
