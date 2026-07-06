"""Config and options flow for the Swiss EV Charging integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAX_STATIONS,
    CONF_MIN_POWER,
    CONF_NOTIFY_ON_AVAILABLE,
    CONF_NOTIFY_SERVICE,
    CONF_PINNED_EVSE_IDS,
    CONF_PLUG_TYPES,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_TAG,
    DEFAULT_MAX_STATIONS,
    DEFAULT_MIN_POWER,
    DEFAULT_NOTIFY_ON_AVAILABLE,
    DEFAULT_RADIUS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)


def _clean_id_list(raw: Any) -> list[str]:
    """Normalise a comma/newline separated string (or list) into EVSE IDs."""
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        items = raw.replace("\n", ",").split(",")
    else:
        items = []
    return [item.strip() for item in items if item and item.strip()]


def _clean_plug_list(raw: Any) -> list[str]:
    """Normalise a comma separated plug-type filter into a list."""
    return _clean_id_list(raw)


def _notify_service_selector(hass: HomeAssistant, current: str) -> SelectSelector:
    """Build a dropdown of the currently registered ``notify.*`` services.

    ``custom_value`` keeps free-text entry possible (e.g. a service that is not
    loaded yet, or ``persistent_notification.create``); leaving it blank uses the
    persistent-notification fallback.
    """
    options = sorted(
        f"notify.{service}"
        for service in hass.services.async_services().get("notify", {})
    )
    # Keep an existing custom value selectable even if it is not a notify.* service.
    if current and current not in options:
        options.append(current)
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            mode=SelectSelectorMode.DROPDOWN,
            custom_value=True,
            sort=True,
        )
    )


class SwissEvChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial UI configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the location, tracking and polling settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pinned = _clean_id_list(user_input.get(CONF_PINNED_EVSE_IDS, ""))
            has_location = (
                user_input.get(CONF_LATITUDE) is not None
                and user_input.get(CONF_LONGITUDE) is not None
            )
            if not has_location and not pinned:
                # Nothing would be tracked without either an origin or pinned IDs.
                errors["base"] = "no_selection"
            else:
                data = {
                    CONF_LATITUDE: user_input.get(CONF_LATITUDE),
                    CONF_LONGITUDE: user_input.get(CONF_LONGITUDE),
                    CONF_RADIUS: user_input.get(CONF_RADIUS, DEFAULT_RADIUS),
                    CONF_MAX_STATIONS: user_input.get(
                        CONF_MAX_STATIONS, DEFAULT_MAX_STATIONS
                    ),
                    CONF_MIN_POWER: user_input.get(CONF_MIN_POWER, DEFAULT_MIN_POWER),
                    CONF_PLUG_TYPES: _clean_plug_list(
                        user_input.get(CONF_PLUG_TYPES, "")
                    ),
                    CONF_PINNED_EVSE_IDS: pinned,
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                    CONF_TAG: (user_input.get(CONF_TAG) or "").strip(),
                    CONF_NOTIFY_ON_AVAILABLE: user_input.get(
                        CONF_NOTIFY_ON_AVAILABLE, DEFAULT_NOTIFY_ON_AVAILABLE
                    ),
                    CONF_NOTIFY_SERVICE: (
                        user_input.get(CONF_NOTIFY_SERVICE) or ""
                    ).strip(),
                }
                return self.async_create_entry(
                    title="Swiss EV Charging", data=data
                )

        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude
        schema = vol.Schema(
            {
                # Location is optional (pinned-only setups clear it), so allow None.
                vol.Optional(CONF_LATITUDE, default=home_lat): vol.Any(None, cv.latitude),
                vol.Optional(CONF_LONGITUDE, default=home_lon): vol.Any(
                    None, cv.longitude
                ),
                vol.Optional(CONF_RADIUS, default=DEFAULT_RADIUS): vol.All(
                    vol.Coerce(int), vol.Range(min=0)
                ),
                vol.Optional(
                    CONF_MAX_STATIONS, default=DEFAULT_MAX_STATIONS
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=50)),
                vol.Optional(CONF_MIN_POWER, default=DEFAULT_MIN_POWER): vol.All(
                    vol.Coerce(float), vol.Range(min=0)
                ),
                vol.Optional(CONF_PLUG_TYPES, default=""): str,
                vol.Optional(CONF_PINNED_EVSE_IDS, default=""): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                vol.Optional(CONF_TAG, default=""): str,
                vol.Optional(
                    CONF_NOTIFY_ON_AVAILABLE, default=DEFAULT_NOTIFY_ON_AVAILABLE
                ): bool,
                vol.Optional(
                    CONF_NOTIFY_SERVICE, default=""
                ): _notify_service_selector(self.hass, ""),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> SwissEvChargingOptionsFlow:
        """Return the options flow handler."""
        return SwissEvChargingOptionsFlow()


class SwissEvChargingOptionsFlow(OptionsFlow):
    """Allow editing the tracking and polling settings after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and persist the editable options."""
        if user_input is not None:
            options = {
                CONF_RADIUS: user_input.get(CONF_RADIUS, DEFAULT_RADIUS),
                CONF_MAX_STATIONS: user_input.get(
                    CONF_MAX_STATIONS, DEFAULT_MAX_STATIONS
                ),
                CONF_MIN_POWER: user_input.get(CONF_MIN_POWER, DEFAULT_MIN_POWER),
                CONF_PLUG_TYPES: _clean_plug_list(user_input.get(CONF_PLUG_TYPES, "")),
                CONF_PINNED_EVSE_IDS: _clean_id_list(
                    user_input.get(CONF_PINNED_EVSE_IDS, "")
                ),
                CONF_SCAN_INTERVAL: user_input.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
                CONF_TAG: (user_input.get(CONF_TAG) or "").strip(),
                CONF_NOTIFY_ON_AVAILABLE: user_input.get(
                    CONF_NOTIFY_ON_AVAILABLE, DEFAULT_NOTIFY_ON_AVAILABLE
                ),
                CONF_NOTIFY_SERVICE: (user_input.get(CONF_NOTIFY_SERVICE) or "").strip(),
            }
            return self.async_create_entry(title="", data=options)

        data = self.config_entry.data
        options = self.config_entry.options
        current = {**data, **options}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_RADIUS, default=current.get(CONF_RADIUS, DEFAULT_RADIUS)
                ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                vol.Optional(
                    CONF_MAX_STATIONS,
                    default=current.get(CONF_MAX_STATIONS, DEFAULT_MAX_STATIONS),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=50)),
                vol.Optional(
                    CONF_MIN_POWER,
                    default=current.get(CONF_MIN_POWER, DEFAULT_MIN_POWER),
                ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Optional(
                    CONF_PLUG_TYPES,
                    default=", ".join(current.get(CONF_PLUG_TYPES, []) or []),
                ): str,
                vol.Optional(
                    CONF_PINNED_EVSE_IDS,
                    default=", ".join(current.get(CONF_PINNED_EVSE_IDS, []) or []),
                ): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                vol.Optional(
                    CONF_TAG, default=current.get(CONF_TAG, "") or ""
                ): str,
                vol.Optional(
                    CONF_NOTIFY_ON_AVAILABLE,
                    default=current.get(
                        CONF_NOTIFY_ON_AVAILABLE, DEFAULT_NOTIFY_ON_AVAILABLE
                    ),
                ): bool,
                vol.Optional(
                    CONF_NOTIFY_SERVICE,
                    default=current.get(CONF_NOTIFY_SERVICE, "") or "",
                ): _notify_service_selector(
                    self.hass, current.get(CONF_NOTIFY_SERVICE, "") or ""
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
