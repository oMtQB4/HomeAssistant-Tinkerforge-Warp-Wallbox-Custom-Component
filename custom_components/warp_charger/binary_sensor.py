"""Binary sensors for WARP chargers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WarpConfigEntry, WarpData
from .entity import WarpEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class WarpBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a WARP binary sensor."""

    has_fn: Callable[[WarpData], bool] = lambda _: True
    is_on_fn: Callable[[WarpData], bool | None]


DESCRIPTIONS: tuple[WarpBinarySensorDescription, ...] = (
    WarpBinarySensorDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.PLUG,
        is_on_fn=lambda d: d.iec_state >= 1,
    ),
    WarpBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        is_on_fn=lambda d: d.iec_state == 2,
    ),
    WarpBinarySensorDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda d: d.error_state != 0,
    ),
    WarpBinarySensorDescription(
        key="websocket_connected",
        translation_key="websocket_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda d: d.ws_connected,
    ),
    WarpBinarySensorDescription(
        key="ntp_synced",
        translation_key="ntp_synced",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        has_fn=lambda d: "synced" in d.ntp,
        is_on_fn=lambda d: d.ntp.get("synced"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WarpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WARP binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        WarpBinarySensorEntity(
            entry=entry, coordinator=coordinator, description=description
        )
        for description in DESCRIPTIONS
        if description.has_fn(coordinator.data)
    )


class WarpBinarySensorEntity(WarpEntity, BinarySensorEntity):
    """A WARP binary sensor."""

    entity_description: WarpBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.is_on_fn(self.coordinator.data)
