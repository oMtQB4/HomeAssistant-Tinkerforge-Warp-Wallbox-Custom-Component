"""Number entities for WARP chargers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
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

from .api import WarpApi
from .const import T_PM_CONFIG
from .coordinator import WarpConfigEntry, WarpData
from .entity import WarpEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class WarpNumberDescription(NumberEntityDescription):
    """Describe a WARP number entity."""

    has_fn: Callable[[WarpData], bool] = lambda _: True
    value_fn: Callable[[WarpData], float | None]
    set_fn: Callable[[WarpApi, WarpData, float], Awaitable[Any]]


def _num(value: Any, scale: float = 1.0) -> float | None:
    return value / scale if isinstance(value, (int, float)) else None


DESCRIPTIONS: tuple[WarpNumberDescription, ...] = (
    WarpNumberDescription(
        key="external_current",
        translation_key="external_current",
        device_class=NumberDeviceClass.CURRENT,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=6,
        native_max_value=32,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        has_fn=lambda d: d.external_enabled,
        value_fn=lambda d: _num(d.external_current_ma, 1000),
        set_fn=lambda api, d, v: api.set_external_current(int(round(v * 1000))),
    ),
    WarpNumberDescription(
        key="energy_limit",
        translation_key="energy_limit",
        device_class=NumberDeviceClass.ENERGY,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=0,
        native_max_value=200,
        native_step=0.5,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        has_fn=lambda d: "energy_wh" in d.limits_default,
        value_fn=lambda d: _num(d.limits_default.get("energy_wh"), 1000),
        set_fn=lambda api, d, v: api.set_default_limits(
            {"energy_wh": int(round(v * 1000))}, d.limits_default
        ),
    ),
    WarpNumberDescription(
        key="soc_limit",
        translation_key="soc_limit",
        device_class=NumberDeviceClass.BATTERY,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.SLIDER,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        has_fn=lambda d: "soc_pct" in d.limits_default,
        value_fn=lambda d: _num(d.limits_default.get("soc_pct")),
        set_fn=lambda api, d, v: api.set_default_limits(
            {"soc_pct": int(round(v))}, d.limits_default
        ),
    ),
    WarpNumberDescription(
        key="guaranteed_power",
        translation_key="guaranteed_power",
        device_class=NumberDeviceClass.POWER,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=0,
        native_max_value=22000,
        native_step=10,
        native_unit_of_measurement=UnitOfPower.WATT,
        has_fn=lambda d: "guaranteed_power" in d.pm_config,
        value_fn=lambda d: _num(d.pm_config.get("guaranteed_power")),
        set_fn=lambda api, d, v: api.write_config(
            T_PM_CONFIG, {"guaranteed_power": int(round(v))}, d.pm_config
        ),
    ),
    WarpNumberDescription(
        key="target_power_from_grid",
        translation_key="target_power_from_grid",
        device_class=NumberDeviceClass.POWER,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        native_min_value=-10000,
        native_max_value=10000,
        native_step=10,
        native_unit_of_measurement=UnitOfPower.WATT,
        has_fn=lambda d: "target_power_from_grid" in d.pm_config,
        value_fn=lambda d: _num(d.pm_config.get("target_power_from_grid")),
        set_fn=lambda api, d, v: api.write_config(
            T_PM_CONFIG, {"target_power_from_grid": int(round(v))}, d.pm_config
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WarpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WARP number entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        WarpNumberEntity(entry=entry, coordinator=coordinator, description=description)
        for description in DESCRIPTIONS
        if description.has_fn(coordinator.data)
    )


class WarpNumberEntity(WarpEntity, NumberEntity):
    """A WARP number entity."""

    entity_description: WarpNumberDescription

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        """Write the value."""
        await self._async_write(
            self.entity_description.set_fn(
                self.coordinator.api, self.coordinator.data, value
            )
        )
