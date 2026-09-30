"""Sensors for WARP chargers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CHARGER_STATE_MAP,
    IEC61851_STATE_MAP,
    METER_ID_ENERGY_IMPORT,
    METER_ID_POWER,
)
from .coordinator import WarpConfigEntry, WarpData
from .entity import WarpEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class WarpSensorDescription(SensorEntityDescription):
    """Describe a WARP sensor."""

    has_fn: Callable[[WarpData], bool] = lambda _: True
    value_fn: Callable[[WarpData], float | int | str | None]


DESCRIPTIONS: tuple[WarpSensorDescription, ...] = (
    WarpSensorDescription(
        key="charger_state",
        translation_key="charger_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(CHARGER_STATE_MAP.values()),
        icon="mdi:ev-station",
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
        has_fn=lambda d: METER_ID_POWER in d.meter_ids,
        value_fn=lambda d: d.power_w,
    ),
    WarpSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        has_fn=lambda d: METER_ID_ENERGY_IMPORT in d.meter_ids,
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
        and METER_ID_ENERGY_IMPORT in d.meter_ids,
        value_fn=lambda d: d.session_energy_kwh,
    ),
    WarpSensorDescription(
        key="ev_name",
        translation_key="ev_name",
        icon="mdi:car-electric",
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
    def native_value(self) -> float | int | str | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
