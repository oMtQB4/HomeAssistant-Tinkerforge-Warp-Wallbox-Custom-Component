"""Async HTTP client for Tinkerforge WARP chargers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from typing import Any

import httpx

from .const import (
    LOGGER,
    MAX_CONCURRENCY,
    REQUEST_TIMEOUT,
    T_CHARGE_MODE,
    T_EXTERNAL_CURRENT,
    T_INFO_DISPLAY_NAME,
    T_INFO_NAME,
    T_INFO_VERSION,
    T_START_CHARGING,
    T_STOP_CHARGING,
    WRITE_METHOD,
)


class WarpError(Exception):
    """Base error for the WARP API."""


class WarpConnectionError(WarpError):
    """Raised when the charger is unreachable."""


class WarpAuthError(WarpError):
    """Raised when the charger rejects the credentials."""


class WarpNotFoundError(WarpError):
    """Raised when a topic does not exist on this charger."""


@dataclass(frozen=True)
class WarpDeviceInfo:
    """Static device information."""

    name: str
    uid: str
    type: str
    display_type: str
    firmware: str
    display_name: str


def normalize_host(raw: str) -> str:
    """Strip scheme and trailing slashes from a user supplied host."""
    host = raw.strip()
    for prefix in ("https://", "http://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
    return host.rstrip("/")


class WarpApi:
    """Thin client around the WARP HTTP API."""

    def __init__(
        self,
        *,
        host: str,
        client: httpx.AsyncClient,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize the client."""
        self.host = normalize_host(host)
        self.base_url = f"https://{self.host}"
        self._client = client
        self._auth = (
            httpx.DigestAuth(username, password) if username and password else None
        )
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def _request(
        self, method: str, topic: str, *, content: str | None = None
    ) -> Any:
        """Perform a request and decode the response."""
        url = f"{self.base_url}/{topic}"
        headers = {"Content-Type": "application/json"} if content is not None else None
        try:
            async with self._semaphore:
                resp = await self._client.request(
                    method,
                    url,
                    content=content,
                    headers=headers,
                    auth=self._auth,
                    follow_redirects=True,
                    timeout=REQUEST_TIMEOUT,
                )
        except (httpx.TransportError, httpx.TimeoutException) as err:
            raise WarpConnectionError(f"{method} {topic}: {err}") from err

        if resp.status_code == 401:
            raise WarpAuthError(f"{topic}: authentication required or rejected")
        if resp.status_code == 404:
            raise WarpNotFoundError(topic)
        if resp.status_code >= 400:
            raise WarpError(
                f"{method} {topic}: HTTP {resp.status_code}: {resp.text[:200]}"
            )
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    async def get(self, topic: str) -> Any:
        """Read a topic."""
        return await self._request("GET", topic)

    async def put(self, topic: str, payload: Any) -> None:
        """Write a JSON payload to a topic."""
        LOGGER.debug("%s %s <- %s", WRITE_METHOD, topic, payload)
        await self._request(WRITE_METHOD, topic, content=json.dumps(payload))

    async def command(self, topic: str) -> None:
        """Trigger an action topic (requires a literal null body)."""
        LOGGER.debug("%s %s <- null", WRITE_METHOD, topic)
        await self._request(WRITE_METHOD, topic, content="null")

    async def get_info(self) -> WarpDeviceInfo:
        """Fetch static device information."""
        name = await self.get(T_INFO_NAME)
        version = await self.get(T_INFO_VERSION)
        if not isinstance(name, dict) or not isinstance(version, dict):
            raise WarpError("Unexpected response from info topics")
        display_name = ""
        try:
            dn = await self.get(T_INFO_DISPLAY_NAME)
            if isinstance(dn, dict):
                display_name = str(dn.get("display_name", ""))
        except WarpError as err:
            LOGGER.debug("info/display_name unavailable: %s", err)
        return WarpDeviceInfo(
            name=str(name.get("name", "")),
            uid=str(name.get("uid", "")),
            type=str(name.get("type", "warp")),
            display_type=str(name.get("display_type", "WARP Charger")),
            firmware=str(version.get("firmware", "")),
            display_name=display_name,
        )

    async def set_charge_mode(self, mode: int) -> None:
        """Set the power manager charge mode."""
        await self.put(T_CHARGE_MODE, {"mode": mode})

    async def set_external_current(self, current_ma: int) -> None:
        """Set the external control current limit in mA."""
        await self.put(T_EXTERNAL_CURRENT, {"current": current_ma})

    async def start_charging(self) -> None:
        """Start charging (like pressing the button)."""
        await self.command(T_START_CHARGING)

    async def stop_charging(self) -> None:
        """Stop charging (like pressing the button)."""
        await self.command(T_STOP_CHARGING)
