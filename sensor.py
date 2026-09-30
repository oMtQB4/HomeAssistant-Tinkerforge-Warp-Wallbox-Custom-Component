"""Sensors for WARP chargers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.dt import utc_from_timestamp, utcnow

from .const import (
    CHARGER_STATE_MAP,
    CONNECTION_STATE_MAP,
    DC_FAULT_STATE_MAP,
    ERROR_STATE_MAP,
    IEC61851_STATE_MAP,
    METER_ID_CURRENT_L1,
    METER_ID_CURRENT_L2,
    METER_ID_CURRENT_L3,
    METER_ID_ENERGY_EXPORT,
    METER_ID_ENERGY_IMPORT,
    METER_ID_FREQUENCY,
    METER_ID_POWER,
    METER_ID_POWER_FACTOR,
    METER_ID_POWER_L1,
    METER_ID_POWER_L2,
    METER_ID_POWER_L3,
    METER_ID_VOLTAGE_L1,
    METER_ID_VOLTAGE_L2,
    METER_ID_VOLTAGE_L3,
)
from .coordinator import WarpConfigEntry, WarpData
from .entity import WarpEntity

PARALLEL_UPDATES = 0

type SensorValue = datetime | float | int | str | None


@dataclass(frozen=True, kw_only=True)
class WarpSensorDescription(SensorEntityDescription):
    """Describe a WARP sensor."""

    has_fn: Callable[[WarpData], bool] = lambda _: True
    value_fn: Callable[[WarpData], SensorValue]


def _meter_sensor(
    key: str,
    value_id: int,
    *,
    device_class: SensorDeviceClass,
    unit: str | None,
    state_class: SensorStateClass = SensorStateClass.MEASUREMENT,
    precision: int = 1,
    enabled: bool = True,
    diagnostic: bool = False,
) -> WarpSensorDescription:
    return WarpSensorDescription(
        key=key,
        translation_key=key,
        device_class=device_class,
        native_unit_of_measurement=unit,
        state_class=state_class,
        suggested_display_precision=precision,
        entity_registry_enabled_default=enabled,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        has_fn=lambda d, vid=value_id: d.has_meter(vid),
        value_fn=lambda d, vid=value_id: d.meter(vid),
    )


def _uptime(d: WarpData) -> datetime | None:
    uptime = d.evse_low_level.get("uptime")
    if not isinstance(uptime, (int, float)):
        return None
    return utcnow().replace(microsecond=0) - timedelta(milliseconds=uptime)


def _target_time(d: WarpData) -> datetime | None:
    ts = d.limits_state.get("target_timestamp_ms")
    if not isinstance(ts, (int, float)) or ts <= 0:
        return None
    return utc_from_timestamp(ts / 1000)


def _limit_value(d: WarpData, key: str) -> float | None:
    value = d.limits_state.get(key)
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return value


def _last_charge_value(d: WarpData, key: str) -> float | None:
    last = d.last_charge
    if not last:
        return None
    value = last.get(key)
    return value if isinstance(value, (int, float)) else None


def _ip_address(d: WarpData) -> str | None:
    if d.ethernet.get("connection_state") == 3 and d.ethernet.get("ip") not in (None, "0.0.0.0"):
        return str(d.ethernet["ip"])
    if d.wifi.get("connection_state") == 3 and d.wifi.get("sta_ip") not in (None, "0.0.0.0"):
        return str(d.wifi["sta_ip"])
    return None


def _phases(d: WarpData) -> str | None:
    is_3p = d.pm_low_level.get("is_3phase")
    if isinstance(is_3p, bool):
        return "three" if is_3p else "one"
    return None


DESCRIPTIONS: tuple[WarpSensorDescription, ...] = (
    # --- existing (keys must not change) ---
    WarpSensorDescription(
        key="charger_state",
        translation_key="charger_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(CHARGER_STATE_MAP.values()),
        value_fn=lambda d: CHARGER_STATE_MAP.get(d.charger_state, "error"),
    ),
    WarpSensorDescription(
        key="iec61851_state",
        translation_key="iec61851_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(IEC61851_STATE_MAP.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: IEC61851_STATE_MAP.get(d.iec_state, "error"),
    ),
    WarpSensorDescription(
        key="allowed_current",
        translation_key="allowed_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.allowed_current_a,
    ),
    WarpSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        has_fn=lambda d: d.has_meter(METER_ID_POWER),
        value_fn=lambda d: d.power_w,
    ),
    WarpSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        has_fn=lambda d: d.has_meter(METER_ID_ENERGY_IMPORT),
        value_fn=lambda d: d.energy_import_kwh,
    ),
    WarpSensorDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=3,
        has_fn=lambda d: d.current_charge is not None
        and d.has_meter(METER_ID_ENERGY_IMPORT),
        value_fn=lambda d: d.session_energy_kwh,
    ),
    WarpSensorDescription(
        key="ev_name",
        translation_key="ev_name",
        has_fn=lambda d: d.ev is not None,
        value_fn=lambda d: d.ev_name,
    ),
    WarpSensorDescription(
        key="ev_soc",
        translation_key="ev_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        has_fn=lambda d: d.ev is not None,
        value_fn=lambda d: d.ev_soc,
    ),
    # --- meter details ---
    _meter_sensor("current_l1", METER_ID_CURRENT_L1, device_class=SensorDeviceClass.CURRENT, unit=UnitOfElectricCurrent.AMPERE),
    _meter_sensor("current_l2", METER_ID_CURRENT_L2, device_class=SensorDeviceClass.CURRENT, unit=UnitOfElectricCurrent.AMPERE),
    _meter_sensor("current_l3", METER_ID_CURRENT_L3, device_class=SensorDeviceClass.CURRENT, unit=UnitOfElectricCurrent.AMPERE),
    _meter_sensor("voltage_l1", METER_ID_VOLTAGE_L1, device_class=SensorDeviceClass.VOLTAGE, unit=UnitOfElectricPotential.VOLT, enabled=False, diagnostic=True),
    _meter_sensor("voltage_l2", METER_ID_VOLTAGE_L2, device_class=SensorDeviceClass.VOLTAGE, unit=UnitOfElectricPotential.VOLT, enabled=False, diagnostic=True),
    _meter_sensor("voltage_l3", METER_ID_VOLTAGE_L3, device_class=SensorDeviceClass.VOLTAGE, unit=UnitOfElectricPotential.VOLT, enabled=False, diagnostic=True),
    _meter_sensor("power_l1", METER_ID_POWER_L1, device_class=SensorDeviceClass.POWER, unit=UnitOfPower.WATT, precision=0, enabled=False),
    _meter_sensor("power_l2", METER_ID_POWER_L2, device_class=SensorDeviceClass.POWER, unit=UnitOfPower.WATT, precision=0, enabled=False),
    _meter_sensor("power_l3", METER_ID_POWER_L3, device_class=SensorDeviceClass.POWER, unit=UnitOfPower.WATT, precision=0, enabled=False),
    _meter_sensor("frequency", METER_ID_FREQUENCY, device_class=SensorDeviceClass.FREQUENCY, unit=UnitOfFrequency.HERTZ, precision=2, enabled=False, diagnostic=True),
    _meter_sensor("energy_export", METER_ID_ENERGY_EXPORT, device_class=SensorDeviceClass.ENERGY, unit=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING, precision=3, enabled=False),
    _meter_sensor("power_factor", METER_ID_POWER_FACTOR, device_class=SensorDeviceClass.POWER_FACTOR, unit=None, precision=2, enabled=False, diagnostic=True),
    # --- session + limits ---
    WarpSensorDescription(
        key="session_duration",
        translation_key="session_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        has_fn=lambda d: d.current_charge is not None,
        value_fn=lambda d: d.session_duration_s,
    ),
    WarpSensorDescription(
        key="session_user",
        translation_key="session_user",
        has_fn=lambda d: d.current_charge is not None,
        value_fn=lambda d: d.session_user,
    ),
    WarpSensorDescription(
        key="last_session_energy",
        translation_key="last_session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        has_fn=lambda d: d.has_topic("charge_tracker/last_charges"),
        value_fn=lambda d: _last_charge_value(d, "energy_charged"),
    ),
    WarpSensorDescription(
        key="last_session_duration",
        translation_key="last_session_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        has_fn=lambda d: d.has_topic("charge_tracker/last_charges"),
        value_fn=lambda d: _last_charge_value(d, "charge_duration"),
    ),
    WarpSensorDescription(
        key="limit_target_energy",
        translation_key="limit_target_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        has_fn=lambda d: d.has_topic("charge_limits/state"),
        value_fn=lambda d: _limit_value(d, "target_energy_kwh"),
    ),
    WarpSensorDescription(
        key="limit_target_time",
        translation_key="limit_target_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        has_fn=lambda d: d.has_topic("charge_limits/state"),
        value_fn=_target_time,
    ),
    WarpSensorDescription(
        key="limit_target_soc",
        translation_key="limit_target_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        has_fn=lambda d: "target_soc_pct" in d.limits_state,
        value_fn=lambda d: _limit_value(d, "target_soc_pct"),
    ),
    # --- diagnostics ---
    WarpSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: "uptime" in d.evse_low_level,
        value_fn=_uptime,
    ),
    WarpSensorDescription(
        key="charging_time",
        translation_key="charging_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: "charging_time" in d.evse_low_level,
        value_fn=lambda d: (
            int(d.evse_low_level["charging_time"] / 1000)
            if isinstance(d.evse_low_level.get("charging_time"), (int, float))
            else None
        ),
    ),
    WarpSensorDescription(
        key="error_state",
        translation_key="error_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(ERROR_STATE_MAP.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: ERROR_STATE_MAP.get(d.error_state, "unknown_error"),
    ),
    WarpSensorDescription(
        key="dc_fault_state",
        translation_key="dc_fault_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(DC_FAULT_STATE_MAP.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: "dc_fault_current_state" in d.evse,
        value_fn=lambda d: DC_FAULT_STATE_MAP.get(
            int(d.evse.get("dc_fault_current_state", 0)), "unknown_error"
        ),
    ),
    WarpSensorDescription(
        key="contactor_state",
        translation_key="contactor_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: "contactor_state" in d.evse,
        value_fn=lambda d: d.evse.get("contactor_state"),
    ),
    WarpSensorDescription(
        key="wifi_rssi",
        translation_key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: d.wifi.get("connection_state") == 3,
        value_fn=lambda d: d.wifi.get("sta_rssi"),
    ),
    WarpSensorDescription(
        key="ip_address",
        translation_key="ip_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: bool(d.ethernet) or bool(d.wifi),
        value_fn=_ip_address,
    ),
    WarpSensorDescription(
        key="ethernet_link",
        translation_key="ethernet_link",
        device_class=SensorDeviceClass.ENUM,
        options=list(CONNECTION_STATE_MAP.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: "connection_state" in d.ethernet,
        value_fn=lambda d: CONNECTION_STATE_MAP.get(
            int(d.ethernet.get("connection_state", 0)), "not_configured"
        ),
    ),
    WarpSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        has_fn=lambda d: "power_at_meter" in d.pm_low_level,
        value_fn=lambda d: d.pm_low_level.get("power_at_meter"),
    ),
    WarpSensorDescription(
        key="available_power",
        translation_key="available_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: "power_available" in d.pm_low_level,
        value_fn=lambda d: d.pm_low_level.get("power_available"),
    ),
    WarpSensorDescription(
        key="phases",
        translation_key="phases",
        device_class=SensorDeviceClass.ENUM,
        options=["one", "three"],
        has_fn=lambda d: "is_3phase" in d.pm_low_level,
        value_fn=_phases,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WarpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WARP sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        WarpSensorEntity(entry=entry, coordinator=coordinator, description=description)
        for description in DESCRIPTIONS
        if description.has_fn(coordinator.data)
    )


class WarpSensorEntity(WarpEntity, SensorEntity):
    """A WARP sensor."""

    entity_description: WarpSensorDescription

    @property
    def native_value(self) -> SensorValue:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
