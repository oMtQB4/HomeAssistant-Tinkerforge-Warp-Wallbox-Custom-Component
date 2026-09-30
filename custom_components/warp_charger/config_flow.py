"""Config flow for the WARP Charger integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import (
    WarpApi,
    WarpAuthError,
    WarpConnectionError,
    WarpDeviceInfo,
    normalize_host,
)
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_USE_WEBSOCKET,
    CONF_VERIFY_SSL,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_AUTH_FIELDS = {
    vol.Optional(CONF_USERNAME): TextSelector(
        TextSelectorConfig(autocomplete="username")
    ),
    vol.Optional(CONF_PASSWORD): TextSelector(
        TextSelectorConfig(type=TextSelectorType.PASSWORD)
    ),
    vol.Required(CONF_VERIFY_SSL, default=False): BooleanSelector(),
}

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): TextSelector(
            TextSelectorConfig(autocomplete="off")
        ),
        **_AUTH_FIELDS,
    }
)
STEP_AUTH_SCHEMA = vol.Schema(_AUTH_FIELDS)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USE_WEBSOCKET, default=True): BooleanSelector(),
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                step=1,
                unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
)


def _strip_empty_credentials(data: dict[str, Any]) -> dict[str, Any]:
    """Drop blank username/password so stored values survive a reconfigure."""
    return {
        k: v
        for k, v in data.items()
        if not (k in (CONF_USERNAME, CONF_PASSWORD) and not v)
    }


class WarpFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle the WARP Charger config flow."""

    VERSION = 1

    _discovery_host: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WarpOptionsFlow:
        """Return the options flow."""
        return WarpOptionsFlow()

    async def _async_validate(
        self, data: Mapping[str, Any]
    ) -> tuple[dict[str, str], WarpDeviceInfo | None]:
        """Try to reach the charger; return (errors, info)."""
        errors: dict[str, str] = {}
        client = get_async_client(self.hass, verify_ssl=data.get(CONF_VERIFY_SSL, False))
        api = WarpApi(
            host=data[CONF_HOST],
            client=client,
            username=data.get(CONF_USERNAME),
            password=data.get(CONF_PASSWORD),
        )
        try:
            info = await api.get_info()
        except WarpAuthError:
            errors["base"] = "invalid_auth"
        except WarpConnectionError:
            errors[CONF_HOST] = "cannot_connect"
        except Exception:  # noqa: BLE001
            LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return {}, info
        return errors, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_HOST] = normalize_host(user_input[CONF_HOST])
            user_input = _strip_empty_credentials(user_input)
            errors, info = await self._async_validate(user_input)
            if not errors and info:
                await self.async_set_unique_id(info.uid, raise_on_progress=False)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: user_input[CONF_HOST]}
                )
                return self.async_create_entry(
                    title=info.display_type or info.name, data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        props = discovery_info.properties
        model = str(props.get("model", ""))
        if "charger" not in model.lower():
            return self.async_abort(reason="not_supported")

        # The HA container has no mDNS resolver, so always use the IP address.
        host = str(discovery_info.ip_address)
        self._async_abort_entries_match({CONF_HOST: host})
        self._async_abort_entries_match(
            {CONF_HOST: discovery_info.hostname.rstrip(".")}
        )

        self._discovery_host = host
        name = discovery_info.name.split(".")[0]
        self.context["title_placeholders"] = {
            "name": f"{model or 'WARP Charger'} ({name})"
        }
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered charger."""
        errors: dict[str, str] = {}
        assert self._discovery_host is not None

        if user_input is not None:
            data = _strip_empty_credentials(
                {CONF_HOST: self._discovery_host, **user_input}
            )
            errors, info = await self._async_validate(data)
            if not errors and info:
                await self.async_set_unique_id(info.uid, raise_on_progress=False)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: self._discovery_host}
                )
                return self.async_create_entry(
                    title=info.display_type or info.name, data=data
                )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=self.add_suggested_values_to_schema(
                STEP_AUTH_SCHEMA, user_input
            ),
            description_placeholders={
                "name": self.context.get("title_placeholders", {}).get(
                    "name", "WARP Charger"
                ),
                "host": self._discovery_host,
            },
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            user_input = _strip_empty_credentials(user_input)
            data = {**reauth_entry.data, **user_input}
            errors, _info = await self._async_validate(data)
            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                STEP_AUTH_SCHEMA,
                user_input
                or {
                    CONF_USERNAME: reauth_entry.data.get(CONF_USERNAME),
                    CONF_VERIFY_SSL: reauth_entry.data.get(CONF_VERIFY_SSL, False),
                },
            ),
            description_placeholders={"host": reauth_entry.data[CONF_HOST]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host, credentials or TLS verification."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            user_input[CONF_HOST] = normalize_host(user_input[CONF_HOST])
            user_input = _strip_empty_credentials(user_input)
            data = {**entry.data, **user_input}
            errors, info = await self._async_validate(data)
            if not errors and info:
                await self.async_set_unique_id(info.uid)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        suggested = user_input or {
            k: v for k, v in entry.data.items() if k != CONF_PASSWORD
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, suggested),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )


class WarpOptionsFlow(OptionsFlowWithReload):
    """Options: push channel and fallback poll interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
