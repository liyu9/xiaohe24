"""bitable-auto-logger plugin skeleton — drop-in template.

Replace the 4 UPPER-CASE placeholders below with the user's event:
- KEYWORDS: the event nouns (drug names, drink types, activity names, ...)
- INTAKE_SIGNALS: phrases that mean "the event just happened"
- FIELDS: the Bitable column names + value-builder lambdas
- DEFAULT_VALUES: any field where the absence of a value is *meaningful*
  (e.g. "未填" for an optional column). For load-bearing fields like
  dose or amount, leave DEFAULT_VALUES empty and let the LLM ask.

Copy this file to `~/.hermes/plugins/<name>/__init__.py` and the
plugin.yaml below to `~/.hermes/plugins/<name>/plugin.yaml`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, List

logger = logging.getLogger(__name__)


# --- CONFIG PLACEHOLDERS (replace per event class) -----------------------

KEYWORDS = ("KEYWORD1", "KEYWORD2")          # TODO: list the event nouns
INTAKE_SIGNALS = ("刚吃", "吃了", "服了")     # TODO: list the intake verbs
DOSE_RE = re.compile(r"PATTERN_HERE")         # TODO: e.g. r"(\d+\s*(?:mg|片|颗))"
SYMPTOM_KEYWORDS = ("OPTION1", "OPTION2")    # TODO: optional 4th column

# Map: column name in Bitable -> (parser callable returning str)
# Parser must return "" if the value is not in the message.
FIELDS = {
    "时间": lambda text: int(time.time() * 1000),   # auto-now; no parsing
    "事件类型": lambda text: "",                    # TODO: parse from KEYWORDS
    "剂量": lambda text: "",                        # TODO: DOSE_RE parse
    "备注": lambda text: text[:200],
}

# Field that is load-bearing — if its parser returns "", DO NOT WRITE.
LOAD_BEARING_FIELDS = {"事件类型", "剂量"}


# --- Configuration (lazy-loaded; Hermes env may not be set at import) ----

def _cfg() -> tuple[str, str, str, str, int]:
    return (
        os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789").rstrip("/"),
        os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip(),
        os.environ.get("BITABLE_APP_TOKEN", "").strip(),
        os.environ.get("BITABLE_TABLE_ID", "").strip(),
        int(os.environ.get("OPENCLAW_GATEWAY_TIMEOUT", "8")),
    )


# --- OpenClaw client (do not edit) ---------------------------------------

def _openclaw_invoke(tool_name: str, args: dict, timeout: float = 8.0) -> dict:
    base, token, _, _, _ = _cfg()
    body = json.dumps({"name": tool_name, "args": args}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/tools/invoke",
        data=body,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --- Writer (do not edit) -----------------------------------------------

def _do_write(text: str, parsed: dict) -> None:
    _, _, app_token, table_id, _ = _cfg()
    if not (app_token and table_id):
        logger.debug("plugin not configured (env missing), skipping")
        return

    # Honesty contract: refuse to write if any load-bearing field is empty.
    missing = [k for k in LOAD_BEARING_FIELDS if not parsed.get(k)]
    if missing:
        logger.warning(
            "plugin refusing to write — load-bearing fields empty: %s",
            ", ".join(missing),
        )
        return

    try:
        resp = _openclaw_invoke(
            "feishu_bitable_create_record",
            {"app_token": app_token, "table_id": table_id, "fields": parsed},
        )
        if not resp.get("ok"):
            logger.warning("openclaw returned not-ok: %s", resp)
            return
        out = resp.get("result") or {}
        for c in (out.get("content") or []):
            if c.get("type") == "text":
                try:
                    parsed_resp = json.loads(c.get("text", ""))
                    rec = parsed_resp.get("record") or {}
                    rid = rec.get("record_id") or rec.get("id")
                    logger.info("plugin: wrote record %s for: %s", rid, text[:60])
                except (ValueError, KeyError):
                    pass
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
        logger.warning("plugin: openclaw call failed: %s", exc)


# --- Hook entry point (do not edit) -------------------------------------

def _extract_user_text(messages: Any) -> List[str]:
    if not isinstance(messages, list):
        return []
    out: List[str] = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        c = m.get("content", "")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") == "text":
                    out.append(p.get("text", ""))
    return out


def on_pre_llm_call(messages=None, user_message=None, **kwargs) -> dict:
    sources: list[str] = []
    if isinstance(user_message, str) and user_message:
        sources.append(user_message)
    for t in _extract_user_text(messages):
        if t and t not in sources:
            sources.append(t)

    for text in sources:
        if not text or not any(k in text for k in KEYWORDS):
            continue
        if not any(s in text for s in INTAKE_SIGNALS):
            continue

        parsed = {col: fn(text) for col, fn in FIELDS.items()}

        missing = [k for k in LOAD_BEARING_FIELDS if not parsed.get(k)]
        if not missing:
            t = threading.Thread(
                target=_do_write, args=(text, parsed), daemon=True,
                name=f"{__name__}-write",
            )
            t.start()
            continue

        # Missing load-bearing fields — inject context so the LLM asks
        return {
            "context": (
                f"[{__name__}] 检测到主人刚 X，但有字段未声明："
                + "、".join(missing)
                + "。请在回复中**直接问主人**补全这些字段，**绝对不要猜测或编造**。"
                + "主人回答后再通过 openclaw feishu_bitable_create_record 写入多维表格。"
            )
        }

    return {}


def register(ctx) -> None:
    try:
        ctx.register_hook("pre_llm_call", on_pre_llm_call)
    except Exception as exc:
        logger.debug("%s hook registration failed: %s", __name__, exc)
