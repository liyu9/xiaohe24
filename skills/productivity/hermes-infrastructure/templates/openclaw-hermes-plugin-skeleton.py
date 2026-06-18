"""Hermes plugin skeleton — calls OpenClaw gateway tools via /tools/invoke.

Drop this into ~/.hermes/plugins/<your_plugin_name>/__init__.py, add a
plugin.yaml next to it, set OPENCLAW_GATEWAY_URL + OPENCLAW_GATEWAY_TOKEN
in ~/.hermes/.env, and register the hook in register(ctx).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def _openclaw_invoke(tool_name: str, args: dict, timeout: float = 8.0) -> dict:
    """Call OpenClaw gateway POST /tools/invoke.

    Returns the parsed JSON response. Raises on transport errors.
    """
    base = os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789").rstrip("/")
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    body = json.dumps({"name": tool_name, "args": args}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base}/tools/invoke", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_user_text(messages: Any) -> list[str]:
    """Pull user-role text out of an LLM-bound messages list."""
    if not isinstance(messages, list):
        return []
    out: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                out.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        out.append(part.get("text", ""))
    return out


# --- Hook handlers ---------------------------------------------------------

def on_pre_llm_call(messages=None, user_message=None, **kwargs) -> dict:
    """pre_llm_call hook: detect events, write to Feishu via OpenClaw, etc.

    Returns:
        dict with optional 'context' key — when extra info is needed from
        the user, the value is appended to the current turn's user message
        so the LLM sees it. The framework only injects non-empty values.
    """
    sources: list[str] = []
    if isinstance(user_message, str) and user_message:
        sources.append(user_message)
    for t in _extract_user_text(messages):
        if t and t not in sources:
            sources.append(t)

    for text in sources:
        # ... your detection logic here ...
        if "<your-keyword>" in text:
            # Fire-and-forget write to Bitable (or any other tool)
            def _worker(text=text):
                try:
                    resp = _openclaw_invoke("feishu_bitable_create_record", {
                        "app_token": os.environ.get("YOUR_BITABLE_APP_TOKEN", ""),
                        "table_id": os.environ.get("YOUR_BITABLE_TABLE_ID", ""),
                        "fields": {
                            # ... your fields ...
                        },
                    })
                    if resp.get("ok"):
                        text_block = resp["result"]["content"][0]["text"]
                        record = json.loads(text_block).get("record", {})
                        logger.info("wrote record %s", record.get("record_id"))
                except (urllib.error.URLError, KeyError, ValueError) as exc:
                    logger.warning("openclaw call failed: %s", exc)

            threading.Thread(target=_worker, daemon=True, name="<your>-writer").start()

    return {}


# --- Plugin entry point ----------------------------------------------------

def register(ctx) -> None:
    """Register hooks with the Hermes plugin loader."""
    try:
        ctx.register_hook("pre_llm_call", on_pre_llm_call)
        logger.info("<your_plugin> registered pre_llm_call hook")
    except Exception as exc:  # pragma: no cover
        logger.debug("<your_plugin> hook registration failed: %s", exc)
