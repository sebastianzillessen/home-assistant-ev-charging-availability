"""Tests for the availability sensor's map-marker rendering."""

from __future__ import annotations

from urllib.parse import unquote

import pytest

from custom_components.swiss_ev_charging.const import (
    MARKER_STYLE_DOT,
    MARKER_STYLE_GLYPH,
    MARKER_STYLE_PIP,
    STATE_AVAILABLE,
    STATE_MAINTENANCE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_RESERVED,
    STATE_UNKNOWN,
)
from custom_components.swiss_ev_charging.sensor import marker_picture

# A path fragment unique to each glyph, used to assert the right shape is drawn.
_PLUG = "M7.6 8.2"
_BOLT = "M13 3.8"
_SAND = "M8.6 6.4"
_WRENCH = "M15.9 5"
_POWER = "a5 5 0 1 0"
_QUEST = "a2.55 2.55"
_CHECK = "M7.8 12.2"
_CROSS = "M8.6 8.6"

_COLORS = {
    STATE_AVAILABLE: "#16a34a",
    STATE_OCCUPIED: "#dc2626",
    STATE_RESERVED: "#d97706",
    STATE_MAINTENANCE: "#7c3aed",
    STATE_OUT_OF_SERVICE: "#64748b",
    STATE_UNKNOWN: "#94a3b8",
}


def _svg(state: str, style: str) -> str:
    """Return the decoded SVG body of a marker data URI."""
    picture = marker_picture(state, style)
    assert picture.startswith("data:image/svg+xml,")
    return unquote(picture.split(",", 1)[1])


@pytest.mark.parametrize("style", [MARKER_STYLE_DOT, MARKER_STYLE_GLYPH, MARKER_STYLE_PIP])
@pytest.mark.parametrize("state, color", list(_COLORS.items()))
def test_marker_disc_is_state_coloured(style: str, state: str, color: str) -> None:
    """Every style draws the bordered, state-coloured disc."""
    svg = _svg(state, style)
    assert "<svg" in svg
    assert f"<circle cx='12' cy='12' r='11' fill='{color}'/>" in svg
    assert "stroke='#fff'" in svg  # white border


def test_dot_style_has_no_glyph() -> None:
    """The dot style is just the disc — no plug or state glyph."""
    svg = _svg(STATE_AVAILABLE, MARKER_STYLE_DOT)
    for fragment in (_PLUG, _BOLT, _CHECK):
        assert fragment not in svg


@pytest.mark.parametrize(
    "state, fragment",
    [
        (STATE_AVAILABLE, _PLUG),  # free shows the plug itself
        (STATE_OCCUPIED, _BOLT),
        (STATE_RESERVED, _SAND),
        (STATE_MAINTENANCE, _WRENCH),
        (STATE_OUT_OF_SERVICE, _POWER),
        (STATE_UNKNOWN, _QUEST),
    ],
)
def test_glyph_style_one_glyph_per_state(state: str, fragment: str) -> None:
    """The glyph style centres a distinct white glyph for each state."""
    assert fragment in _svg(state, MARKER_STYLE_GLYPH)


@pytest.mark.parametrize(
    "state, fragment",
    [
        (STATE_AVAILABLE, _CHECK),
        (STATE_OCCUPIED, _BOLT),
        (STATE_RESERVED, _SAND),
        (STATE_MAINTENANCE, _WRENCH),
        (STATE_OUT_OF_SERVICE, _CROSS),
        (STATE_UNKNOWN, _QUEST),
    ],
)
def test_pip_style_keeps_plug_and_adds_state_pip(state: str, fragment: str) -> None:
    """The pip style always shows the plug plus a per-state status pip."""
    svg = _svg(state, MARKER_STYLE_PIP)
    assert _PLUG in svg  # plug on every marker
    assert "cx='16.7'" in svg  # the white status pip
    assert fragment in svg


def test_unknown_and_unmapped_states_use_the_neutral_colour() -> None:
    """Unknown and any unexpected state fall back to the neutral colour + '?'."""
    for state in (STATE_UNKNOWN, "something-else"):
        svg = _svg(state, MARKER_STYLE_GLYPH)
        assert "#94a3b8" in svg
        assert _QUEST in svg


@pytest.mark.parametrize("style", [MARKER_STYLE_DOT, MARKER_STYLE_GLYPH, MARKER_STYLE_PIP])
def test_marker_picture_is_url_safe(style: str) -> None:
    """The data URI payload carries no raw spaces or angle brackets."""
    payload = marker_picture(STATE_OCCUPIED, style).split(",", 1)[1]
    assert " " not in payload
    assert "<" not in payload and ">" not in payload
