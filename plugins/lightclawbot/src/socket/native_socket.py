"""
LightClaw native WebSocket connection loop + pending ACK table.
Mirrors: src/socket/native-socket.ts

协议层职责（"哑"传输）：
    - 连接 / 重连 / 心跳 / 收发
    - 收到帧 → _handle_raw() 同步派发，绝不 await 业务
    - 内置 pending ACK 表：_ws_emit_with_timeout() → callback
    - 断线 → _flush_pending_acks(error) 一次性回调所有挂起
"""

import asyncio
import json
import logging
import random
import urllib.parse
from typing import Callable, Dict, Optional, Tuple

from ..config import (
    API_PATH_TICKET,
    EMIT_ACK_TIMEOUT,
    RECONNECT_DELAY_BASE,
    RECONNECT_DELAY_MAX,
    SOCKET_PATH,
)

logger = logging.getLogger(__name__)


class NativeSocketMixin:
    """
    Mixin providing the WebSocket transport layer.
    Mirrors: NativeSocketClient in native-socket.ts

    Provides to upper layers:
        _ws_emit(event, data)                              — fire-and-forget
        _ws_emit_with_timeout(event, data, timeout_ms, cb) — ACK + timeout
        _on_ws_ack(related_msg_id)                         — dispatch ACK
        _flush_pending_acks(err)                           — disconnect cleanup

    Requires (set by LightClawAdapter.__init__):
        self._ws_base_url: str
        self._api_base_url: str
        self._api_keys: list[str]
        self._session: aiohttp.ClientSession
        self._reliable: ReliableEmitter
        self._stopped: bool
        self._socket_id: str
        self._first_connect_event: asyncio.Event

    Must implement (in LightClawAdapter):
        async _handle_raw(raw: str) -> None
        _mark_connected() -> None
        _mark_disconnected() -> None
    """

    # ------------------------------------------------------------------
    # Pending ACK table (mirrors TS _pendingAcks)
    # ------------------------------------------------------------------
    # { pending_key: (timer_handle, callback) }
    _pending_acks: Dict[str, Tuple[asyncio.TimerHandle, Callable]]

    def _init_pending_acks(self) -> None:
        """Must be called from __init__."""
        self._pending_acks = {}

    def _ws_emit(self, event: str, data: dict) -> None:
        """Fire-and-forget send.  Synchronous, never blocks.

        Mirrors TS ``socket.emit(event, data)``  — send and return
        immediately without registering an ACK callback.
        """
        ws = self._ws
        if ws is None or getattr(ws, "closed", True):
            return
        try:
            # aiohttp ws.send_json is a coroutine, but we want sync.
            # Schedule the write without awaiting.
            asyncio.ensure_future(ws.send_json({"event": event, "data": data}))
        except Exception as exc:
            logger.debug("[lightclaw] _ws_emit send failed: %s", exc)

    def _ws_emit_with_timeout(
        self,
        event: str,
        data: dict,
        timeout_ms: int,
        callback: Callable[[Optional[Exception]], None],
    ) -> None:
        """Send + register ACK callback with timeout.  Synchronous return.

        Mirrors TS ``socket.timeout(ms).emit(event, data, callback)``.

        The *callback* receives ``None`` on ACK success, or an ``Exception``
        on timeout / disconnect.  It is invoked exactly once.
        """
        ws = self._ws
        if ws is None or getattr(ws, "closed", True):
            callback(ConnectionError("not connected"))
            return

        # pending_key = data["msgId"] (matches TS: server ACK relatedMsgId = msgId)
        pending_key = data.get("msgId") or f"_ack_{id(data)}"

        # If a retry for the same msgId is already pending, cancel old timer
        existing = self._pending_acks.get(pending_key)
        if existing is not None:
            existing[0].cancel()

        loop = asyncio.get_running_loop()

        def _on_timeout() -> None:
            entry = self._pending_acks.pop(pending_key, None)
            if entry is not None:
                callback(TimeoutError("ACK timeout"))

        timer = loop.call_later(timeout_ms / 1000.0, _on_timeout)
        self._pending_acks[pending_key] = (timer, callback)

        # Send the frame
        try:
            asyncio.ensure_future(ws.send_json({"event": event, "data": data}))
        except Exception as exc:
            # Send failed — clean up and callback immediately
            timer.cancel()
            self._pending_acks.pop(pending_key, None)
            callback(ConnectionError(f"send failed: {exc}"))

    def _on_ws_ack(self, related_msg_id: str) -> None:
        """Dispatch an incoming ACK.  Mirrors TS ``_handleMessage`` ACK branch.

        Called from ``_handle_raw`` when ``event == "message:ack"``.
        Looks up the pending table and invokes the callback with ``None``.
        """
        entry = self._pending_acks.pop(related_msg_id, None)
        if entry is None:
            logger.debug(
                "[lightclaw] ACK for unknown msgId=%s (already resolved)",
                related_msg_id,
            )
            return
        timer, callback = entry
        timer.cancel()
        callback(None)

    def _flush_pending_acks(self, err: Exception) -> None:
        """Disconnect cleanup — resolve all pending callbacks with *err*.

        Mirrors TS ``_flushPendingAcks``.
        """
        pending = self._pending_acks
        self._pending_acks = {}
        for timer, callback in pending.values():
            timer.cancel()
            try:
                callback(err)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Ticket & URL
    # ------------------------------------------------------------------

    async def _fetch_ticket(self) -> str:
        """Fetch a fresh connection ticket. Called before each WS connect."""
        import aiohttp

        key = self._api_keys[0]
        url = f"{self._api_base_url}{API_PATH_TICKET}"
        headers = {"authorization": f"Bearer {key}", "x-product": "channel"}

        async with self._session.post(
            url, headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"POST /cgi/ticket HTTP {resp.status}")
            data = await resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"POST /cgi/ticket error: {data.get('message')}")
            ticket = data.get("data", {}).get("ticket", "")
            if not ticket:
                logger.warning("[lightclaw] /cgi/ticket returned empty ticket, connecting without it")
            return ticket

    def _build_ws_url(self, ticket: str) -> str:
        """Construct full WS URL with ticket query param."""
        base  = self._ws_base_url.rstrip("/")
        path  = SOCKET_PATH
        query = f"?ticket={urllib.parse.quote(ticket, safe='')}&enableMultiLogin=false" if ticket else ""
        return f"{base}{path}{query}"

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _connection_loop(self) -> None:
        """Reconnect loop with exponential backoff."""
        attempts = 0
        while not self._stopped:
            try:
                ticket = await self._fetch_ticket()
                ws_url = self._build_ws_url(ticket)
                logger.info("[lightclaw] Connecting to %s", ws_url[:80])
                await self._run_once(ws_url)
                attempts = 0   # successful session resets counter
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("[lightclaw] Connection session ended: %s", exc)

            if self._stopped:
                return

            attempts += 1
            base_delay = min(RECONNECT_DELAY_BASE * (2 ** (attempts - 1)), RECONNECT_DELAY_MAX)
            delay = base_delay * (0.8 + random.random() * 0.4)
            logger.info("[lightclaw] Reconnecting in %.1fs (attempt %d)", delay, attempts)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

    async def _run_once(self, ws_url: str) -> None:
        """Single WebSocket session: connect -> receive loop -> cleanup."""
        import aiohttp

        ws = await self._session.ws_connect(
            ws_url,
            heartbeat=30,
            timeout=aiohttp.ClientTimeout(total=None, connect=15),
        )
        self._ws = ws

        try:
            self._socket_id = ""
            self._mark_connected()
            self._first_connect_event.set()
            if self._reliable:
                self._reliable.resume()

            async for raw_msg in ws:
                if self._stopped:
                    break
                if raw_msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        await self._handle_raw(raw_msg.data)
                    except Exception as exc:
                        logger.error("[lightclaw] handle_raw error: %s", exc)
                elif raw_msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        finally:
            self._ws = None
            # Flush all pending ACK callbacks with disconnect error
            self._flush_pending_acks(ConnectionError("disconnect"))
            if self._reliable:
                self._reliable.pause()
            if not ws.closed:
                try:
                    await ws.close()
                except Exception:
                    pass
            self._mark_disconnected()
            logger.info("[lightclaw] Disconnected (socket_id=%s)", self._socket_id or "?")
