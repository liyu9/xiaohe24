"""hermes_allergy_logger — full working example of a Hermes plugin that
auto-logs allergy medication intake to a Feishu Bitable via the OpenClaw
gateway's /tools/invoke → feishu_bitable_create_record path.

Drop into ~/.hermes/plugins/hermes_allergy_logger/__init__.py with a
plugin.yaml, set env vars, restart gateway.

Triggers on user messages that:
  (a) mention an allergy-medication keyword (氯雷他定 / 西替利嗪 / 开瑞坦 / ...)
  (b) carry a clear "I took it" signal (刚吃 / 吃了 / 服了 / 吞了 / ...)

If the user provides drug + dose + symptom in the same message → silent write.
If anything is missing → inject a context reminder so the LLM asks the user.
Never invent a symptom or dose.
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


# --- Lazy config ----------------------------------------------------------

def _cfg() -> tuple[str, str, str, str]:
    return (
        os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789").rstrip("/"),
        os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip(),
        os.environ.get("ALLERGY_BITABLE_APP_TOKEN", "").strip(),
        os.environ.get("ALLERGY_BITABLE_TABLE_ID", "").strip(),
    )


# --- Keyword set ---------------------------------------------------------

_KEYWORDS = (
    "氯雷他定", "开瑞坦", "西替利嗪", "仙特明", "依巴斯汀",
    "息斯敏", "扑尔敏", "非索非那定", "孟鲁司特", "过敏药", "抗过敏",
)
_INTAKE_SIGNALS = (
    "刚吃", "吃了", "服了", "喝了", "刚服", "刚喝了", "刚服了",
    "刚吞", "吞了", "咽了", "吃了一片", "吃了两片", "吃了一颗",
)
_DOSE_RE = re.compile(r"(\d+\s*(?:mg|毫克|片|颗))", re.IGNORECASE)
_SYMPTOMS = (
    "荨麻疹", "鼻塞", "打喷嚏", "眼睛痒", "皮肤痒",
    "流鼻涕", "鼻痒", "皮疹", "湿疹", "瘙痒",
)


def _parse_drug(text: str) -> str:
    for k in _KEYWORDS:
        if k in text:
            if k == "开瑞坦": return "氯雷他定"
            if k == "仙特明": return "西替利嗪"
            return k
    return ""

def _parse_dose(text: str) -> str:
    m = _DOSE_RE.search(text)
    return m.group(1).replace(" ", "") if m else ""

def _parse_symptom(text: str) -> str:
    for k in _SYMPTOMS:
        if k in text:
            return k
    return ""


# --- OpenClaw /tools/invoke client ---------------------------------------

def _openclaw_invoke(tool_name: str, args: dict, timeout: float = 8.0) -> dict:
    base, token, _, _ = _cfg()
    body = json.dumps({"name": tool_name, "args": args}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base}/tools/invoke", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _do_write(text: str, drug: str, dose: str, symptom: str) -> None:
    _, _, app_token, table_id = _cfg()
    if not (drug and dose and symptom):
        logger.warning("refusing to write — incomplete fields: %r %r %r", drug, dose, symptom)
        return
    if not (app_token and table_id):
        logger.warning("not configured (env missing)")
        return

    try:
        resp = _openclaw_invoke("feishu_bitable_create_record", {
            "app_token": app_token,
            "table_id": table_id,
            "fields": {
                "服药时间": int(time.time() * 1000),
                "药品名": drug,
                "剂量": dose,
                "症状": symptom,
                "备注": text[:200],
            },
        })
        if resp.get("ok"):
            content = resp.get("result", {}).get("content") or []
            for c in content:
                if c.get("type") == "text":
                    try:
                        rec = json.loads(c["text"]).get("record", {})
                        logger.info("wrote record %s", rec.get("record_id"))
                    except (ValueError, KeyError):
                        pass
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        logger.warning("openclaw call failed: %s", exc)


def _extract_user_text(messages: Any) -> List[str]:
    if not isinstance(messages, list):
        return []
    out: List[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, str):
                out.append(c)
            elif isinstance(c, list):
                for p in c:
                    if isinstance(p, dict) and p.get("type") == "text":
                        out.append(p.get("text", ""))
    return out


# --- Hook -----------------------------------------------------------------

def on_pre_llm_call(messages=None, user_message=None, **kwargs) -> dict:
    sources: list[str] = []
    if isinstance(user_message, str) and user_message:
        sources.append(user_message)
    for t in _extract_user_text(messages):
        if t and t not in sources:
            sources.append(t)

    for text in sources:
        if not text or not any(k in text for k in _KEYWORDS):
            continue
        if not any(s in text for s in _INTAKE_SIGNALS):
            continue

        symptom = _parse_symptom(text)
        dose = _parse_dose(text)
        drug = _parse_drug(text)

        if drug and dose and symptom:
            threading.Thread(
                target=_do_write, args=(text, drug, dose, symptom),
                daemon=True, name="allergy-logger-write",
            ).start()
            continue

        missing = [n for n, v in (("药品名", drug), ("剂量", dose), ("症状", symptom)) if not v]
        return {"context": (
            "[hermes_allergy_logger] 检测到主人刚服过敏药，但字段未声明："
            + "、".join(missing)
            + "。请直接问主人补全，**不要猜测**。"
            + "主人回答后通过 openclaw feishu_bitable_create_record 写入多维表格。"
        )}

    return {}


def register(ctx) -> None:
    try:
        ctx.register_hook("pre_llm_call", on_pre_llm_call)
        logger.info("hermes_allergy_logger registered pre_llm_call hook")
    except Exception as exc:  # pragma: no cover
        logger.debug("hermes_allergy_logger hook registration failed: %s", exc)
