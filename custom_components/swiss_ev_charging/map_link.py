"""Build a deep link to a charging station on the Swiss geoportal map.

The device's ``configuration_url`` points at ``map.geo.admin.ch`` centred and
zoomed on the station, with a crosshair marker and the official charging-station
layer enabled. The geoportal centres the map in LV95 (EPSG:2056) easting/northing,
so the station's WGS84 coordinates are converted first.
"""

from __future__ import annotations

from urllib.parse import urlencode

from .const import (
    GEOADMIN_LADESTELLEN_LAYER,
    GEOADMIN_MAP_URL,
    GEOADMIN_MAP_ZOOM,
    ICH_TANKE_STROM_URL,
)


def wgs84_to_lv95(latitude: float, longitude: float) -> tuple[float, float]:
    """Convert WGS84 lat/lon (degrees) to LV95 easting/northing (metres).

    Uses swisstopo's published approximate formula, which is accurate to well
    under a metre across Switzerland — far more than enough to drop a map marker.
    """
    # Latitude/longitude in sexagesimal seconds, expressed as offsets from Bern
    # in units of 10000 seconds.
    phi = (latitude * 3600.0 - 169028.66) / 10000.0
    lam = (longitude * 3600.0 - 26782.5) / 10000.0

    easting = (
        2600072.37
        + 211455.93 * lam
        - 10938.51 * lam * phi
        - 0.36 * lam * phi**2
        - 44.54 * lam**3
    )
    northing = (
        1200147.07
        + 308807.95 * phi
        + 3745.25 * lam**2
        + 76.63 * phi**2
        - 194.56 * lam**2 * phi
        + 119.79 * phi**3
    )
    return easting, northing


def station_map_url(
    latitude: float | None, longitude: float | None
) -> str:
    """Return a geoportal deep link centred on the station, or the homepage.

    When coordinates are unknown, fall back to the ich-tanke-strom homepage so the
    device link is always useful.
    """
    if latitude is None or longitude is None:
        return ICH_TANKE_STROM_URL

    easting, northing = wgs84_to_lv95(latitude, longitude)
    query = urlencode(
        {
            "center": f"{easting:.0f},{northing:.0f}",
            "z": GEOADMIN_MAP_ZOOM,
            "crosshair": "marker",
            "layers": GEOADMIN_LADESTELLEN_LAYER,
        }
    )
    return f"{GEOADMIN_MAP_URL}?{query}"
