"""Data update coordinator for WARP chargers."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    WarpApi,
    WarpAuthError,
    WarpConnectionError,
    WarpDeviceInfo,
    WarpError,
    WarpNotFoundError,
)
from .const import (
    ALL_TOPICS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    METER_ID_ENERGY_IMPORT,
    METER_ID_POWER,
    POLL_FAST,
    POLL_MEDIUM,
    POLL_MEDIUM_EVERY,
    POLL_SLOW,
    POLL_SLOW_EVERY,
    REQUIRED_TOPICS,
    T_AUTO_START,
    T_BOOST_MODE,
    T_BUTTON_STATE,
    T_CHARGE_MODE,
    T_CURRENT_CHARGE,
    T_ETHERNET_STATE,
    T_EV_STATE,
    T_EV_WAKEUP,
    T_EVSE_LOW_LEVEL,
    T_EVSE_STATE,
    T_EXTERNAL_CURRENT,
    T_EXTERNAL_ENABLED,
    T_FW_INSTALL_STATE,
    T_FW_STATE,
    T_INFO_FEATURES,
    T_LAST_CHARGES,
    T_LIMITS_ACTIVE,
    T_LIMITS_DEFAULT,
    T_LIMITS_STATE,
    T_METER_IDS,
    T_METER_VALUES,
    T_NFC_SEEN_TAGS,
    T_NTP_STATE,
    T_PM_CONFIG,
    T_PM_LOW_LEVEL,
    T_SUPPORTED_MODES,
    T_USERS_CONFIG,
    T_WIFI_STATE,
    WS_DEBOUNCE_COOLDOWN,
    WS_POLL_INTERVAL,
)

if TYPE_CHECKING:
    from .ws_client import WarpWebSocket


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _opt_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


@dataclass
class WarpData:
    """Snapshot of the charger state, derived from the topic cache."""

    cache: dict[str, Any]
    meter_ids: list[int]
    ws_connected: bool = False
    features: list[str] = field(default_factory=list)

    # --- raw topic accessors -------------------------------------------------
    @property
    def evse(self) -> dict[str, Any]:
        """evse/state."""
        return _dict(self.cache.get(T_EVSE_STATE))

    @property
    def evse_low_level(self) -> dict[str, Any]:
        """evse/low_level_state."""
        return _dict(self.cache.get(T_EVSE_LOW_LEVEL))

    @property
    def pm_config(self) -> dict[str, Any]:
        """power_manager/config."""
        return _dict(self.cache.get(T_PM_CONFIG))

    @property
    def pm_low_level(self) -> dict[str, Any]:
        """power_manager/low_level_state."""
        return _dict(self.cache.get(T_PM_LOW_LEVEL))

    @property
    def limits_state(self) -> dict[str, Any]:
        """charge_limits/state."""
        return _dict(self.cache.get(T_LIMITS_STATE))

    @property
    def limits_default(self) -> dict[str, Any]:
        """charge_limits/default_limits."""
        return _dict(self.cache.get(T_LIMITS_DEFAULT))

    @property
    def limits_active(self) -> dict[str, Any]:
        """charge_limits/active_limits."""
        return _dict(self.cache.get(T_LIMITS_ACTIVE))

    @property
    def current_charge(self) -> dict[str, Any] | None:
        """charge_tracker/current_charge."""
        return _opt_dict(self.cache.get(T_CURRENT_CHARGE))

    @property
    def last_charges(self) -> list[dict[str, Any]]:
        """charge_tracker/last_charges."""
        return [c for c in _list(self.cache.get(T_LAST_CHARGES)) if isinstance(c, dict)]

    @property
    def users(self) -> list[dict[str, Any]]:
        """users/config.users."""
        return [
            u
            for u in _list(_dict(self.cache.get(T_USERS_CONFIG)).get("users"))
            if isinstance(u, dict)
        ]

    @property
    def ev(self) -> dict[str, Any] | None:
        """ev/state."""
        return _opt_dict(self.cache.get(T_EV_STATE))

    @property
    def seen_tags(self) -> list[dict[str, Any]]:
        """nfc/seen_tags."""
        return [t for t in _list(self.cache.get(T_NFC_SEEN_TAGS)) if isinstance(t, dict)]

    @property
    def button_state(self) -> dict[str, Any]:
        """evse/button_state."""
        return _dict(self.cache.get(T_BUTTON_STATE))

    @property
    def wifi(self) -> dict[str, Any]:
        """wifi/state."""
        return _dict(self.cache.get(T_WIFI_STATE))

    @property
    def ethernet(self) -> dict[str, Any]:
        """ethernet/state."""
        return _dict(self.cache.get(T_ETHERNET_STATE))

    @property
    def ntp(self) -> dict[str, Any]:
        """ntp/state."""
        return _dict(self.cache.get(T_NTP_STATE))

    @property
    def fw_state(self) -> dict[str, Any]:
        """firmware_update/state."""
        return _dict(self.cache.get(T_FW_STATE))

    @property
    def fw_install_state(self) -> dict[str, Any]:
        """firmware_update/install_state."""
        return _dict(self.cache.get(T_FW_INSTALL_STATE))

    def has_topic(self, topic: str) -> bool:
        """Return True when the topic has been received at least once."""
        return topic in self.cache

    def flag(self, topic: str, key: str) -> bool | None:
        """Return a boolean field of a simple config topic, or None."""
        value = _dict(self.cache.get(topic)).get(key)
        return value if isinstance(value, bool) else None

    # --- derived values --------------------------------------------------------
    @property
    def charge_mode(self) -> int | None:
        """Active power manager charge mode."""
        return _dict(self.cache.get(T_CHARGE_MODE)).get("mode")

    @property
    def supported_charge_modes(self) -> list[int]:
        """Charge modes the charger currently offers."""
        return [int(m) for m in _list(self.cache.get(T_SUPPORTED_MODES))]

    @property
    def external_enabled(self) -> bool:
        """Whether the external control slot is enabled."""
        return bool(_dict(self.cache.get(T_EXTERNAL_ENABLED)).get("enabled", False))

    @property
    def external_current_ma(self) -> int | None:
        """External control current limit in mA."""
        return _dict(self.cache.get(T_EXTERNAL_CURRENT)).get("current")

    @property
    def auto_start_charging(self) -> bool | None:
        """evse/auto_start_charging."""
        return self.flag(T_AUTO_START, "auto_start_charging")

    @property
    def boost_mode(self) -> bool | None:
        """evse/boost_mode."""
        return self.flag(T_BOOST_MODE, "enabled")

    @property
    def ev_wakeup(self) -> bool | None:
        """evse/ev_wakeup."""
        return self.flag(T_EV_WAKEUP, "enabled")

    @property
    def meter_values(self) -> list[float]:
        """meters/0/values."""
        return _list(self.cache.get(T_METER_VALUES))

    def meter(self, value_id: int) -> float | None:
        """Return the meter value for a MeterValueID."""
        try:
            return float(self.meter_values[self.meter_ids.index(value_id)])
        except (ValueError, IndexError, TypeError):
            return None

    def has_meter(self, value_id: int) -> bool:
        """Return True when the meter provides this value id."""
        return value_id in self.meter_ids

    @property
    def power_w(self) -> float | None:
        """Charge power in W."""
        return self.meter(METER_ID_POWER)

    @property
    def energy_import_kwh(self) -> float | None:
        """Total imported energy in kWh."""
        return self.meter(METER_ID_ENERGY_IMPORT)

    @property
    def session_active(self) -> bool:
        """Whether a charge session is tracked."""
        cc = self.current_charge
        return bool(cc) and cc.get("user_id", -1) != -1

    @property
    def session_energy_kwh(self) -> float | None:
        """Energy of the running charge session in kWh."""
        cc = self.current_charge
        if not cc or cc.get("user_id", -1) == -1 or cc.get("meter_start") is None:
            return None
        energy = self.energy_import_kwh
        if energy is None:
            return None
        return max(0.0, round(energy - float(cc["meter_start"]), 3))

    @property
    def session_duration_s(self) -> int | None:
        """Duration of the running charge session in seconds."""
        if not self.session_active:
            return None
        charging_time = self.evse_low_level.get("charging_time")
        if isinstance(charging_time, (int, float)) and charging_time > 0:
            return int(charging_time / 1000)
        start = self.current_charge.get("evse_uptime_start") if self.current_charge else None
        uptime = self.evse_low_level.get("uptime")
        if isinstance(start, (int, float)) and isinstance(uptime, (int, float)):
            return max(0, int((uptime - start) / 1000))
        return None

    def user_name(self, user_id: Any) -> str | None:
        """Resolve a user id to its display name."""
        if not isinstance(user_id, int) or user_id < 0:
            return None
        for user in self.users:
            if user.get("id") == user_id:
                return str(user.get("display_name") or user.get("username") or user_id)
        return str(user_id)

    @property
    def session_user(self) -> str | None:
        """Display name of the user of the running session."""
        if not self.session_active or not self.current_charge:
            return None
        return self.user_name(self.current_charge.get("user_id"))

    @property
    def last_charge(self) -> dict[str, Any] | None:
        """Most recent finished charge session."""
        charges = self.last_charges
        return charges[-1] if charges else None

    @property
    def iec_state(self) -> int:
        """IEC 61851 state."""
        return int(self.evse.get("iec61851_state", 0))

    @property
    def charger_state(self) -> int:
        """Processed charger state."""
        return int(self.evse.get("charger_state", 0))

    @property
    def allowed_current_a(self) -> float:
        """Allowed charging current in A."""
        return int(self.evse.get("allowed_charging_current", 0)) / 1000

    @property
    def error_state(self) -> int:
        """Error state of the charge controller."""
        return int(self.evse.get("error_state", 0))

    @property
    def ev_name(self) -> str | None:
        """Name of the detected vehicle."""
        if not self.ev:
            return None
        return self.ev.get("name") or None

    @property
    def ev_soc(self) -> float | None:
        """State of charge of the detected vehicle in %."""
        if not self.ev:
            return None
        return self.ev.get("soc")


@dataclass(kw_only=True)
class WarpRuntimeData:
    """Runtime data stored on the config entry."""

    coordinator: WarpDataUpdateCoordinator
    api: WarpApi
    info: WarpDeviceInfo
    ws: WarpWebSocket | None = None


type WarpConfigEntry = ConfigEntry[WarpRuntimeData]


def build_data(
    cache: Mapping[str, Any], meter_ids: list[int], ws_connected: bool
) -> WarpData:
    """Build the immutable-ish snapshot handed to entities."""
    features = [str(f) for f in _list(cache.get(T_INFO_FEATURES))]
    return WarpData(
        cache=dict(cache),
        meter_ids=meter_ids,
        ws_connected=ws_connected,
        features=features,
    )


class WarpDataUpdateCoordinator(DataUpdateCoordinator[WarpData]):
    """Poll the WARP charger and merge WebSocket pushes."""

    config_entry: WarpConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WarpConfigEntry,
        api: WarpApi,
        info: WarpDeviceInfo,
        meter_ids: list[int],
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.info = info
        self._meter_ids = meter_ids
        self._cache: dict[str, Any] = {}
        self._poll_count = 0
        self.ws: WarpWebSocket | None = None
        self._fallback_interval = timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"WARP Charger {entry.title}",
            update_interval=self._fallback_interval,
        )
        self._push_debouncer = Debouncer(
            hass,
            LOGGER,
            cooldown=WS_DEBOUNCE_COOLDOWN,
            immediate=False,
            function=self._async_push_from_cache,
            background=True,
        )

    @property
    def ws_connected(self) -> bool:
        """Whether the push channel is up."""
        return self.ws is not None and self.ws.connected

    @property
    def cache(self) -> Mapping[str, Any]:
        """Read-only view of the topic cache (diagnostics)."""
        return self._cache

    # --- WebSocket hooks -------------------------------------------------------
    @callback
    def handle_ws_message(self, topic: str, payload: Any) -> None:
        """Store a pushed state and schedule an entity update."""
        if topic not in ALL_TOPICS:
            return
        if topic == T_METER_IDS and isinstance(payload, list):
            self._meter_ids = [int(i) for i in payload]
        self._cache[topic] = payload
        self._push_debouncer.async_schedule_call()

    async def _async_push_from_cache(self) -> None:
        self.async_set_updated_data(
            build_data(self._cache, self._meter_ids, self.ws_connected)
        )

    @callback
    def handle_ws_connection(self, connected: bool) -> None:
        """Adjust the poll interval when the push channel changes."""
        self.update_interval = WS_POLL_INTERVAL if connected else self._fallback_interval
        if connected:
            self._push_debouncer.async_schedule_call()
        else:
            self.hass.async_create_task(self.async_request_refresh())

    async def async_shutdown(self) -> None:
        """Stop the push channel and the debouncer."""
        await self._push_debouncer.async_shutdown()
        if self.ws is not None:
            await self.ws.stop()
        await super().async_shutdown()

    # --- HTTP polling ------------------------------------------------------------
    def _topics_for_poll(self) -> tuple[str, ...]:
        first = self._poll_count == 0
        topics: list[str] = list(POLL_FAST)
        if first or self._poll_count % POLL_MEDIUM_EVERY == 0:
            topics += POLL_MEDIUM
        if first or self._poll_count % POLL_SLOW_EVERY == 0:
            topics += POLL_SLOW
        # Topics never seen yet are fetched regardless of tier.
        topics += [t for t in (*POLL_MEDIUM, *POLL_SLOW) if t not in self._cache and t not in topics]
        return tuple(topics)

    async def _async_update_data(self) -> WarpData:
        """Fetch topics over HTTP and merge them into the cache."""
        topics = self._topics_for_poll()
        self._poll_count += 1
        results = await asyncio.gather(
            *(self.api.get(t) for t in topics), return_exceptions=True
        )
        res: dict[str, Any] = dict(zip(topics, results, strict=True))

        for result in res.values():
            if isinstance(result, WarpAuthError):
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="authentication_error",
                ) from result

        failed_required = [
            t for t in REQUIRED_TOPICS if isinstance(res.get(t), BaseException)
        ]
        if failed_required:
            if self.ws_connected and self._cache:
                LOGGER.debug(
                    "Poll failed for %s while websocket connected; using cache",
                    failed_required,
                )
                return build_data(self._cache, self._meter_ids, self.ws_connected)
            err = res[failed_required[0]]
            if isinstance(err, WarpConnectionError):
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="communication_error",
                    translation_placeholders={"error": str(err)},
                ) from err
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="unknown_error",
                translation_placeholders={"error": f"{failed_required[0]}: {err}"},
            ) from err

        for topic, result in res.items():
            if isinstance(result, BaseException):
                if not isinstance(result, WarpNotFoundError):
                    LOGGER.debug("Topic %s failed: %s", topic, result)
                continue
            self._cache[topic] = result

        values = self._cache.get(T_METER_VALUES)
        if isinstance(values, list) and values and len(values) != len(self._meter_ids):
            try:
                ids = await self.api.get(T_METER_IDS)
                if isinstance(ids, list):
                    self._meter_ids = [int(i) for i in ids]
                    self._cache[T_METER_IDS] = ids
            except WarpError as err:
                LOGGER.debug("Could not refresh meter value ids: %s", err)

        return build_data(self._cache, self._meter_ids, self.ws_connected)
