"""WebSocket client for the WARP charger push API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import hashlib
import re
import secrets
from typing import Any, Final

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.json import json_loads

from .api import WarpAuthError, WarpConnectionError, normalize_host
from .const import (
    DOMAIN,
    LOGGER,
    T_KEEP_ALIVE,
    WS_BACKOFF_MAX,
    WS_BACKOFF_MIN,
    WS_KEEPALIVE_TIMEOUT,
    WS_PATH,
)

type MessageCallback = Callable[[str, Any], None]
type ConnectionCallback = Callable[[bool], None]

_CHALLENGE_RE: Final = re.compile(r'(\w+)=(?:"([^"]*)"|([^,\s]*))')


def _parse_challenge(header: str) -> dict[str, str]:
    """Parse a `Digest realm="…", qop="auth", nonce="…"` header."""
    if header.lower().startswith("digest "):
        header = header[7:]
    return {k: (quoted or bare) for k, quoted, bare in _CHALLENGE_RE.findall(header)}


def _md5(value: str) -> str:
    return hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()


def digest_header(
    method: str, uri: str, challenge_header: str, username: str, password: str
) -> str:
    """Build an RFC 2617 Authorization header (MD5, qop=auth) for one request."""
    challenge = _parse_challenge(challenge_header)
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")
    qop = "auth" if "auth" in challenge.get("qop", "") else None
    nc = "00000001"
    cnonce = secrets.token_hex(8)
    ha1 = _md5(f"{username}:{realm}:{password}")
    ha2 = _md5(f"{method}:{uri}")
    if qop:
        response = _md5(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}")
    else:
        response = _md5(f"{ha1}:{nonce}:{ha2}")
    parts = [
        f'username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        f'response="{response}"',
        "algorithm=MD5",
    ]
    if qop:
        parts += [f"qop={qop}", f"nc={nc}", f'cnonce="{cnonce}"']
    if opaque := challenge.get("opaque"):
        parts.append(f'opaque="{opaque}"')
    return "Digest " + ", ".join(parts)


class WarpWebSocket:
    """Maintain a WebSocket to the charger and forward pushed states."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        session: aiohttp.ClientSession,
        *,
        host: str,
        username: str | None,
        password: str | None,
        on_message: MessageCallback,
        on_connection: ConnectionCallback,
    ) -> None:
        """Initialize the client."""
        self._hass = hass
        self._entry = entry
        self._session = session
        self._url = f"wss://{normalize_host(host)}{WS_PATH}"
        self._username = username
        self._password = password
        self._on_message = on_message
        self._on_connection = on_connection
        self._task: asyncio.Task[None] | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._stopping = False
        self.connected = False
        self.auth_failed = False

    def start(self) -> None:
        """Start the background connection loop."""
        if self._task is None:
            self._stopping = False
            self._task = self._entry.async_create_background_task(
                self._hass, self._run(), name=f"{DOMAIN} websocket {self._url}"
            )

    async def stop(self) -> None:
        """Stop the loop and close the socket."""
        self._stopping = True
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._set_connected(False)

    async def _connect(self) -> aiohttp.ClientWebSocketResponse:
        """Upgrade with a Digest handshake: bare request -> 401 -> retry."""
        headers: dict[str, str] = {}
        for attempt in (0, 1):
            try:
                return await self._session.ws_connect(
                    self._url,
                    headers=headers,
                    heartbeat=None,
                    autoping=True,
                    receive_timeout=WS_KEEPALIVE_TIMEOUT,
                )
            except aiohttp.WSServerHandshakeError as err:
                challenge = (err.headers or {}).get("WWW-Authenticate", "")
                if (
                    err.status == 401
                    and attempt == 0
                    and self._username
                    and challenge.lower().startswith("digest")
                ):
                    headers = {
                        "Authorization": digest_header(
                            "GET",
                            WS_PATH,
                            challenge,
                            self._username,
                            self._password or "",
                        )
                    }
                    continue
                if err.status == 401:
                    raise WarpAuthError("websocket: credentials rejected") from err
                raise WarpConnectionError(
                    f"websocket handshake: HTTP {err.status}"
                ) from err
            except (aiohttp.ClientError, TimeoutError, OSError) as err:
                raise WarpConnectionError(f"websocket: {err}") from err
        raise WarpConnectionError("websocket: handshake failed")

    async def _run(self) -> None:
        backoff = WS_BACKOFF_MIN
        while not self._stopping:
            try:
                self._ws = await self._connect()
            except WarpAuthError as err:
                # The HTTP poll path raises ConfigEntryAuthFailed -> reauth.
                LOGGER.warning("WARP websocket authentication failed: %s", err)
                self.auth_failed = True
                return
            except WarpConnectionError as err:
                LOGGER.debug(
                    "WARP websocket connect failed (%s); retry in %.0fs", err, backoff
                )
                await asyncio.sleep(backoff + secrets.randbelow(1000) / 1000)
                backoff = min(backoff * 2, WS_BACKOFF_MAX)
                continue

            self._set_connected(True)
            got_frame = False
            try:
                got_frame = await self._read_loop(self._ws)
            except TimeoutError:
                LOGGER.debug(
                    "WARP websocket: no frame for %.0fs, reconnecting",
                    WS_KEEPALIVE_TIMEOUT,
                )
            except aiohttp.ClientError as err:
                LOGGER.debug("WARP websocket read error: %s", err)
            finally:
                ws, self._ws = self._ws, None
                if ws is not None and not ws.closed:
                    await ws.close()
                self._set_connected(False)
            if got_frame:
                backoff = WS_BACKOFF_MIN
            if not self._stopping:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, WS_BACKOFF_MAX)

    async def _read_loop(self, ws: aiohttp.ClientWebSocketResponse) -> bool:
        got_frame = False
        while True:
            msg = await ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                got_frame = True
                self._handle_text(msg.data)
            elif msg.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                LOGGER.debug("WARP websocket closed: %s %s", msg.type, ws.exception())
                return got_frame

    @callback
    def _handle_text(self, text: str) -> None:
        """Frames are NDJSON: one or more `{"topic":…,"payload":…}` lines."""
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json_loads(line)
            except ValueError:
                LOGGER.debug("WARP websocket: bad JSON line %.80s", line)
                continue
            if not isinstance(obj, dict) or "topic" not in obj:
                continue
            topic = obj["topic"]
            if topic == T_KEEP_ALIVE:
                continue
            self._on_message(topic, obj.get("payload"))

    @callback
    def _set_connected(self, value: bool) -> None:
        if value != self.connected:
            self.connected = value
            LOGGER.info("WARP websocket %s", "connected" if value else "disconnected")
            self._on_connection(value)
