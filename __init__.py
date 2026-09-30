"""Integration for Tinkerforge WARP chargers."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.typing import ConfigType

from .api import WarpApi, WarpAuthError, WarpConnectionError, WarpError
from .const import CONF_USE_WEBSOCKET, CONF_VERIFY_SSL, DOMAIN, LOGGER, T_METER_IDS
from .coordinator import WarpConfigEntry, WarpDataUpdateCoordinator, WarpRuntimeData
from .services import async_setup_services
from .ws_client import WarpWebSocket

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WarpConfigEntry) -> bool:
    """Set up a WARP charger from a config entry."""
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, False)
    client = get_async_client(hass, verify_ssl=verify_ssl)
    api = WarpApi(
        host=entry.data[CONF_HOST],
        client=client,
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
    )

    try:
        info = await api.get_info()
    except WarpAuthError as err:
        raise ConfigEntryAuthFailed from err
    except WarpConnectionError as err:
        raise ConfigEntryNotReady(
            f"Could not connect to WARP charger at {api.host}"
        ) from err
    except WarpError as err:
        raise ConfigEntryNotReady(f"WARP charger at {api.host}: {err}") from err

    meter_ids: list[int] = []
    try:
        ids = await api.get(T_METER_IDS)
        if isinstance(ids, list):
            meter_ids = [int(i) for i in ids]
    except WarpAuthError as err:
        raise ConfigEntryAuthFailed from err
    except WarpConnectionError as err:
        raise ConfigEntryNotReady(
            f"Could not connect to WARP charger at {api.host}"
        ) from err
    except WarpError as err:
        LOGGER.warning("Meter value ids unavailable, no meter sensors: %s", err)

    coordinator = WarpDataUpdateCoordinator(hass, entry, api, info, meter_ids)
    await coordinator.async_config_entry_first_refresh()

    ws: WarpWebSocket | None = None
    if entry.options.get(CONF_USE_WEBSOCKET, True):
        ws = WarpWebSocket(
            hass,
            entry,
            async_get_clientsession(hass, verify_ssl=verify_ssl),
            host=entry.data[CONF_HOST],
            username=entry.data.get(CONF_USERNAME),
            password=entry.data.get(CONF_PASSWORD),
            on_message=coordinator.handle_ws_message,
            on_connection=coordinator.handle_ws_connection,
        )
        coordinator.ws = ws
        ws.start()
        entry.async_on_unload(ws.stop)

    entry.runtime_data = WarpRuntimeData(
        coordinator=coordinator, api=api, info=info, ws=ws
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WarpConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
