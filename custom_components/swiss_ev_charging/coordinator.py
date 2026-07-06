"""Data update coordinator for the Swiss EV Charging integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from .api import (
    ChargingPoint,
    SwissEvChargingApi,
    SwissEvChargingApiError,
    index_status_by_normalized,
    normalize_evse_id,
)
from .ecarup import async_resolve_ecarup_states, is_ecarup_evse_id
from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAX_STATIONS,
    CONF_MIN_POWER,
    CONF_NOTIFY_ON_AVAILABLE,
    CONF_NOTIFY_SERVICE,
    CONF_PINNED_EVSE_IDS,
    CONF_PLUG_TYPES,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_TAG,
    DEFAULT_MAX_STATIONS,
    DEFAULT_MIN_POWER,
    DEFAULT_NOTIFY_ON_AVAILABLE,
    DEFAULT_RADIUS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MASTER_REFRESH_INTERVAL,
    MIN_SCAN_INTERVAL,
    STATE_AVAILABLE,
    STATE_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TrackedEvse:
    """A tracked charging point combining master data, live state and distance."""

    point: ChargingPoint
    state: str
    distance_m: float | None
    is_pinned: bool


class SwissEvChargingCoordinator(DataUpdateCoordinator[dict[str, TrackedEvse]]):
    """Download live status each poll and merge it onto cached master data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator from a config entry."""
        self.entry = entry
        self.api = SwissEvChargingApi(async_get_clientsession(hass))
        self._master: dict[str, ChargingPoint] = {}
        self._master_refreshed_at = None
        # The set of EVSE IDs we expose as entities; fixed after the first refresh
        # so the entity list is stable across reloads.
        self.tracked_ids: list[str] = []
        # Diagnostics: size of the last live-status feed, and the tracked IDs that
        # had no live status in it (surfaced as ``unknown``).
        self.status_feed_size: int = 0
        self.unmatched_ids: list[str] = []
        # Diagnostics: eCarUp EVSEs the SFOE feed left unknown that we filled from
        # eCarUp's own public map API.
        self.ecarup_resolved_ids: list[str] = []

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self._scan_interval),
        )

    @property
    def _scan_interval(self) -> int:
        """Return the effective poll interval in seconds (clamped to a minimum)."""
        configured = self._option(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return max(int(configured), MIN_SCAN_INTERVAL)

    def _option(self, key: str, default):
        """Read a value preferring options over the original config data."""
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    @property
    def tag(self) -> str | None:
        """Return the user-configured tag applied to all tracked stations."""
        value = self._option(CONF_TAG, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    async def _async_update_data(self) -> dict[str, TrackedEvse]:
        """Refresh master data if stale, then poll live status and merge."""
        await self._async_ensure_master_data()

        try:
            statuses = await self.api.async_get_status()
        except SwissEvChargingApiError as err:
            raise UpdateFailed(str(err)) from err

        if not self.tracked_ids:
            self.tracked_ids = self._select_tracked_ids()

        # Fallback index for operators (e.g. eCarUp) whose EvseID is formatted
        # differently in the master and status feeds; only used on an exact miss.
        status_by_norm = index_status_by_normalized(statuses)
        self.status_feed_size = len(statuses)
        unmatched: list[str] = []

        origin = self._origin()
        result: dict[str, TrackedEvse] = {}
        for evse_id in self.tracked_ids:
            point = self._master.get(evse_id) or ChargingPoint(evse_id=evse_id)
            state = statuses.get(evse_id)
            if state is None:
                state = status_by_norm.get(normalize_evse_id(evse_id))
                if state is not None:
                    _LOGGER.debug(
                        "Matched %s to live status via normalized EvseID", evse_id
                    )
            if state is None:
                state = STATE_UNKNOWN
                unmatched.append(evse_id)
            result[evse_id] = TrackedEvse(
                point=point,
                state=state,
                distance_m=self._distance(origin, point),
                is_pinned=evse_id in self._pinned_ids(),
            )

        self.unmatched_ids = unmatched
        if unmatched:
            _LOGGER.debug(
                "%d/%d tracked stations have no live status in the SFOE feed "
                "(shown as unknown): %s",
                len(unmatched),
                len(self.tracked_ids),
                ", ".join(unmatched),
            )

        # The SFOE feed reports Unknown for many eCarUp EVSEs; fill those from
        # eCarUp's own key-less public map API before notifying, so an eCarUp
        # station becoming available still fires a notification.
        await self._async_apply_ecarup_fallback(result)

        # self.data still holds the previous refresh here; compare to notify on
        # stations that just became available.
        self._notify_newly_available(self.data, result)
        return result

    async def _async_apply_ecarup_fallback(
        self, result: dict[str, TrackedEvse]
    ) -> None:
        """Fill ``unknown`` eCarUp EVSEs from eCarUp's public map API.

        Best-effort: overrides only states we can resolve confidently and never
        raises, so a third-party outage leaves those stations ``unknown``.
        """
        targets = [
            (evse_id, tracked.point.latitude, tracked.point.longitude)
            for evse_id, tracked in result.items()
            if tracked.state == STATE_UNKNOWN
            and is_ecarup_evse_id(evse_id)
            and tracked.point.latitude is not None
            and tracked.point.longitude is not None
        ]
        if not targets:
            self.ecarup_resolved_ids = []
            return

        try:
            resolved = await async_resolve_ecarup_states(
                async_get_clientsession(self.hass), targets
            )
        except Exception as err:  # noqa: BLE001 - fallback must never break polling
            _LOGGER.debug("eCarUp status fallback failed: %s", err)
            self.ecarup_resolved_ids = []
            return

        for evse_id, state in resolved.items():
            tracked = result.get(evse_id)
            if tracked is not None:
                tracked.state = state

        self.ecarup_resolved_ids = list(resolved)
        if resolved:
            self.unmatched_ids = [e for e in self.unmatched_ids if e not in resolved]
            _LOGGER.debug(
                "Filled %d eCarUp station(s) from the eCarUp public API: %s",
                len(resolved),
                ", ".join(resolved),
            )

    async def _async_ensure_master_data(self) -> None:
        """Download the static master file on first use or when it is stale."""
        now = dt_util.utcnow()
        if self._master and self._master_refreshed_at is not None:
            if now - self._master_refreshed_at < MASTER_REFRESH_INTERVAL:
                return
        try:
            self._master = await self.api.async_get_master_data()
            self._master_refreshed_at = now
        except SwissEvChargingApiError as err:
            if not self._master:
                # No cached data to fall back on: surface the failure.
                raise UpdateFailed(str(err)) from err
            _LOGGER.warning("Keeping cached master data; refresh failed: %s", err)

    def _notify_newly_available(
        self,
        previous: dict[str, TrackedEvse] | None,
        current: dict[str, TrackedEvse],
    ) -> None:
        """Fire a notification for stations that just became available.

        Skips the very first refresh (no ``previous``) to avoid a burst of
        notifications on startup.
        """
        if previous is None:
            return
        if not self._option(CONF_NOTIFY_ON_AVAILABLE, DEFAULT_NOTIFY_ON_AVAILABLE):
            return
        # A notify.* entity id, or blank to fall back to a persistent notification.
        target = (self._option(CONF_NOTIFY_SERVICE, "") or "").strip()

        for evse_id, tracked in current.items():
            was = previous.get(evse_id)
            if was is None:
                continue
            if was.state != STATE_AVAILABLE and tracked.state == STATE_AVAILABLE:
                self.hass.async_create_task(
                    self._async_send_notification(target, tracked)
                )

    async def _async_send_notification(
        self, target: str, tracked: TrackedEvse
    ) -> None:
        """Publish a message for one station via the configured notify entity."""
        label = tracked.point.name or tracked.point.evse_id
        message = f"{label} is now available"
        if self.tag:
            message = f"[{self.tag}] {message}"
        data = {"message": message, "title": "EV charger available"}
        try:
            if target:
                # Any entity that can publish a message (notify.* entity).
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {"entity_id": target, **data},
                    blocking=False,
                )
            else:
                await self.hass.services.async_call(
                    "persistent_notification", "create", data, blocking=False
                )
        except Exception as err:  # noqa: BLE001 - notification must never break polling
            _LOGGER.warning(
                "Failed to notify %s for %s: %s",
                target or "persistent_notification",
                tracked.point.evse_id,
                err,
            )

    def _select_tracked_ids(self) -> list[str]:
        """Compute the tracked set: pinned IDs plus the N closest matches."""
        pinned = self._pinned_ids()
        origin = self._origin()
        nearby: list[str] = []

        if origin is not None:
            radius = float(self._option(CONF_RADIUS, DEFAULT_RADIUS))
            max_stations = int(self._option(CONF_MAX_STATIONS, DEFAULT_MAX_STATIONS))
            min_power = float(self._option(CONF_MIN_POWER, DEFAULT_MIN_POWER))
            plug_filter = {p.lower() for p in self._option(CONF_PLUG_TYPES, []) or []}

            candidates: list[tuple[float, str]] = []
            for evse_id, point in self._master.items():
                if evse_id in pinned:
                    continue
                dist = self._distance(origin, point)
                if dist is None or dist > radius:
                    continue
                if min_power and (point.max_power_kw or 0) < min_power:
                    continue
                if plug_filter and not _matches_plug(point.plugs, plug_filter):
                    continue
                candidates.append((dist, evse_id))
            candidates.sort(key=lambda item: item[0])
            nearby = [evse_id for _, evse_id in candidates[:max_stations]]

        # Preserve order: pinned first, then nearby, without duplicates.
        ordered: list[str] = []
        for evse_id in [*pinned, *nearby]:
            if evse_id not in ordered:
                ordered.append(evse_id)
        return ordered

    def _pinned_ids(self) -> list[str]:
        """Return the configured pinned EVSE IDs."""
        return list(self._option(CONF_PINNED_EVSE_IDS, []) or [])

    def _origin(self) -> tuple[float, float] | None:
        """Return the configured ``(latitude, longitude)`` origin, if any."""
        lat = self._option(CONF_LATITUDE, None)
        lon = self._option(CONF_LONGITUDE, None)
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)

    @staticmethod
    def _distance(
        origin: tuple[float, float] | None, point: ChargingPoint
    ) -> float | None:
        """Return the distance in metres from origin to point, if computable."""
        if origin is None or point.latitude is None or point.longitude is None:
            return None
        return distance(origin[0], origin[1], point.latitude, point.longitude)

    @callback
    def async_update_options(self) -> None:
        """Reset cached selection so option changes take effect on next refresh."""
        self.tracked_ids = []
        self.update_interval = timedelta(seconds=self._scan_interval)


def _matches_plug(plugs: list[str], wanted: set[str]) -> bool:
    """Return True if any of the point's plugs contains a wanted plug token."""
    lowered = [p.lower() for p in plugs]
    return any(any(w in p for p in lowered) for w in wanted)
