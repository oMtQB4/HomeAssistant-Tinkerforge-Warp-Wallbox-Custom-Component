"""Base entity for the WARP Charger integration."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import WarpError
from .const import DOMAIN
from .coordinator import WarpConfigEntry, WarpDataUpdateCoordinator


class WarpEntity(CoordinatorEntity[WarpDataUpdateCoordinator]):
    """Defines a WARP charger entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        entry: WarpConfigEntry,
        coordinator: WarpDataUpdateCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator=coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

        info = coordinator.info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, info.uid)},
            manufacturer="Tinkerforge",
            model=info.display_type,
            name=f"{info.type.upper()} Charger",
            sw_version=info.firmware,
            serial_number=info.uid,
            configuration_url=f"https://{entry.data[CONF_HOST]}",
        )

    async def _async_write(self, coro: Awaitable[Any]) -> None:
        """Run a write against the charger and refresh, translating errors."""
        try:
            await coro
        except WarpError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if not self.coordinator.ws_connected:
            await self.coordinator.async_request_refresh()
