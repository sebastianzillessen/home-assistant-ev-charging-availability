<p align="center">
  <img src="custom_components/swiss_ev_charging/brand/logo@2x.png" alt="Swiss EV Charging" width="440">
</p>

# Swiss EV Charging (ich-tanke-strom) — Home Assistant Integration

Home Assistant integration for Switzerland's official real-time EV charging
availability, powered by the open data behind
[ich-tanke-strom.ch](https://www.ich-tanke-strom.ch), operated by the Swiss
Federal Office of Energy (SFOE). It tracks charging point availability near a GPS
position and/or for specific charging points you pin, exposes sensors and
"is free" binary sensors, and — because availability is modelled as enum sensors —
lets Home Assistant record long-term statistics for occupancy analysis.

No API key or registration is required.

## How it works

The SFOE publishes two country-wide JSON files in the OICP 2.3 format:

- **EVSEData** — static master data (location, operator, plug types, power)
- **EVSEStatus** — live availability per charging point (EVSE)

Because the data is delivered as full-country files rather than a query API, the
integration downloads the live status file **once per polling interval** and
merges it (by `EvseID`) onto locally cached master data — it does **not** poll
per station. The large master file is cached and refreshed only occasionally.

### Operator live-status fallbacks

The SFOE feed reports `Unknown` live status for a large share of some operators'
charging points even when the operator itself knows the state. For those
operators that expose their own **key-less public API**, the integration fills
the gap: for any tracked station the SFOE feed leaves `unknown`, it looks the
state up from the operator's own backend. Two operators are covered today —
**eCarUp** and **Move** — together the two biggest sources of missing status.

All of this is **best-effort** and runs only for stations the SFOE feed could not
resolve: any failure of an operator API simply leaves those stations `unknown`,
exactly as before. It fires before the "became available" notification, so a
charger going free still notifies. Diagnostics list what each fallback filled
(`ecarup_resolved_ids`, `move_resolved_ids`).

**eCarUp** (`CH*ECU…`) — via eCarUp's public map API (`www.ecarup.com/api`). Per
station: query the map for the area (one request covering all tracked eCarUp
stations), fetch per-connector detail, then match either by roaming id
(`Hubject.ID`, the authoritative join) or by nearest-station coordinate — the
coordinate match is used only when that station's connectors **unanimously
agree**, so an ambiguous multi-connector site stays `unknown` rather than
guessing. Connector state maps as `Free → available`,
`Occupied`/`Car connected → occupied`, `Reserved → reserved`,
`Maintenance → maintenance`, `Offline → out_of_service`, `Unknown → unknown`.

**Move** (`CH*CCI…`, `CH*CCC…`) — via the Move app's public search endpoint
(`app.move.ch/search`). One request covers all tracked Move stations. The join is
**direct and authoritative**: each returned station's id *is* the OICP `EvseID`,
so no coordinate matching is needed. Availability maps as `available → available`,
`occupied → occupied`, `outOfService → out_of_service`, `unknown → unknown`.
(Move's `CH*SOC`/`CH*MMN` points are not served by this backend and are not
recovered.)

### Coverage and known gaps by operator

Most operators report reliable live status through the SFOE feed. A few do not —
they report `Unknown` (or are absent from the status feed) for many or all of
their points. The table below is a snapshot of the country-wide feed (~18,900
charging points, ~20% of which report no live status) to gauge where extra
integration effort would pay off. "Share" is the operator's fraction of all
Swiss charging points; "No live status" is how many of *its* points the SFOE feed
leaves dark.

| Operator | Share of all points | No live status | Recoverable without an API key? |
| --- | --: | --: | --- |
| **eCarUp** | ~35% | ~32% | ✅ **Yes — implemented** (public map API) |
| **Move** | ~13% | ~22% | ✅ **Yes — implemented** (public app search API; `CH*CCI`/`CH*CCC` only) |
| swisscharge | ~13% | ~6% | — mostly healthy |
| Shell Recharge | ~6% | ~3% | — mostly healthy |
| AVIA VOLT | ~3% | ~14% | ❌ No public availability endpoint found |
| Tesla | ~2% | **100%** | ❌ Availability API is access-controlled (HTTP 403) |
| Power Up | ~1% | ~16% | ❌ No public endpoint found |
| Saascharge | ~1% | ~23% | ❌ No public endpoint found |
| PLUG N ROLL (Repower) | ~1% | **100%** | ❌ No reachable public endpoint |
| evpass (Green Motion) | <1% | ~95% | ❌ Map is behind authentication |
| AIL | <1% | **100%** | ❌ Not on a recoverable backend |

Operators reporting essentially complete live status (≈0% dark) include GoFast,
IONITY, Electra, Lidl, Plenitude, Chargepoint and Fastned.

**eCarUp and Move together cover the bulk of the gap** — they are the two
largest operators and the two biggest sources of missing status, and both expose
a genuinely public, key-less backend. The remaining dark operators either never
publish live status to the roaming/SFOE layer at all (Tesla, PLUG N ROLL, AIL) or
keep it behind their own authentication (evpass, AVIA, Power Up, Saascharge), so
recovering them would require per-operator reverse engineering with uncertain,
fragile results.

## Installation

### HACS (recommended)

1. In HACS → Integrations → ⋮ → *Custom repositories*, add
   `https://github.com/sebastianzillessen/home-assistant-ev-charging-availability`
   as category **Integration**.
2. Install **Swiss EV Charging (ich-tanke-strom)** and restart Home Assistant.

### Manual

Copy `custom_components/swiss_ev_charging` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

Add the integration via **Settings → Devices & Services → Add Integration →
Swiss EV Charging**. You can track stations two ways (combine both):

| Option | Description |
| --- | --- |
| Latitude / Longitude | Origin for nearby discovery (defaults to your HA home location) |
| Search radius (m) | Only stations within this radius are considered |
| Max nearby stations | Number of closest stations to expose as entities |
| Minimum power (kW) | Filter out chargers below this power |
| Plug type filter | Comma-separated substrings, e.g. `CCS` |
| Pinned EVSE IDs | Comma-separated `EvseID`s to always track (e.g. the charger near your flat) |
| Polling interval (s) | Default 180 s; minimum 60 s |
| Tag | Free-text label applied to every station of this entry (exposed as a `tag` attribute) |
| Notify when available | Toggle: send a notification when a tracked station becomes available |
| Notify service | Which `notify.*` service to call (blank = a Home Assistant persistent notification) |

At least a location **or** one pinned EVSE ID is required. Radius, filters,
pinned IDs and the interval can be changed later via the integration's
**Configure** (options) dialog.

## Entities

For each tracked charging point you get:

- **Availability sensor** (enum): `available` / `occupied` / `reserved` /
  `out_of_service` / `maintenance` / `unknown`, with attributes `operator`, `plug_types`,
  `max_power_kw`, `distance_km`, `address`, `latitude`, `longitude`, `is_pinned`.
- **"Is free" binary sensor**: on when the point is available — convenient for
  automations.

## Showing the chargers on the map

Because the availability sensor carries `latitude`/`longitude` attributes, each
tracked charger already appears on Home Assistant's built-in **Map** panel and
can be added to a dashboard map card. (If your `type: map` card shows nothing,
set `show_all: true` or list the sensors under `entities:`.)

```yaml
type: map
show_all: true
label_mode: state   # marker label shows available / occupied / …
```

Home Assistant colours map markers statically, not by state. To get
**availability-coloured markers** (green when free, red when in use), enable the
**"Colour map markers by availability"** option (integration → *Configure*). Each
availability sensor then exposes a state-coloured dot as its `entity_picture`, so
markers follow availability automatically — no template sensors needed.

Note the trade-off: because a marker's image is the entity's `entity_picture`,
which Home Assistant also uses everywhere else, turning this on replaces the
sensor's `mdi:ev-station` **icon with the coloured dot in entity lists, cards and
the more-info dialog too** — not only on the map. It is therefore off by default.
Marker colours: green = available, red = occupied, orange = reserved,
purple = maintenance, grey = out of service, light grey = unknown.

If you would rather keep the icon and colour only the map, drive the map from a
small template sensor that mirrors the charger and sets the `entity_picture`
itself, and add that sensor to the map instead:

```yaml
template:
  - sensor:
      - name: Charger XY (map)
        state: "{{ states('sensor.charger_xy_availability') }}"
        attributes:
          latitude: "{{ state_attr('sensor.charger_xy_availability', 'latitude') }}"
          longitude: "{{ state_attr('sensor.charger_xy_availability', 'longitude') }}"
          entity_picture: >
            {% set s = states('sensor.charger_xy_availability') %}
            {% set c = 'limegreen' if s == 'available'
                       else 'red' if s in ['occupied', 'reserved']
                       else 'gray' %}
            data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='24'
            height='24'><circle cx='12' cy='12' r='11' fill='{{ c }}'/></svg>
```

For richer per-marker styling, the community `nathan-gs/ha-map-card` custom card
is another alternative.

## Example automation

Notify when a pinned charger becomes free:

```yaml
automation:
  - alias: "Charger near the flat is free"
    trigger:
      - platform: state
        entity_id: binary_sensor.zurich_bahnhofstrasse_is_free
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "The charger near the flat is free."
```

## Development

```bash
pip install -r requirements_test.txt
pytest
```

CI runs Home Assistant's `hassfest`, HACS validation and the pytest suite on
every push and pull request.

### Upstream schema drift detection

The upstream OICP feeds occasionally change shape (e.g. a field serialised as an
object instead of an array, or a numeric value delivered as a string).
`scripts/generate_evse_schema.py` downloads both feeds and writes an inferred
JSON Schema to `schemas/`. The `Update feed schema` workflow runs weekly (and on
demand): if the regenerated schema differs from what is committed, it opens a
pull request and requests your review, so a breaking upstream change is caught
before it reaches users.

Regenerate locally with:

```bash
pip install genson
python scripts/generate_evse_schema.py
```

> The auto-PR needs "Allow GitHub Actions to create and approve pull requests"
> enabled under **Settings → Actions → General → Workflow permissions**.

### Releases

The `Release` workflow tags builds from the `version` in `manifest.json`:

- push to `main` → a GitHub release `v<version>` (created once per version bump)
- push to any other branch → a **pre-release** `v<version>-<branch>.<run>`

Bump `manifest.json` `version` to cut a new stable release on the next merge to
`main`.

## Data source

Open data from the Swiss Federal Office of Energy (SFOE) via
[data.geo.admin.ch](https://data.geo.admin.ch), dataset
`ch.bfe.ladestellen-elektromobilitaet`. See the
[SFOE documentation](https://github.com/SFOE/ichtankestrom_Documentation).

## Roadmap

Deferred for a later iteration: Home Assistant zone sourcing, live device-tracker
GPS as an origin, and dedicated automation trigger blueprints.
