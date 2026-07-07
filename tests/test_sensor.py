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
    """The marker is an inline SVG data URI with a state-dependent fill colour."""
    picture = marker_picture(STATE_AVAILABLE)
    assert picture.startswith("data:image/svg+xml,")
    svg = unquote(picture.split(",", 1)[1])
    assert "<svg" in svg and "circle" in svg
    assert "fill='limegreen'" in svg


def test_marker_picture_colour_per_state() -> None:
    """Each availability state maps to its own marker colour."""
    colors = {
        STATE_AVAILABLE: "limegreen",
        STATE_OCCUPIED: "red",
        STATE_RESERVED: "orange",
        STATE_OUT_OF_SERVICE: "gray",
        STATE_MAINTENANCE: "mediumpurple",
    }
    for state, color in colors.items():
        assert f"fill='{color}'" in unquote(marker_picture(state))
    # Unknown / unmapped states fall back to a neutral colour.
    assert "fill='lightgray'" in unquote(marker_picture(STATE_UNKNOWN))
    assert "fill='lightgray'" in unquote(marker_picture("something-else"))


def test_marker_picture_is_url_safe() -> None:
    """The data URI is percent-encoded, so it carries no raw spaces or angle brackets."""
    picture = marker_picture(STATE_OCCUPIED)
    payload = picture.split(",", 1)[1]
    assert " " not in payload
    assert "<" not in payload and ">" not in payload
