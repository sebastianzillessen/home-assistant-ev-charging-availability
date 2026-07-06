"""Tests for the geoportal deep-link helper."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from custom_components.swiss_ev_charging.const import (
    GEOADMIN_LADESTELLEN_LAYER,
    ICH_TANKE_STROM_URL,
)
from custom_components.swiss_ev_charging.map_link import (
    station_map_url,
    wgs84_to_lv95,
)


def test_wgs84_to_lv95_bern_fundamental_point() -> None:
    """The Bern fundamental point maps to the LV95 origin (2600000, 1200000)."""
    easting, northing = wgs84_to_lv95(46.9510811, 7.4386372)
    assert easting == pytest.approx(2600000, abs=1.0)
    assert northing == pytest.approx(1200000, abs=1.0)


def test_station_map_url_deep_links_to_the_station() -> None:
    """A station with coordinates deep-links to the geoportal, marked and zoomed."""
    url = station_map_url(47.3769, 8.5417)
    parsed = urlparse(url)
    assert parsed.netloc == "map.geo.admin.ch"

    params = parse_qs(parsed.query)
    # Centre is LV95 easting,northing near Zurich (E ~2.68M, N ~1.25M).
    easting, northing = (float(v) for v in params["center"][0].split(","))
    assert 2_480_000 < easting < 2_840_000
    assert 1_070_000 < northing < 1_300_000
    assert params["crosshair"] == ["marker"]
    assert params["layers"] == [GEOADMIN_LADESTELLEN_LAYER]
    assert "z" in params


def test_station_map_url_without_coordinates_falls_back_to_homepage() -> None:
    """Missing coordinates fall back to the public homepage."""
    assert station_map_url(None, None) == ICH_TANKE_STROM_URL
    assert station_map_url(47.0, None) == ICH_TANKE_STROM_URL
    assert station_map_url(None, 8.0) == ICH_TANKE_STROM_URL
