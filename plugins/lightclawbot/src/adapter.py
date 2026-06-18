"""
LightClaw adapter — main coordinator class and module singleton.
Mirrors: src/gateway.ts
"""

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional

from gateway.platforms.base import BasePlatformAdapter
from gateway.config import PlatformConfig

from .config import (
    API_PATH_TICKET,
    DEFAULT_API_BASE_URL,
    DEFAULT_WS_BASE_URL,
    EVENT_HANDSHAKE,
    EVENT_HISTORY_REQUEST,
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_PRIVATE,
    EVENT_SESSIONS_REQUEST,
    FileDownloadStatus,
    KIND_FILE_DOWNLOAD,
    generate_msg_id,
)
from .socket.reliable_emitter import ReliableEmitter
from .socket.native_socket import NativeSocketMixin
from .inbound import InboundMixin
from .outbound import OutboundMixin
from .download_handler import DownloadHandlerMixin
from .tenancy import set_api_key_map
from .usage_tracker import SessionUsageTracker

logger = logging.getLogger(__name__)


class LightClawAdapter(
    NativeSocketMixin,
    InboundMixin,
    OutboundMixin,
    DownloadHandlerMixin,
    BasePlatformAdapter,
):
    """
    Hermes gateway adapter for LightClaw-compatible servers.

    Connects via native WebSocket (aiohttp), receives message:private events,
    dispatches them to Hermes AIAgent, and sends responses back.

    Protocol:
    - Auth:      POST /cgi/ticket  → { code:0, data:{ client:{ extra:'{"botId":"..."}' }, ticket:"..." } }
    - Transport: Native WebSocket  wss://<domain>/ws/agent?ticket=<ticket>&enableMultiLogin=false
    - Framing:   Raw JSON  { "event": "<name>", "data": {...} }
    - Handshake: server sends { "event": "__handshake__", "data": { "id": "<socket_id>" } }
    - ACK:       server sends { "event": "message:ack", "data": { "relatedMsgId": "<msgId>" } }
    """

    # Streaming mode: GatewayStreamConsumer sends first chunk via send(),
    # then updates via edit_message() with accumulated text, and finally
    # calls edit_message(finalize=True) to close the stream.
    SUPPORTS_MESSAGE_EDITING = True
    REQUIRES_EDIT_FINALIZE = True

    def __init__(self, config: PlatformConfig):
        from gateway.config import Platform
        super().__init__(config, Platform("lightclawbot"))

        extra = config.extra or {}

        # API key — single source: env LIGHTCLAW_API_KEY.
        # `extra.api_keys` (yaml list) is kept as a forward-compat hook for
        # future multi-tenant deployments; not used in current deployments.
        if extra.get("api_keys"):
            self._api_keys: List[str] = list(extra["api_keys"])
        else:
            single = os.getenv("LIGHTCLAW_API_KEY", "").strip()
            self._api_keys = [single] if single else []

        # Server URLs — default to config.py constants; env overrides are kept
        # as an operational escape hatch for private deployments / staging.
        self._ws_base_url: str  = os.getenv("LIGHTCLAW_WS_URL",       DEFAULT_WS_BASE_URL)
        self._api_base_url: str = os.getenv("LIGHTCLAW_API_BASE_URL", DEFAULT_API_BASE_URL)

        # Identity (resolved on connect, stable across reconnects)
        self._bot_client_id: str        = ""
        self._api_key_map: Dict[str, str] = {}   # uin → apiKey (populated during _resolve_identity)

        # Per-chat round msgId
        self._round_ids: Dict[str, str] = {}

        # Per-chat "last closed round" msgId.  Populated by stop_typing()
        # when it closes an active round; consumed by outbound.send() so
        # that any output arriving AFTER stop_typing but BEFORE the next
        # inbound (e.g. framework-routed attachment links) can reuse the
        # same msgId instead of opening a brand-new standalone round.
        # Cleared by inbound when a new turn begins.
        self._last_round_id: Dict[str, str] = {}

        # Per-chat flag: whether the current round has already emitted a
        # stream_chunk.  Used by OutboundMixin.send() to prepend "\n\n"
        # before non-first chunks so front-end concatenation matches the
        # visual breaks seen in the history view.
        self._round_has_content: Dict[str, bool] = {}

        # Per-chat snapshot of accumulated text (cursor-stripped) for
        # edit_message() delta computation in streaming mode.
        self._edit_snapshot: Dict[str, str] = {}

        # Per-chat agentId received from inbound messages (used by outbound to echo back)
        self._incoming_agent_ids: Dict[str, str] = {}

        # ── Token usage (per-turn delta over session-cumulative counters) ──
        # Snapshots Hermes' cumulative SQLite counters at turn start and
        # diffs them at turn end to derive this turn's consumption.  The
        # tracker is constructed below, once sessions_dir is resolved, so it
        # locates state.db from the same authoritative path the rest of the
        # plugin uses (never a hardcoded path / username).

        # Per-chat inbound msgId, echoed as `replyToMsgId` on the usage frame.
        self._round_reply_to: Dict[str, str] = {}

        # Per-chat guard: round msgId already emitted (stop_typing fires
        # multiple times per turn; we emit usage at most once).
        self._round_usage_emitted: Dict[str, str] = {}

        # Per-chat list of attachments seen on inbound messages.
        # Used by history persistence / outbound enrichment.  Entries are
        # dicts of shape {"name", "mimeType", "url"} where url is always
        # a `localfile://` URI (mirrors TS `publicMediaUrls`).
        self._inbound_attachments: Dict[str, list] = {}

        # Per-chat list of file paths extracted from write_file tool_start
        # messages during a turn.  Used by the model-independent fallback in
        # stop_typing() to auto-deliver files when the model omits MEDIA: tags.
        self._pending_file_paths: Dict[str, list] = {}

        # Per-chat set of absolute paths already delivered via send_document()
        # in the current turn (populated by the framework's MEDIA: →
        # _deliver_media_from_response path).  Used by _deliver_pending_files()
        # to avoid duplicate links.
        self._delivered_paths: Dict[str, set] = {}

        # Sessions directory for history reading
        hermes_home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
        self._sessions_dir: str = (
            extra.get("sessions_dir")
            or os.getenv("LIGHTCLAW_SESSIONS_DIR")
            or os.path.join(hermes_home, "sessions")
        )

        # Token usage tracker — resolves state.db relative to the sessions
        # dir above (state.db is its sibling), so it follows custom install
        # locations and never assumes a hardcoded path / username.
        self._usage_tracker: SessionUsageTracker = SessionUsageTracker(
            sessions_dir=self._sessions_dir,
        )

        # Per-agent system prompts (multi-agent support)
        # Configured in config.yaml → platforms.lightclaw.extra.agent_prompts
        self._agent_prompts: Dict[str, str] = extra.get("agent_prompts") or {}

        # Connection state
        self._stopped           = False
        self._socket_id: str    = ""
        self._ws                = None          # aiohttp.ClientWebSocketResponse
        self._session           = None          # aiohttp.ClientSession
        self._connection_task: Optional[asyncio.Task] = None
        self._reliable: Optional[ReliableEmitter]     = None
        self._first_connect_event: asyncio.Event      = asyncio.Event()

        # Pending ACK table (owned by NativeSocketMixin)
        self._init_pending_acks()

    # ------------------------------------------------------------------
    # Identity resolution
    # ------------------------------------------------------------------

    async def _resolve_identity(self) -> None:
        """
        POST /cgi/ticket for each API key to get botClientId and the tenant's uin.

        Response shape::

            { code: 0,
              data: {
                id: "<uin>",                               # tenant user id
                client: { extra: '{"botId":"<botId>"}' },  # JSON string
                ticket: "..."
              }
            }

        Populates:
            self._bot_client_id   — any non-empty botId (first key wins)
            self._api_key_map     — { uin: apiKey, ... }  (plus apiKey→apiKey
                                     as a safety fallback when uin missing)

        And pushes the result into :mod:`.tenancy` so tool handlers and the
        download signal handler can resolve the correct apiKey per session.
        """
        import aiohttp

        url = f"{self._api_base_url}{API_PATH_TICKET}"
        bot_client_id = ""
        api_key_map: Dict[str, str] = {}

        async with aiohttp.ClientSession() as session:
            for key in self._api_keys:
                try:
                    headers = {
                        "authorization": f"Bearer {key}",
                        "x-product":     "channel",
                    }
                    async with session.post(
                        url, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(
                                "[lightclaw] %s HTTP %d for key ***%s",
                                API_PATH_TICKET, resp.status, key[-4:],
                            )
                            continue
                        data = await resp.json()
                        if data.get("code") != 0:
                            logger.warning(
                                "[lightclaw] %s error for key ***%s: %s",
                                API_PATH_TICKET, key[-4:], data.get("message"),
                            )
                            continue

                        payload = data.get("data") or {}

                        # Extract botClientId from data.client.extra (JSON-encoded)
                        extra_str = (payload.get("client") or {}).get("extra", "")
                        try:
                            parsed = json.loads(extra_str) if extra_str else {}
                            bid    = parsed.get("botId", "")
                        except (json.JSONDecodeError, TypeError):
                            bid = ""

                        if bid and not bot_client_id:
                            bot_client_id = bid

                        # Extract the uin — this is what inbound messages use
                        # as their `from` field and what we use to route the
                        # per-tenant apiKey.
                        uin = str(payload.get("id") or "").strip()
                        if uin:
                            api_key_map[uin] = key
                            logger.info(
                                "[lightclaw] Key ***%s mapped to uin=%s (botId=%s)",
                                key[-4:], uin, bid or "?",
                            )
                        else:
                            # No uin exposed → fall back to key→key so
                            # resolve_effective_api_key() always finds
                            # *something* for single-tenant deployments.
                            api_key_map[key] = key
                            logger.info(
                                "[lightclaw] Key ***%s mapped (botId=%s, no uin returned)",
                                key[-4:], bid or "?",
                            )
                except Exception as exc:
                    logger.warning(
                        "[lightclaw] Identity resolve failed for key ***%s: %s",
                        key[-4:], exc,
                    )

        if not bot_client_id:
            raise RuntimeError(
                "Failed to resolve botClientId from any API key via POST /cgi/ticket"
            )

        self._bot_client_id = bot_client_id
        self._api_key_map   = api_key_map

        # Publish the map into the tenancy module so inbound/outbound/tool
        # code can resolve the correct apiKey for a given sessionKey/senderId.
        default_key = self._api_keys[0] if self._api_keys else ""
        set_api_key_map(api_key_map, default_key)

        logger.info(
            "[lightclaw] Bot clientId: %s, %d key(s) mapped",
            bot_client_id, len(api_key_map),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        if not self._api_keys:
            logger.error("[lightclaw] No API keys configured")
            self._set_fatal_error("no_api_keys", "No API keys configured", retryable=False)
            return False

        try:
            import aiohttp  # noqa: F401
        except ImportError:
            logger.error("[lightclaw] aiohttp not installed")
            self._set_fatal_error("missing_deps", "aiohttp not installed", retryable=False)
            return False

        try:
            await self._resolve_identity()
        except Exception as exc:
            logger.error("[lightclaw] Identity resolution failed: %s", exc)
            self._set_fatal_error("identity_failed", str(exc), retryable=True)
            return False

        import aiohttp
        self._stopped            = False
        self._first_connect_event.clear()
        self._session            = aiohttp.ClientSession()
        self._reliable           = ReliableEmitter(
            ws_emit=self._ws_emit,
            ws_emit_with_timeout=self._ws_emit_with_timeout,
            prefix="[lightclaw]",
        )
        self._connection_task    = asyncio.create_task(self._connection_loop())

        # Wait for first successful WS connect
        try:
            await asyncio.wait_for(self._first_connect_event.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            logger.error("[lightclaw] Timed out waiting for initial connection")
            self._set_fatal_error("connect_timeout", "Initial connection timeout", retryable=True)
            return False

        _set_active_adapter(self)
        return True

    async def disconnect(self) -> None:
        self._stopped = True
        self._flush_pending_acks(ConnectionError("adapter disconnect"))
        if self._reliable:
            self._reliable.destroy()
            self._reliable = None
        if self._connection_task:
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
            self._connection_task = None
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        _set_active_adapter(None)
        self._mark_disconnected()

    # ------------------------------------------------------------------
    # Raw message dispatch
    # ------------------------------------------------------------------

    async def _handle_raw(self, raw: str) -> None:
        """
        Dispatch incoming WebSocket frames.
        Mirrors: src/socket/handlers.ts
        """
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        event = msg.get("event", "")
        data  = msg.get("data") or {}

        if event == EVENT_HANDSHAKE:
            self._socket_id = data.get("id", "")
            logger.info("[lightclaw] Handshake, socket_id=%s", self._socket_id)
            return

        if event == EVENT_MESSAGE_ACK:
            related = data.get("relatedMsgId", "")
            logger.debug("[lightclaw] ACK received: relatedMsgId=%s", related)
            if related:
                self._on_ws_ack(related)
            return

        if event == EVENT_MESSAGE_PRIVATE:
            # ── file:download signalling — separate from the AI pipeline ──
            # The front-end issues `kind=file:download, status=download_req`
            # when the user clicks on a `localfile://` markdown link.  We
            # handle it inline, never forwarding to handle_message().
            if data.get("kind") == KIND_FILE_DOWNLOAD:
                td = (data.get("extra") or {}).get("transferData") or {}
                if td.get("status") == FileDownloadStatus.REQ:
                    asyncio.create_task(self._handle_file_download_req(data))
                # Any other status on a client→adapter frame is ignored:
                # ready / url / error are only ever sent adapter→client.
                return

            # Spawn as background task: handle_message triggers the full
            # agent pipeline (seconds to minutes), must not block the WS
            # read loop.  Matches TS: void (async () => { await handler(msg); })()
            asyncio.create_task(self._handle_incoming_message(data))
            return

        if event == EVENT_HISTORY_REQUEST:
            await self._handle_history_request(data)
            return

        if event == EVENT_SESSIONS_REQUEST:
            await self._handle_sessions_request(data)
            return

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    async def get_chat_info(self, chat_id: str) -> dict:
        return {"name": f"LightClaw DM ({chat_id})", "type": "dm", "chat_id": chat_id}


# ---------------------------------------------------------------------------
# Module-level singleton accessor
# ---------------------------------------------------------------------------

_active_adapter: Optional[LightClawAdapter] = None


def _set_active_adapter(adapter: Optional[LightClawAdapter]) -> None:
    global _active_adapter
    _active_adapter = adapter


def get_active_adapter() -> Optional[LightClawAdapter]:
    """Return the running LightClawAdapter singleton, or None if not started."""
    return _active_adapter
