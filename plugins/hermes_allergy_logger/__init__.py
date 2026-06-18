"""hermes_allergy_logger — auto-log allergy medication intake to Feishu Bitable.

Triggers on every user message that contains allergy-medication keywords
("过敏药 / 氯雷他定 / 西替利嗪 / 息斯敏 / 依巴斯汀 / 开瑞坦 / 抗过敏")
AND a clear "intake" signal ("刚吃 / 吃了 / 服了 / 吃了X片"). When the
user provides dose + symptom in the same message, writes a row to a
pre-configured Feishu Bitable via the OpenClaw gateway HTTP API
(`POST /tools/invoke` → `feishu_bitable_create_record`). When fields are
missing, the hook injects a context reminder that asks the LLM to
elicit them from the user — never invent data.

Honesty contract:
  * Never invent a symptom or dose. If the user did not state it, the
    field stays empty.
  * Bare mentions of a drug name ("这药副作用大不大") do NOT trigger
    a write or a follow-up question.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.request
import urllib.error
from typing import Any, List

logger = logging.getLogger(__name__)

# --- Configuration (lazy-loaded) -------------------------------------------

def _cfg() -> tuple[str, str, str, str, int]:
    """Resolve plugin config from env.

    Returns: (openclaw_url, openclaw_token, app_token, table_id, default_account)
    """
    return (
        os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789").rstrip("/"),
        os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip(),
        os.environ.get("ALLERGY_BITABLE_APP_TOKEN", "").strip(),
        os.environ.get("ALLERGY_BITABLE_TABLE_ID", "").strip(),
        int(os.environ.get("OPENCLAW_GATEWAY_TIMEOUT", "8")),
    )


# --- Keyword set ---------------------------------------------------------

_KEYWORDS = (
    "氯雷他定",
    "开瑞坦",
    "西替利嗪",
    "仙特明",
    "依巴斯汀",
    "息斯敏",
    "扑尔敏",
    "非索非那定",
    "孟鲁司特",
    "过敏药",
    "抗过敏",
)

# Intake signals — only treat as a real "I took it" event when one of these
# is in the message. Bare mentions ("氯雷他定副作用大不大") never trigger.
_INTAKE_SIGNALS = (
    "刚吃", "吃了", "服了", "喝了", "刚服", "刚喝了", "刚服了",
    "刚吞", "吞了", "咽了", "吃了一片", "吃了两片", "吃了一颗",
)

_DOSE_RE = re.compile(r"(\d+\s*(?:mg|毫克|片|颗))", re.IGNORECASE)

_SYMPTOM_KEYWORDS = (
    "荨麻疹", "鼻塞", "打喷嚏", "眼睛痒", "皮肤痒",
    "流鼻涕", "鼻痒", "皮疹", "湿疹", "瘙痒",
)


# --- Parsers (no guessing) -------------------------------------------------

def _parse_drug(text: str) -> str:
    """Return the drug name from the message, or '' if not stated."""
    for k in _KEYWORDS:
        if k in text:
            # Map common brand names to generics where reasonable
            if k in ("开瑞坦",):
                return "氯雷他定"
            if k in ("仙特明",):
                return "西替利嗪"
            return k
    return ""


def _parse_dose(text: str) -> str:
    """Return dose string like '10mg' / '1片' from the message, or ''."""
    m = _DOSE_RE.search(text)
    return m.group(1).replace(" ", "") if m else ""


def _parse_symptom(text: str) -> str:
    """Return the symptom the user explicitly mentioned, or ''."""
    for k in _SYMPTOM_KEYWORDS:
        if k in text:
            return k
    return ""


# --- OpenClaw /tools/invoke client ---------------------------------------

def _openclaw_invoke(tool_name: str, args: dict, timeout: float = 8.0) -> dict:
    """Call OpenClaw gateway `POST /tools/invoke`.

    Returns the parsed JSON response. Raises on transport errors.
    """
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


def _do_write(text: str, drug: str, dose: str, symptom: str) -> None:
    """Background worker: write one row via OpenClaw feishu_bitable_create_record.

    Refuses to write if any required field is empty.
    """
    _, _, app_token, table_id, _ = _cfg()
    if not (drug and dose and symptom):
        logger.warning(
            "allergy logger refusing to write — incomplete fields: "
            "drug=%r dose=%r symptom=%r text=%r",
            drug, dose, symptom, text[:60],
        )
        return
    if not (app_token and table_id):
        logger.warning("allergy logger not configured (env missing)")
        return

    now_ms = int(time.time() * 1000)
    fields = {
        "服药时间": now_ms,
        "药品名": drug,
        "剂量": dose,
        "症状": symptom,
        "备注": text[:200],
    }

    try:
        resp = _openclaw_invoke(
            "feishu_bitable_create_record",
            {"app_token": app_token, "table_id": table_id, "fields": fields},
        )
        if not resp.get("ok"):
            logger.warning("allergy logger: openclaw returned not-ok: %s", resp)
            return

        # OpenClaw wraps tool output as result.content[*].text (string of JSON)
        out = resp.get("result") or {}
        record_id = None
        for c in (out.get("content") or []):
            if c.get("type") == "text":
                try:
                    parsed = json.loads(c.get("text", ""))
                    rec = parsed.get("record") or {}
                    record_id = rec.get("record_id") or rec.get("id")
                except (ValueError, KeyError):
                    pass
        logger.info(
            "allergy logger: wrote record %s via openclaw for: %s",
            record_id or "(unknown)", text[:60],
        )
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
        logger.warning("allergy logger: openclaw call failed: %s", exc)


def _extract_user_text(messages: Any) -> List[str]:
    """Pull the latest user-role text content out of an LLM-bound messages list."""
    if not isinstance(messages, list):
        return []
    out: List[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "user":
            continue
        content = m.get("content", "")
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    out.append(part.get("text", ""))
    return out


# --- Hook entry point -----------------------------------------------------

def on_pre_llm_call(messages=None, user_message=None, **kwargs) -> dict:
    """pre_llm_call hook: detect allergy-med intake events, log via OpenClaw.

    Returns:
        dict with optional 'context' key — when symptom/dose is missing,
        we ask the LLM to elicit them from the user instead of writing
        a guessed row. When everything is present, we log silently.
    """
    sources: list[str] = []
    if isinstance(user_message, str) and user_message:
        sources.append(user_message)
    for t in _extract_user_text(messages):
        if t and t not in sources:
            sources.append(t)

    for text in sources:
        if not text or not any(k in text for k in _KEYWORDS):
            continue

        # Require an explicit "I took it" signal
        if not any(s in text for s in _INTAKE_SIGNALS):
            continue

        symptom = _parse_symptom(text)
        dose = _parse_dose(text)
        drug = _parse_drug(text)

        if symptom and dose and drug:
            # All fields present — write via OpenClaw
            t = threading.Thread(
                target=_do_write, args=(text, drug, dose, symptom),
                daemon=True, name="allergy-logger-write",
            )
            t.start()
            continue

        # Missing fields — DO NOT WRITE. Inject context so the LLM asks.
        missing = []
        if not drug:
            missing.append("药品名")
        if not dose:
            missing.append("剂量")
        if not symptom:
            missing.append("症状")
        ask = (
            "[hermes_allergy_logger] 检测到主人刚服过敏药，但有字段未声明："
            + "、".join(missing)
            + "。请在回复中**直接问主人**补全这些字段，**绝对不要猜测或编造**。"
            + "主人回答后再通过 openclaw feishu_bitable_create_record 写入多维表格。"
        )
        return {"context": ask}

    return {}


# --- Plugin entry point ---------------------------------------------------

def register(ctx) -> None:
    """Register pre_llm_call hook with the Hermes plugin loader."""
    try:
        ctx.register_hook("pre_llm_call", on_pre_llm_call)
        logger.info("hermes_allergy_logger registered pre_llm_call hook")
    except Exception as exc:  # pragma: no cover
        logger.debug("hermes_allergy_logger hook registration failed: %s", exc)
