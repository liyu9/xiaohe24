# hermes_allergy_logger.py — full working example (the 2026-06-06 plugin)

This is the **actual working plugin** the skill was built from, in
`~/.hermes/plugins/hermes_allergy_logger/__init__.py`. Read it as the
canonical reference when adapting the `templates/plugin-skeleton.py`
to a new event class. The 4 events that distinguish it from the
skeleton:

1. **Drug-name alias map** (`开瑞坦 → 氯雷他定`, `仙特明 → 西替利嗪`) — the
   skeleton has a single `parse_drug` returning the keyword verbatim;
   the real plugin canonicalizes brand names to generics.
2. **Symptom options set with no defaults** — the 2026-06-06 lesson was
   "do not default-fill the symptom column". The real parser returns
   `""` if the user did not state the symptom, and the writer refuses
   to write.
3. **De-dup window** (the `_is_duplicate_record` helper, removed in the
   final version) — the original plugin had a 60-second dedup window
   to avoid writing the same message twice if the hook fired twice on
   a multi-turn reply. The current version does not, because the
   `_last_logged` dict was leaking across sessions; the cleaner
   approach is to make the LLM/hook dedup at the message boundary
   (the hook receives one user message per turn, so true dedup is not
   needed).
4. **Bare-mention guard** — only write when both a keyword AND an
   intake-signal are present. The skeleton encodes this; the lesson
   is that "this drug is great for sleep" must not trigger a write.

## The file

```python
"""hermes_allergy_logger — auto-log allergy medication intake to Feishu Bitable.

Triggers on every user message that contains allergy-medication keywords
("过敏药 / 氯雷他定 / 西替利嗪 / 息斯敏 / 依巴斯汀 / 开瑞坦 / 抗过敏")
AND a clear "intake" signal ("刚吃 / 吃了 / 服了 / 吃了X片"). When the
user provides dose + symptom in the same message, writes a row to a
pre-configured Feishu Bitable via the OpenClaw gateway HTTP API
(`POST /tools/invoke` → `feishu_bitable_create_record`). When fields are
missing, the hook injects a context reminder that asks the LLM to
elicit them from the user — never invent data.
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


# --- Configuration (lazy-loaded) -----------------------------------------

def _cfg() -> tuple[str, str, str, str, int]:
    return (
        os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789").rstrip("/"),
        os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip(),
        os.environ.get("ALLERGY_BITABLE_APP_TOKEN", "").strip(),
        os.environ.get("ALLERGY_BITABLE_TABLE_ID", "").strip(),
        int(os.environ.get("OPENCLAW_GATEWAY_TIMEOUT", "8")),
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
_SYMPTOM_KEYWORDS = (
    "荨麻疹", "鼻塞", "打喷嚏", "眼睛痒", "皮肤痒",
    "流鼻涕", "鼻痒", "皮疹", "湿疹", "瘙痒",
)


# --- Parsers (no guessing) ------------------------------------------------

def _parse_drug(text: str) -> str:
    for k in _KEYWORDS:
        if k in text:
            if k in ("开瑞坦",): return "氯雷他定"
            if k in ("仙特明",): return "西替利嗪"
            return k
    return ""


def _parse_dose(text: str) -> str:
    m = _DOSE_RE.search(text)
    return m.group(1).replace(" ", "") if m else ""


def _parse_symptom(text: str) -> str:
    for k in _SYMPTOM_KEYWORDS:
        if k in text:
            return k
    return ""


# --- OpenClaw /tools/invoke client ---------------------------------------

def _openclaw_invoke(tool_name: str, args: dict, timeout: float = 8.0) -> dict:
    base, token, _, _, _ = _cfg()
    body = json.dumps({"name": tool_name, "args": args}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    }
    req = urllib.request.Request(f"{base}/tools/invoke", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _do_write(text: str, drug: str, dose: str, symptom: str) -> None:
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

    try:
        resp = _openclaw_invoke("feishu_bitable_create_record", {
            "app_token": app_token,
            "table_id": table_id,
            "fields": {
                "服药时间": int(time.time() * 1000),
                "药品名": drug, "剂量": dose, "症状": symptom,
                "备注": text[:200],
            },
        })
        if not resp.get("ok"):
            logger.warning("allergy logger: openclaw returned not-ok: %s", resp)
            return
        out = resp.get("result") or {}
        for c in (out.get("content") or []):
            if c.get("type") == "text":
                try:
                    parsed = json.loads(c.get("text", ""))
                    rec = parsed.get("record") or {}
                    rid = rec.get("record_id") or rec.get("id")
                    logger.info("allergy logger: wrote record %s for: %s",
                                rid, text[:60])
                except (ValueError, KeyError):
                    pass
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
        logger.warning("allergy logger: openclaw call failed: %s", exc)


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


# --- Hook entry point -----------------------------------------------------

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

        if symptom and dose and drug:
            t = threading.Thread(
                target=_do_write, args=(text, drug, dose, symptom),
                daemon=True, name="allergy-logger-write",
            )
            t.start()
            continue

        missing = []
        if not drug: missing.append("药品名")
        if not dose: missing.append("剂量")
        if not symptom: missing.append("症状")
        ask = (
            "[hermes_allergy_logger] 检测到主人刚服过敏药，但有字段未声明："
            + "、".join(missing)
            + "。请在回复中**直接问主人**补全这些字段，**绝对不要猜测或编造**。"
            + "主人回答后再通过 openclaw feishu_bitable_create_record 写入多维表格。"
        )
        return {"context": ask}

    return {}


def register(ctx) -> None:
    try:
        ctx.register_hook("pre_llm_call", on_pre_llm_call)
    except Exception as exc:
        logger.debug("hermes_allergy_logger hook registration failed: %s", exc)
```

## What this file shows that the skeleton does not

- **5-line keyword tuple** with intentional brand-name aliases
  (`开瑞坦`, `仙特明`) mapped to generics in `_parse_drug`. When the
  user says "我吃了开瑞坦" the Bitable gets "氯雷他定", which is
  the right name for a future "what generics have I used?" query.
- **Strict missing-field policy**: `_do_write` calls `logger.warning`
  AND returns without writing if any of the three parsers returned
  `""`. The LLM does not get to second-guess this — the plugin code
  is the durable guard.
- **Log-level escalation on miss**: `logger.info` for a successful
  write, `logger.warning` for a refused write. The user can grep
  `journalctl --user -u hermes-gateway` for the warning level to see
  what fields they keep forgetting to say.

## What it deliberately does not do

- No dedup window. The hook receives one user message per turn; if
  the user sends the same message twice in two turns, two rows is
  the correct answer (they had two doses).
- No retry on transient openclaw errors. A failed write logs a
  warning; the user can read the warning and decide whether to
  re-state the event. Building a retry layer adds complexity for a
  real-world event logger that should be deterministic, not resilient.
- No LLM call. A symptom parsing layer that calls the LLM to extract
  "what was the user feeling?" introduces a determinism-breaking
  vector and a cost-per-event. The keyword set is the parser; if the
  user says something the keyword set does not match, the LLM asks
  the follow-up question instead.
