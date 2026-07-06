"""Tests for the geoportal deep-link helper."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from custom_components.swiss_ev_charging.const import (
    GEOADMIN_LADESTELLEN_LAYER,
    ICH_TANKE_STROM_URL,
)
from custom_components.swiss_ev_charging.map_link import (
    station_map_url,
    wgs84_to_lv95,
)


def _hash_params(url: str) -> dict[str, str]:
    """Parse the query part of a geoportal ``#/map?...`` hash URL.

    Values are kept verbatim (``@``/``*``/``,`` are literal in the geoportal hash).
    """
    fragment = urlsplit(url).fragment  # e.g. "/map?center=...&z=13&..."
    query = fragment.split("?", 1)[1]
    return dict(part.split("=", 1) for part in query.split("&"))


def test_wgs84_to_lv95_bern_fundamental_point() -> None:
    """The Bern fundamental point maps to the LV95 origin (2600000, 1200000)."""
    easting, northing = wgs84_to_lv95(46.9510811, 7.4386372)
    assert easting == pytest.approx(2600000, abs=1.0)
    assert northing == pytest.approx(1200000, abs=1.0)


def test_station_map_url_uses_hash_routing_and_marks_the_point() -> None:
    """A station deep-links to the geoportal hash route, centred and marked."""
    url = station_map_url(47.3769, 8.5417)
    split = urlsplit(url)
    assert split.netloc == "map.geo.admin.ch"
    assert split.fragment.startswith("/map?")

    params = _hash_params(url)
    easting, northing = (float(v) for v in params["center"].split(","))
    assert 2_480_000 < easting < 2_840_000
    assert 1_070_000 < northing < 1_300_000
    assert params["crosshair"].startswith("marker,")
    assert params["layers"] == GEOADMIN_LADESTELLEN_LAYER


def test_station_map_url_preselects_the_evse_and_opens_info() -> None:
    """With an EvseID, the station is preselected and its info panel opened."""
    evse_id = "CH*ECU*EDR654CLPY9WN3HBTTGEYKFKTVS"
    url = station_map_url(47.3769, 8.5417, evse_id)
    params = _hash_params(url)
    assert params["layers"] == f"{GEOADMIN_LADESTELLEN_LAYER}@features={evse_id}"
    assert params["featureInfo"] == "bottomPanel"
    # The id must appear verbatim (not percent-encoded) in the hash.
    assert f"@features={evse_id}" in url


def test_station_map_url_without_coordinates_falls_back_to_homepage() -> None:
    """Missing coordinates fall back to the public homepage."""
    assert station_map_url(None, None) == ICH_TANKE_STROM_URL
    assert station_map_url(47.0, None) == ICH_TANKE_STROM_URL
    assert station_map_url(None, 8.0, "CH*ECU*E1") == ICH_TANKE_STROM_URL
