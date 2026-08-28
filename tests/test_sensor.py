"""Tests for the availability sensor's map-marker rendering."""

from __future__ import annotations

from urllib.parse import unquote

import pytest

from custom_components.swiss_ev_charging.const import (
    MARKER_STYLE_DOT,
    MARKER_STYLE_GLYPH,
    MARKER_STYLE_PIP,
    POWER_TIER_FAST,
    POWER_TIER_STANDARD,
    POWER_TIER_ULTRA,
    STATE_AVAILABLE,
    STATE_MAINTENANCE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_RESERVED,
    STATE_UNKNOWN,
)
from custom_components.swiss_ev_charging.sensor import (
    format_connector,
    marker_picture,
    power_tier,
)

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


@pytest.mark.parametrize(
    "kw, tier",
    [
        (None, POWER_TIER_STANDARD),
        (3.7, POWER_TIER_STANDARD),
        (22.0, POWER_TIER_STANDARD),
        (49.9, POWER_TIER_STANDARD),
        (50.0, POWER_TIER_FAST),
        (149.0, POWER_TIER_FAST),
        (150.0, POWER_TIER_ULTRA),
        (350.0, POWER_TIER_ULTRA),
    ],
)
def test_power_tier_thresholds(kw: float | None, tier: str) -> None:
    """Power classifies into standard (<50), fast (50-149), ultra (>=150)."""
    assert power_tier(kw) == tier


def test_marker_tier_ring_present_only_for_fast_and_ultra() -> None:
    """The tier ring is drawn for fast/ultra chargers and absent for standard."""
    standard = _svg_of(STATE_AVAILABLE, MARKER_STYLE_DOT, POWER_TIER_STANDARD)
    fast = _svg_of(STATE_AVAILABLE, MARKER_STYLE_DOT, POWER_TIER_FAST)
    ultra = _svg_of(STATE_AVAILABLE, MARKER_STYLE_DOT, POWER_TIER_ULTRA)
    # The enlarged viewBox leaves room for the outer ring(s).
    assert "viewBox='-2 -2 28 28'" in standard
    assert "r='12.7'" not in standard  # no ring
    assert standard.count("r='12.7'") == 0
    assert fast.count("r='12.7'") == 2  # one white ring + its dark hairline
    assert "r='14.4'" not in fast
    assert ultra.count("r='12.7'") == 2 and ultra.count("r='14.4'") == 2  # two rings


def _svg_of(state: str, style: str, tier: str) -> str:
    """Decoded SVG body of a tiered marker."""
    return unquote(marker_picture(state, style, tier).split(",", 1)[1])


@pytest.mark.parametrize(
    "plugs, power_type, expected",
    [
        (["CCS Combo 2 Plug (Cable Attached)"], "DC", "CCS Combo 2 · DC"),
        (["Type 2 Outlet"], "AC_3_PHASE", "Type 2 · AC 3-phase"),
        (["CHAdeMO"], "DC", "CHAdeMO · DC"),
        (["Type 2 Outlet", "Type 2 Connector (Cable Attached)"], None, "Type 2"),
        ([], None, None),
        ([], "DC", "DC"),
    ],
)
def test_format_connector(
    plugs: list[str], power_type: str | None, expected: str | None
) -> None:
    """Connector label shortens plug strings, de-dupes, and appends AC/DC."""
    assert format_connector(plugs, power_type) == expected
