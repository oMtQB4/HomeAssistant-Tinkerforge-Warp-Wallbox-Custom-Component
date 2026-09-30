"""Buttons for WARP chargers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import WarpApi
from .coordinator import WarpConfigEntry
from .entity import WarpEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class WarpButtonDescription(ButtonEntityDescription):
    """Describe a WARP button."""

    press_fn: Callable[[WarpApi], Awaitable[None]]


DESCRIPTIONS: tuple[WarpButtonDescription, ...] = (
    WarpButtonDescription(
        key="start_charging",
        translation_key="start_charging",
        icon="mdi:play",
        press_fn=lambda api: api.start_charging(),
    ),
    WarpButtonDescription(
        key="stop_charging",
        translation_key="stop_charging",
        icon="mdi:stop",
        press_fn=lambda api: api.stop_charging(),
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
    )


class WarpButtonEntity(WarpEntity, ButtonEntity):
    """A WARP button."""

    entity_description: WarpButtonDescription

    async def async_press(self) -> None:
        """Trigger the action."""
        await self.entity_description.press_fn(self.coordinator.api)
        await self.coordinator.async_request_refresh()
