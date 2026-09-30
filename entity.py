"""Base entity for the WARP Charger integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
