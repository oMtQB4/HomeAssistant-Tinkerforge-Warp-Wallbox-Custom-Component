"""Data update coordinator for WARP chargers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
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
    DOMAIN,
    LOGGER,
    METER_ID_ENERGY_IMPORT,
    METER_ID_POWER,
    SCAN_INTERVAL,
    T_CHARGE_MODE,
    T_CURRENT_CHARGE,
    T_EV_STATE,
    T_EVSE_STATE,
    T_EXTERNAL_CURRENT,
    T_EXTERNAL_ENABLED,
    T_METER_IDS,
    T_METER_VALUES,
    T_SUPPORTED_MODES,
)

REQUIRED_TOPICS: tuple[str, ...] = (
    T_CHARGE_MODE,
    T_SUPPORTED_MODES,
    T_EVSE_STATE,
    T_EXTERNAL_ENABLED,
    T_EXTERNAL_CURRENT,
    T_METER_VALUES,
)
OPTIONAL_TOPICS: tuple[str, ...] = (T_CURRENT_CHARGE, T_EV_STATE)


@dataclass
class WarpData:
    """Snapshot of the charger state."""

    charge_mode: int | None
    supported_charge_modes: list[int]
    evse: dict[str, Any]
    external_enabled: bool
    external_current_ma: int | None
    meter_ids: list[int] = field(default_factory=list)
    meter_values: list[float] = field(default_factory=list)
    current_charge: dict[str, Any] | None = None
    ev: dict[str, Any] | None = None

    def meter(self, value_id: int) -> float | None:
        """Return the meter value for a MeterValueID."""
        try:
            return float(self.meter_values[self.meter_ids.index(value_id)])
        except (ValueError, IndexError, TypeError):
            return None

    @property
    def power_w(self) -> float | None:
        """Charge power in W."""
        return self.meter(METER_ID_POWER)

    @property
    def energy_import_kwh(self) -> float | None:
        """Total imported energy in kWh."""
        return self.meter(METER_ID_ENERGY_IMPORT)

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


type WarpConfigEntry = ConfigEntry[WarpRuntimeData]


class WarpDataUpdateCoordinator(DataUpdateCoordinator[WarpData]):
    """Poll the WARP charger."""

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
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"WARP Charger {entry.title}",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> WarpData:
        """Fetch all topics."""
        topics = (*REQUIRED_TOPICS, *OPTIONAL_TOPICS)
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

        for topic in REQUIRED_TOPICS:
            result = res[topic]
            if isinstance(result, WarpConnectionError):
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="communication_error",
                    translation_placeholders={"error": str(result)},
                ) from result
            if isinstance(result, BaseException):
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="unknown_error",
                    translation_placeholders={"error": f"{topic}: {result}"},
                ) from result

        for topic in OPTIONAL_TOPICS:
            result = res[topic]
            if isinstance(result, BaseException):
                if not isinstance(result, WarpNotFoundError):
                    LOGGER.debug("Optional topic %s failed: %s", topic, result)
                res[topic] = None
            elif not isinstance(result, dict):
                res[topic] = None

        values = res[T_METER_VALUES] if isinstance(res[T_METER_VALUES], list) else []
        if values and len(values) != len(self._meter_ids):
            try:
                ids = await self.api.get(T_METER_IDS)
                if isinstance(ids, list):
                    self._meter_ids = [int(i) for i in ids]
            except WarpError as err:
                LOGGER.debug("Could not refresh meter value ids: %s", err)

        charge_mode = res[T_CHARGE_MODE]
        supported = res[T_SUPPORTED_MODES]
        external_enabled = res[T_EXTERNAL_ENABLED]
        external_current = res[T_EXTERNAL_CURRENT]

        return WarpData(
            charge_mode=charge_mode.get("mode") if isinstance(charge_mode, dict) else None,
            supported_charge_modes=(
                [int(m) for m in supported] if isinstance(supported, list) else []
            ),
            evse=res[T_EVSE_STATE] if isinstance(res[T_EVSE_STATE], dict) else {},
            external_enabled=bool(
                external_enabled.get("enabled", False)
                if isinstance(external_enabled, dict)
                else False
            ),
            external_current_ma=(
                external_current.get("current")
                if isinstance(external_current, dict)
                else None
            ),
            meter_ids=self._meter_ids,
            meter_values=values,
            current_charge=res[T_CURRENT_CHARGE],
            ev=res[T_EV_STATE],
        )
