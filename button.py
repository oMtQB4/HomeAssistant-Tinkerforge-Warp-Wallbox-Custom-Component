"""Buttons for WARP chargers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import WarpApi
from .coordinator import WarpConfigEntry, WarpData
from .entity import WarpEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class WarpButtonDescription(ButtonEntityDescription):
    """Describe a WARP button."""

    has_fn: Callable[[WarpData], bool] = lambda _: True
    press_fn: Callable[[WarpApi], Awaitable[Any]]


DESCRIPTIONS: tuple[WarpButtonDescription, ...] = (
    WarpButtonDescription(
        key="start_charging",
        translation_key="start_charging",
        press_fn=lambda api: api.start_charging(),
    ),
    WarpButtonDescription(
        key="stop_charging",
        translation_key="stop_charging",
        press_fn=lambda api: api.stop_charging(),
    ),
    WarpButtonDescription(
        key="reboot",
        translation_key="reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=lambda api: api.reboot(),
    ),
    WarpButtonDescription(
        key="reset_dc_fault",
        translation_key="reset_dc_fault",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: "dc_fault_current_state" in d.evse,
        press_fn=lambda api: api.reset_dc_fault(),
    ),
    WarpButtonDescription(
        key="check_for_update",
        translation_key="check_for_update",
        device_class=ButtonDeviceClass.UPDATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        has_fn=lambda d: bool(d.fw_state),
        press_fn=lambda api: api.check_for_update(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WarpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WARP buttons."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        WarpButtonEntity(entry=entry, coordinator=coordinator, description=description)
        for description in DESCRIPTIONS
        if description.has_fn(coordinator.data)
    )


class WarpButtonEntity(WarpEntity, ButtonEntity):
    """A WARP button."""

    entity_description: WarpButtonDescription

    async def async_press(self) -> None:
        """Trigger the action."""
        await self._async_write(self.entity_description.press_fn(self.coordinator.api))
