"""Charge mode select for WARP chargers."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CHARGE_MODE_MAP, CHARGE_MODE_REVERSE_MAP
from .coordinator import WarpConfigEntry, WarpDataUpdateCoordinator
from .entity import WarpEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WarpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the charge mode select."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([WarpChargeModeSelect(entry=entry, coordinator=coordinator)])


class WarpChargeModeSelect(WarpEntity, SelectEntity):
    """Select entity for the power manager charge mode."""

    _attr_translation_key = "charge_mode"
    _attr_icon = "mdi:ev-station"

    def __init__(
        self, *, entry: WarpConfigEntry, coordinator: WarpDataUpdateCoordinator
    ) -> None:
        """Initialize the select."""
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            description=SelectEntityDescription(key="charge_mode"),
        )

    @property
    def options(self) -> list[str]:
        """Return the modes the charger currently supports."""
        data = self.coordinator.data
        options = [
            CHARGE_MODE_MAP[m]
            for m in data.supported_charge_modes
            if m in CHARGE_MODE_MAP
        ]
        current = CHARGE_MODE_MAP.get(data.charge_mode)
        if current and current not in options:
            options.append(current)
        return options or list(CHARGE_MODE_MAP.values())

    @property
    def current_option(self) -> str | None:
        """Return the active charge mode."""
        return CHARGE_MODE_MAP.get(self.coordinator.data.charge_mode)

    async def async_select_option(self, option: str) -> None:
        """Change the charge mode."""
        await self.coordinator.api.set_charge_mode(CHARGE_MODE_REVERSE_MAP[option])
        await self.coordinator.async_request_refresh()
