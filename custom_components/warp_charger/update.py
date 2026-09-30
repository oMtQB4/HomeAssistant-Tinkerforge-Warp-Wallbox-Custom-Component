"""Firmware update entity for WARP chargers."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WarpConfigEntry, WarpDataUpdateCoordinator
from .entity import WarpEntity

PARALLEL_UPDATES = 1

RELEASE_URL = "https://docs.warp-charger.com/docs/changelog/"
_VERSION_RE = re.compile(r"^(\d+)[._](\d+)[._](\d+)(?:[._]beta[._](\d+))?")


def normalize_version(raw: str | None) -> str | None:
    """Turn `2_13_5_deadbeef` / `2.13.4+hash` into `2.13.5` / `2.13.4`."""
    if not raw:
        return None
    match = _VERSION_RE.match(raw)
    if not match:
        return raw.split("+")[0]
    major, minor, patch, beta = match.groups()
    version = f"{major}.{minor}.{patch}"
    return f"{version}-beta{beta}" if beta else version


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WarpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the firmware update entity."""
    coordinator = entry.runtime_data.coordinator
    if coordinator.data.fw_state:
        async_add_entities([WarpFirmwareUpdate(entry=entry, coordinator=coordinator)])


class WarpFirmwareUpdate(WarpEntity, UpdateEntity):
    """Firmware update entity backed by firmware_update/state."""

    _attr_translation_key = "firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )
    _attr_release_url = RELEASE_URL
    _attr_title = "WARP Firmware"

    def __init__(
        self, *, entry: WarpConfigEntry, coordinator: WarpDataUpdateCoordinator
    ) -> None:
        """Initialize."""
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            description=UpdateEntityDescription(key="firmware"),
        )

    @property
    def installed_version(self) -> str | None:
        """Running firmware."""
        return normalize_version(self.coordinator.info.firmware)

    @property
    def latest_version(self) -> str | None:
        """Newest firmware the charger knows about."""
        raw = self.coordinator.data.fw_state.get("update_version")
        latest = normalize_version(raw if isinstance(raw, str) else None)
        return latest or self.installed_version

    @property
    def in_progress(self) -> bool:
        """Whether an installation is running."""
        progress = self.coordinator.data.fw_install_state.get("progress")
        return isinstance(progress, int) and 0 < progress < 100

    @property
    def update_percentage(self) -> int | None:
        """Installation progress."""
        progress = self.coordinator.data.fw_install_state.get("progress")
        if isinstance(progress, int) and 0 < progress < 100:
            return progress
        return None

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install the advertised firmware."""
        raw = self.coordinator.data.fw_state.get("update_version")
        if not isinstance(raw, str) or not raw:
            return
        await self._async_write(self.coordinator.api.install_firmware(raw))
