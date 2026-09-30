"""Services for the WARP Charger integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .api import WarpError
from .const import (
    CHARGE_MODE_MAP,
    CHARGE_MODE_REVERSE_MAP,
    DOMAIN,
    DURATION_LIMIT_MAP,
    DURATION_LIMIT_REVERSE_MAP,
    T_EXTERNAL_CURRENT,
    T_LIMITS_OVERRIDE_DURATION,
    T_LIMITS_OVERRIDE_ENERGY,
)
from .coordinator import WarpRuntimeData

ATTR_DEVICE_ID = "device_id"
ATTR_MODE = "mode"
ATTR_ENERGY_KWH = "energy_kwh"
ATTR_DURATION = "duration"
ATTR_SOC_PCT = "soc_pct"
ATTR_OVERRIDE = "override"
ATTR_CURRENT_A = "current_a"
ATTR_TAG_ID = "tag_id"
ATTR_TAG_TYPE = "tag_type"
ATTR_ACTION = "action"

SERVICE_SET_CHARGE_MODE = "set_charge_mode"
SERVICE_SET_CHARGE_LIMITS = "set_charge_limits"
SERVICE_SET_EXTERNAL_CURRENT = "set_external_current"
SERVICE_INJECT_SOC = "inject_soc"
SERVICE_INJECT_NFC_TAG = "inject_nfc_tag"

_DEVICE = {vol.Required(ATTR_DEVICE_ID): cv.string}

SCHEMA_SET_CHARGE_MODE = vol.Schema(
    {**_DEVICE, vol.Required(ATTR_MODE): vol.In(list(CHARGE_MODE_MAP.values()))}
)
SCHEMA_SET_CHARGE_LIMITS = vol.Schema(
    {
        **_DEVICE,
        vol.Optional(ATTR_ENERGY_KWH): vol.All(vol.Coerce(float), vol.Range(min=0, max=1000)),
        vol.Optional(ATTR_DURATION): vol.In(list(DURATION_LIMIT_MAP.values())),
        vol.Optional(ATTR_SOC_PCT): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional(ATTR_OVERRIDE, default=False): cv.boolean,
    }
)
SCHEMA_SET_EXTERNAL_CURRENT = vol.Schema(
    {
        **_DEVICE,
        vol.Required(ATTR_CURRENT_A): vol.All(
            vol.Coerce(float), vol.Any(0, vol.Range(min=6, max=32))
        ),
    }
)
SCHEMA_INJECT_SOC = vol.Schema(
    {**_DEVICE, vol.Required(ATTR_SOC_PCT): vol.All(vol.Coerce(float), vol.Range(min=0, max=100))}
)
SCHEMA_INJECT_NFC_TAG = vol.Schema(
    {
        **_DEVICE,
        vol.Required(ATTR_TAG_ID): cv.string,
        vol.Optional(ATTR_TAG_TYPE, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)),
        vol.Optional(ATTR_ACTION, default="toggle"): vol.In(["toggle", "start", "stop"]),
    }
)


def _runtime_for_device(hass: HomeAssistant, device_id: str) -> WarpRuntimeData:
    """Resolve a device id to the loaded runtime data of its config entry."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="device_not_found"
        )
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            continue
        if entry.state is not ConfigEntryState.LOADED:
            break
        runtime = getattr(entry, "runtime_data", None)
        if isinstance(runtime, WarpRuntimeData):
            return runtime
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="device_not_loaded"
    )


async def _call(coro: Any) -> None:
    try:
        await coro
    except WarpError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"error": str(err)},
        ) from err


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services."""

    async def set_charge_mode(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[ATTR_DEVICE_ID])
        await _call(
            runtime.api.set_charge_mode(CHARGE_MODE_REVERSE_MAP[call.data[ATTR_MODE]])
        )
        await runtime.coordinator.async_request_refresh()

    async def set_charge_limits(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[ATTR_DEVICE_ID])
        data = call.data
        if not any(k in data for k in (ATTR_ENERGY_KWH, ATTR_DURATION, ATTR_SOC_PCT)):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_limit_given"
            )
        if data[ATTR_OVERRIDE]:
            if ATTR_SOC_PCT in data:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="soc_override_unsupported"
                )
            if ATTR_ENERGY_KWH in data:
                await _call(
                    runtime.api.put(
                        T_LIMITS_OVERRIDE_ENERGY,
                        {"energy_wh": int(round(data[ATTR_ENERGY_KWH] * 1000))},
                    )
                )
            if ATTR_DURATION in data:
                await _call(
                    runtime.api.put(
                        T_LIMITS_OVERRIDE_DURATION,
                        {"duration": DURATION_LIMIT_REVERSE_MAP[data[ATTR_DURATION]]},
                    )
                )
        else:
            patch: dict[str, Any] = {}
            if ATTR_ENERGY_KWH in data:
                patch["energy_wh"] = int(round(data[ATTR_ENERGY_KWH] * 1000))
            if ATTR_DURATION in data:
                patch["duration"] = DURATION_LIMIT_REVERSE_MAP[data[ATTR_DURATION]]
            if ATTR_SOC_PCT in data:
                patch["soc_pct"] = data[ATTR_SOC_PCT]
            current = runtime.coordinator.data.limits_default or None
            await _call(runtime.api.set_default_limits(patch, current))
        await runtime.coordinator.async_request_refresh()

    async def set_external_current(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[ATTR_DEVICE_ID])
        await _call(
            runtime.api.put(
                T_EXTERNAL_CURRENT,
                {"current": int(round(call.data[ATTR_CURRENT_A] * 1000))},
            )
        )
        await runtime.coordinator.async_request_refresh()

    async def inject_soc(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[ATTR_DEVICE_ID])
        await _call(runtime.api.inject_soc(call.data[ATTR_SOC_PCT]))

    async def inject_nfc_tag(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[ATTR_DEVICE_ID])
        await _call(
            runtime.api.inject_nfc_tag(
                call.data[ATTR_TAG_ID], call.data[ATTR_TAG_TYPE], call.data[ATTR_ACTION]
            )
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_CHARGE_MODE, set_charge_mode, schema=SCHEMA_SET_CHARGE_MODE
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_CHARGE_LIMITS, set_charge_limits, schema=SCHEMA_SET_CHARGE_LIMITS
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_EXTERNAL_CURRENT,
        set_external_current,
        schema=SCHEMA_SET_EXTERNAL_CURRENT,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_INJECT_SOC, inject_soc, schema=SCHEMA_INJECT_SOC
    )
    hass.services.async_register(
        DOMAIN, SERVICE_INJECT_NFC_TAG, inject_nfc_tag, schema=SCHEMA_INJECT_NFC_TAG
    )
