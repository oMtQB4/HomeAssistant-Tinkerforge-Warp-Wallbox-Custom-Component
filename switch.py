"""Switches for WARP chargers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import WarpApi
from .const import T_AUTO_START, T_BOOST_MODE, T_EV_WAKEUP, T_PM_CONFIG
from .coordinator import WarpConfigEntry, WarpData
from .entity import WarpEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class WarpSwitchDescription(SwitchEntityDescription):
    """Describe a WARP switch."""

    has_fn: Callable[[WarpData], bool] = lambda _: True
    is_on_fn: Callable[[WarpData], bool | None]
    set_fn: Callable[[WarpApi, WarpData, bool], Awaitable[Any]]


DESCRIPTIONS: tuple[WarpSwitchDescription, ...] = (
    WarpSwitchDescription(
        key="auto_start_charging",
        translation_key="auto_start_charging",
        entity_category=EntityCategory.CONFIG,
        has_fn=lambda d: d.auto_start_charging is not None,
        is_on_fn=lambda d: d.auto_start_charging,
        set_fn=lambda api, d, on: api.put(T_AUTO_START, {"auto_start_charging": on}),
    ),
    WarpSwitchDescription(
        key="boost_mode",
        translation_key="boost_mode",
        entity_category=EntityCategory.CONFIG,
        has_fn=lambda d: d.boost_mode is not None,
        is_on_fn=lambda d: d.boost_mode,
        set_fn=lambda api, d, on: api.put(T_BOOST_MODE, {"enabled": on}),
    ),
    WarpSwitchDescription(
        key="ev_wakeup",
        translation_key="ev_wakeup",
        entity_category=EntityCategory.CONFIG,
        has_fn=lambda d: d.ev_wakeup is not None and "cp_disconnect" in d.features,
        is_on_fn=lambda d: d.ev_wakeup,
        set_fn=lambda api, d, on: api.put(T_EV_WAKEUP, {"enabled": on}),
    ),
    WarpSwitchDescription(
        key="excess_charging",
        translation_key="excess_charging",
        entity_category=EntityCategory.CONFIG,
        has_fn=lambda d: "excess_charging_enable" in d.pm_config,
        is_on_fn=lambda d: d.pm_config.get("excess_charging_enable"),
        set_fn=lambda api, d, on: api.write_config(
            T_PM_CONFIG, {"excess_charging_enable": on}, d.pm_config
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WarpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WARP switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        WarpSwitchEntity(entry=entry, coordinator=coordinator, description=description)
        for description in DESCRIPTIONS
        if description.has_fn(coordinator.data)
    )


class WarpSwitchEntity(WarpEntity, SwitchEntity):
    """A WARP switch."""

    entity_description: WarpSwitchDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.is_on_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self._async_write(
            self.entity_description.set_fn(
                self.coordinator.api, self.coordinator.data, True
            )
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self._async_write(
            self.entity_description.set_fn(
                self.coordinator.api, self.coordinator.data, False
            )
        )
