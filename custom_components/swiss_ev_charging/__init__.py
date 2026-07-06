"""The Swiss EV Charging (ich-tanke-strom) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import SwissEvChargingCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

type SwissEvChargingConfigEntry = ConfigEntry[SwissEvChargingCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: SwissEvChargingConfigEntry
) -> bool:
    """Set up Swiss EV Charging from a config entry."""
    coordinator = SwissEvChargingCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SwissEvChargingConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: SwissEvChargingConfigEntry
) -> None:
    """Reload the entry when options change so new selection/interval applies."""
    await hass.config_entries.async_reload(entry.entry_id)
