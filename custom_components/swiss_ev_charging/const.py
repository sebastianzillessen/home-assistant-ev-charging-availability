"""Constants for the Swiss EV Charging integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "swiss_ev_charging"

# Public SFOE / ich-tanke-strom open-data endpoints (OICP 2.3, no key required).
# EVSEData holds static master data (location, operator, plugs, power).
# EVSEStatus holds live availability per charging point (EVSE).
EVSE_DATA_URL: Final = (
    "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet"
    "/data/oicp/ch.bfe.ladestellen-elektromobilitaet.json"
)
EVSE_STATUS_URL: Final = (
    "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet"
    "/status/oicp/ch.bfe.ladestellen-elektromobilitaet.json"
)

# Public homepage, used as the device link when a station has no coordinates.
ICH_TANKE_STROM_URL: Final = "https://www.ich-tanke-strom.ch"

# Swiss federal geoportal map viewer and the charging-stations layer. A device's
# configuration URL deep-links here, centred and zoomed on the station.
GEOADMIN_MAP_URL: Final = "https://map.geo.admin.ch/"
GEOADMIN_LADESTELLEN_LAYER: Final = "ch.bfe.ladestellen-elektromobilitaet"
# Zoom level for the deep link: high enough to show the individual station.
GEOADMIN_MAP_ZOOM: Final = 13

# Configuration / options keys.
CONF_LATITUDE: Final = "latitude"
CONF_LONGITUDE: Final = "longitude"
CONF_RADIUS: Final = "radius"
CONF_MAX_STATIONS: Final = "max_stations"
CONF_PINNED_EVSE_IDS: Final = "pinned_evse_ids"
CONF_MIN_POWER: Final = "min_power"
CONF_PLUG_TYPES: Final = "plug_types"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_TAG: Final = "tag"
CONF_NOTIFY_ON_AVAILABLE: Final = "notify_on_available"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_COLOR_MAP_MARKERS: Final = "color_map_markers"

# Defaults.
DEFAULT_RADIUS: Final = 1000  # metres
DEFAULT_MAX_STATIONS: Final = 5
DEFAULT_MIN_POWER: Final = 0.0  # kW, 0 = no filter
DEFAULT_SCAN_INTERVAL: Final = 180  # seconds (3 minutes)
MIN_SCAN_INTERVAL: Final = 60  # seconds, be respectful of the public endpoint

DEFAULT_NOTIFY_ON_AVAILABLE: Final = False
DEFAULT_COLOR_MAP_MARKERS: Final = False

# Master (static) data is large and rarely changes; refresh it infrequently.
MASTER_REFRESH_INTERVAL: Final = timedelta(hours=24)

# Normalised availability states. These double as the ENUM sensor options, which
# lets Home Assistant record long-term statistics for occupancy analysis.
STATE_AVAILABLE: Final = "available"
STATE_OCCUPIED: Final = "occupied"
STATE_RESERVED: Final = "reserved"
STATE_OUT_OF_SERVICE: Final = "out_of_service"
# Temporarily down for servicing. The OICP feed has no maintenance value (it
# reports these as OutOfService); this is surfaced by the eCarUp fallback, which
# distinguishes a maintenance connector from a hard out-of-service one.
STATE_MAINTENANCE: Final = "maintenance"
STATE_UNKNOWN: Final = "unknown"

AVAILABILITY_STATES: Final = [
    STATE_AVAILABLE,
    STATE_OCCUPIED,
    STATE_RESERVED,
    STATE_OUT_OF_SERVICE,
    STATE_MAINTENANCE,
    STATE_UNKNOWN,
]

# OICP EVSEStatus value -> normalised state.
OICP_STATUS_MAP: Final = {
    "Available": STATE_AVAILABLE,
    "Occupied": STATE_OCCUPIED,
    "Reserved": STATE_RESERVED,
    "OutOfService": STATE_OUT_OF_SERVICE,
    "EvseNotFound": STATE_UNKNOWN,
    "Unknown": STATE_UNKNOWN,
}
