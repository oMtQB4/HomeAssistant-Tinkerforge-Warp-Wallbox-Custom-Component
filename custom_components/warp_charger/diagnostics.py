"""Diagnostics support for WARP Charger."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import T_USERS_CONFIG
from .coordinator import WarpConfigEntry

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "digest_hash", "mac", "username"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WarpConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    cache = dict(coordinator.cache)
    cache.pop(T_USERS_CONFIG, None)
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "info": asdict(runtime.info),
        "websocket": {
            "enabled": runtime.ws is not None,
            "connected": coordinator.ws_connected,
            "auth_failed": runtime.ws.auth_failed if runtime.ws else None,
        },
        "update_interval": str(coordinator.update_interval),
        "last_update_success": coordinator.last_update_success,
        "meter_ids": coordinator.data.meter_ids if coordinator.data else None,
        "cache": async_redact_data(cache, TO_REDACT),
    }
