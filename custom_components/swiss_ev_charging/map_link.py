"""Build a deep link to a charging station on the Swiss geoportal map.

The device's ``configuration_url`` opens ``map.geo.admin.ch`` centred and zoomed
on the station, with a crosshair marker, the official charging-station layer, and
- when the EVSE id is known - the station preselected with its info panel open.

The current geoportal viewer is a single-page app that reads its state from the
URL *hash* (``#/map?...``) and centres the map in LV95 (EPSG:2056) easting/
northing, so the station's WGS84 coordinates are converted first.
"""

from __future__ import annotations

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
    latitude: float | None,
    longitude: float | None,
    evse_id: str | None = None,
) -> str:
    """Return a geoportal deep link centred on the station, or the homepage.

    When coordinates are unknown, fall back to the ich-tanke-strom homepage so the
    device link is always useful. When the EVSE id is known it is used to
    preselect the station and open its feature-info panel.

    The geoportal reads these values from the URL hash and does not expect them
    percent-encoded (``*``/``,``/``@`` appear literally), so the query is built by
    hand rather than via ``urlencode``.
    """
    if latitude is None or longitude is None:
        return ICH_TANKE_STROM_URL

    easting, northing = wgs84_to_lv95(latitude, longitude)
    center = f"{easting:.2f},{northing:.2f}"
    marker = f"marker,{easting:.0f},{northing:.0f}"
    layers = GEOADMIN_LADESTELLEN_LAYER

    params = [
        f"center={center}",
        f"z={GEOADMIN_MAP_ZOOM}",
        f"crosshair={marker}",
    ]
    if evse_id:
        layers = f"{layers}@features={evse_id}"
    params.append(f"layers={layers}")
    if evse_id:
        params.append("featureInfo=bottomPanel")

    return f"{GEOADMIN_MAP_URL}#/map?" + "&".join(params)
