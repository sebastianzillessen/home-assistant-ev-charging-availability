"""Tests for the availability sensor's map-marker colouring helper."""

from __future__ import annotations

from urllib.parse import unquote

from custom_components.swiss_ev_charging.const import (
    STATE_AVAILABLE,
    STATE_MAINTENANCE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_RESERVED,
    STATE_UNKNOWN,
)
from custom_components.swiss_ev_charging.sensor import marker_picture


def test_marker_picture_is_a_coloured_svg_data_uri() -> None:
    """The marker is an inline SVG data URI: a coloured disc with a bolt glyph."""
    picture = marker_picture(STATE_AVAILABLE)
    assert picture.startswith("data:image/svg+xml,")
    svg = unquote(picture.split(",", 1)[1])
    assert "<svg" in svg and "circle" in svg
    assert "fill='#16a34a'" in svg  # available colour
    assert "M13 2 L6 13" in svg  # the white lightning glyph


def test_marker_picture_colour_per_state() -> None:
    """Each availability state maps to its own marker colour."""
    colors = {
        STATE_AVAILABLE: "#16a34a",
        STATE_OCCUPIED: "#dc2626",
        STATE_RESERVED: "#d97706",
        STATE_OUT_OF_SERVICE: "#64748b",
        STATE_MAINTENANCE: "#7c3aed",
    }
    for state, color in colors.items():
        assert f"fill='{color}'" in unquote(marker_picture(state))
    # Unknown / unmapped states fall back to a neutral colour.
    assert "fill='#94a3b8'" in unquote(marker_picture(STATE_UNKNOWN))
    assert "fill='#94a3b8'" in unquote(marker_picture("something-else"))


def test_marker_picture_is_url_safe() -> None:
    """The data URI is percent-encoded, so it carries no raw spaces or angle brackets."""
    picture = marker_picture(STATE_OCCUPIED)
    payload = picture.split(",", 1)[1]
    assert " " not in payload
    assert "<" not in payload and ">" not in payload
