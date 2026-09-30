"""Number entities for WARP chargers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WarpConfigEntry, WarpData
from .entity import WarpEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class WarpNumberDescription(NumberEntityDescription):
    """Describe a WARP number entity."""

    has_fn: Callable[[WarpData], bool] = lambda _: True
    value_fn: Callable[[WarpData], float | None]


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
        value_fn=lambda d: (
            None if d.external_current_ma is None else d.external_current_ma / 1000
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
        """Set the external current limit."""
        await self.coordinator.api.set_external_current(int(round(value * 1000)))
        await self.coordinator.async_request_refresh()
