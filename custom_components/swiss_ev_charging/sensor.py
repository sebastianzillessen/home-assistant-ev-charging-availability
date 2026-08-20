"""Availability sensors for the Swiss EV Charging integration."""

from __future__ import annotations

from urllib.parse import quote

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwissEvChargingConfigEntry
from .const import (
    AVAILABILITY_STATES,
    MARKER_STYLE_GLYPH,
    MARKER_STYLE_OFF,
    MARKER_STYLE_PIP,
    STATE_AVAILABLE,
    STATE_MAINTENANCE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_RESERVED,
)
from .coordinator import SwissEvChargingCoordinator
from .entity import SwissEvChargingEntity

# Map-marker rendering. Home Assistant masks ``entity_picture`` to a circle, so
# every marker is a state-coloured disc with a white border. Three styles build
# on that: a plain ``dot``; a ``glyph`` (one white glyph per state, centred); and
# a ``pip`` (a white plug — charger identity — plus a small status pip whose own
# glyph encodes the state). The glyph/pip styles distinguish states by shape as
# well as colour, so they stay legible in greyscale / red-green colour blindness.
_MARKER_COLORS: dict[str, str] = {
    STATE_AVAILABLE: "#16a34a",
    STATE_OCCUPIED: "#dc2626",
    STATE_RESERVED: "#d97706",
    STATE_MAINTENANCE: "#7c3aed",
    STATE_OUT_OF_SERVICE: "#64748b",
}
_MARKER_COLOR_UNKNOWN = "#94a3b8"

# Glyph library, each authored in the 24x24 box centred on (12,12). ``{c}`` is
# the paint colour, so the same path serves a white glyph or a tinted pip.
_SYM: dict[str, str] = {
    "plug": (
        "<g fill='{c}'>"
        "<rect x='9' y='4.6' width='1.8' height='3.6' rx='.9'/>"
        "<rect x='13.2' y='4.6' width='1.8' height='3.6' rx='.9'/>"
        "<path d='M7.6 8.2 h8.8 v2.3 a4.4 4.4 0 0 1 -8.8 0 z'/>"
        "<rect x='11.1' y='14.4' width='1.8' height='4.9' rx='.9'/></g>"
    ),
    "bolt": "<path fill='{c}' d='M13 3.8 L7 13 H11 L10.3 20.2 L17.2 10.8 H12.6 Z'/>",
    "sand": (
        "<g fill='{c}'>"
        "<rect x='7.4' y='4.6' width='9.2' height='1.8' rx='.9'/>"
        "<rect x='7.4' y='17.6' width='9.2' height='1.8' rx='.9'/>"
        "<path d='M8.6 6.4 h6.8 L12 12 z'/><path d='M8.6 17.6 h6.8 L12 12 z'/></g>"
    ),
    "wrench": (
        "<path fill='{c}' d='M15.9 5 a3.5 3.5 0 0 0 -4.5 4.4 L5.5 15.4 l1.75 1.75 "
        "5.9-5.9 a3.5 3.5 0 0 0 4.4-4.5 l-2.25 2.25 -1.5 -1.5 z'/>"
    ),
    "power": (
        "<g fill='none' stroke='{c}' stroke-width='2' stroke-linecap='round'>"
        "<path d='M12 4.8 V11'/><path d='M8.2 7.1 a5 5 0 1 0 7.6 0'/></g>"
    ),
    "quest": (
        "<g fill='none' stroke='{c}' stroke-width='2' stroke-linecap='round'>"
        "<path d='M9.5 9.3 a2.55 2.55 0 1 1 3.35 2.45 c-.95 .38 -1.4 .95 -1.4 2'/></g>"
        "<circle cx='11.45' cy='16.7' r='1.15' fill='{c}'/>"
    ),
    "check": (
        "<path fill='none' stroke='{c}' stroke-width='2.2' stroke-linecap='round' "
        "stroke-linejoin='round' d='M7.8 12.2 l2.7 2.7 L16.2 8.5'/>"
    ),
    "cross": (
        "<path fill='none' stroke='{c}' stroke-width='2.2' stroke-linecap='round' "
        "d='M8.6 8.6 L15.4 15.4 M15.4 8.6 L8.6 15.4'/>"
    ),
}

# ``glyph`` style: one centred white glyph per state (plug = free / charger).
_GLYPH_STATE: dict[str, str] = {
    STATE_AVAILABLE: "plug",
    STATE_OCCUPIED: "bolt",
    STATE_RESERVED: "sand",
    STATE_MAINTENANCE: "wrench",
    STATE_OUT_OF_SERVICE: "power",
}
# ``pip`` style: the plug stays; a small corner pip carries the state glyph.
_PIP_STATE: dict[str, str] = {
    STATE_AVAILABLE: "check",
    STATE_OCCUPIED: "bolt",
    STATE_RESERVED: "sand",
    STATE_MAINTENANCE: "wrench",
    STATE_OUT_OF_SERVICE: "cross",
}
_GLYPH_UNKNOWN = "quest"

# Transforms: plug up-left, status pip down-right (``pip`` style).
_PLUG_TF = "translate(0.8 0.8) scale(0.8)"
_PIP_TF = "translate(11.66 11.66) scale(0.42)"


def _svg(inner: str) -> str:
    """Wrap marker ``inner`` in a 24x24 SVG and return it as a ``data:`` URI."""
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' "
        f"viewBox='0 0 24 24'>{inner}</svg>"
    )
    return "data:image/svg+xml," + quote(svg)


def _disc(color: str) -> str:
    """The state-coloured disc with a white border, shared by every style."""
    return (
        f"<circle cx='12' cy='12' r='11' fill='{color}'/>"
        "<circle cx='12' cy='12' r='11' fill='none' stroke='#fff' stroke-width='1.6'/>"
    )


def marker_picture(state: str | None, style: str) -> str:
    """Return a ``data:`` URI marker for ``state`` rendered in ``style``."""
    color = _MARKER_COLORS.get(state, _MARKER_COLOR_UNKNOWN)
    if style == MARKER_STYLE_GLYPH:
        name = _GLYPH_STATE.get(state, _GLYPH_UNKNOWN)
        return _svg(_disc(color) + _SYM[name].format(c="#fff"))
    if style == MARKER_STYLE_PIP:
        pip_name = _PIP_STATE.get(state, _GLYPH_UNKNOWN)
        return _svg(
            _disc(color)
            + f"<g transform='{_PLUG_TF}'>{_SYM['plug'].format(c='#fff')}</g>"
            + "<circle cx='16.7' cy='16.7' r='5.5' fill='#fff'/>"
            + "<circle cx='16.7' cy='16.7' r='5.5' fill='none' "
            "stroke='rgba(0,0,0,0.12)' stroke-width='1'/>"
            + f"<g transform='{_PIP_TF}'>{_SYM[pip_name].format(c=color)}</g>"
        )
    # MARKER_STYLE_DOT (and any unknown style): the plain bordered disc.
    return _svg(_disc(color))


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
        """Colour the map marker by availability, per the selected style.

        A HA map marker shows the entity's ``entity_picture``; returning a
        state-coloured badge here paints the marker (and, unavoidably, the
        entity's icon elsewhere). ``off`` by default so the normal icon is kept.
        """
        tracked = self._tracked
        style = self.coordinator.map_marker_style
        if tracked is None or style == MARKER_STYLE_OFF:
            return None
        return marker_picture(tracked.state, style)

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
