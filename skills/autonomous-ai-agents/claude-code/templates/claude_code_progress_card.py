#!/usr/bin/env python3
"""
Claude Code progress card for Feishu (CardKit 2.0).

Drop-in template for streaming a Claude Code task's progress to a
Feishu chat with an interactive card. Cards update in place via
PATCH (throttled 200ms) so the user sees iteration X/Y, current
stage, and accumulated tool calls without the chat being flooded
with separate messages.

Verified against CardKit 2.0 (2026-06-04). Tag reference:
- `lark_md` for text (NOT `markdown` — that's the #1 mistake)
- No top-level `schema: "2.0"` — that returns ErrCode 200621
- No nested `tag: "collapse"` blocks — unsupported in interactive path
- Code blocks go INSIDE lark_md as ```...``` fences, not as `tag: "code"`

Usage:
  1. Programmatic:
     from claude_code_progress_card import ClaudeCodeCard
     card = ClaudeCodeCard(receive_id="ou_xxx", task="Fix race in auth.py")
     card.start()
     for i in range(1, 11):
         card.update_iteration(i, stage=f"step {i}")
     card.complete(success=True, total_cost=0.05)

  2. CLI demo (no Claude Code, just simulates 5 iterations):
     python3 claude_code_progress_card.py demo ou_xxx

  3. CLI real run (drives a Claude Code process, parses its JSON output):
     python3 claude_code_progress_card.py run ou_xxx "Fix the bug" --max-turns 10

Requires:
  - `FEISHU_APP_ID` + `FEISHU_APP_SECRET` in env or
    `~/.hermes/feishu_credentials.json` (chmod 600)
  - `~/.hermes/bin/claude_code` wrapper for the `run` subcommand
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# CardKit 2.0 has a 10 PATCH/sec/app limit. 200ms throttle stays
# well under and gives the user visible streaming.
THROTTLE_INTERVAL = 0.2

CREDS_PATH = Path.home() / ".hermes" / "feishu_credentials.json"
ENV_PATH = Path.home() / ".hermes" / ".env"
_TOKEN_CACHE = {"token": None, "expires_at": 0}


# ---------------------------------------------------------------------------
# Feishu creds + token
# ---------------------------------------------------------------------------

def load_credentials() -> tuple[str, str]:
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if app_id and app_secret:
        return app_id, app_secret
    if CREDS_PATH.exists():
        d = json.loads(CREDS_PATH.read_text())
        return d["app_id"], d["app_secret"]
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env["FEISHU_APP_ID"], env["FEISHU_APP_SECRET"]


def get_token() -> str:
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] - 60 > now:
        return _TOKEN_CACHE["token"]
    app_id, app_secret = load_credentials()
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    if data.get("code") != 0:
        raise RuntimeError(f"token failed: {data}")
    _TOKEN_CACHE["token"] = data["tenant_access_token"]
    _TOKEN_CACHE["expires_at"] = now + data.get("expire", 7200)
    return _TOKEN_CACHE["token"]


def _request(method: str, url: str, body: Optional[dict] = None) -> dict:
    token = get_token()
    data = json.dumps(body, ensure_ascii=False).encode() if body else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
        method=method,
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        return {"code": e.code, "http_error": True,
                **json.loads(e.read() or b"{}")}


# ---------------------------------------------------------------------------
# Card builders — return CardKit 2.0 JSON, schema-verified
# ---------------------------------------------------------------------------

def progress_card(*, iteration: int, max_iterations: int, stage: str,
                  elapsed_seconds: float, completed: List[str],
                  in_progress: str, pending: List[str]) -> dict:
    return {
        "config": {"wide_screen_mode": True, "streaming_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "⏳ 正在执行任务"},
            "template": "blue",
        },
        "elements": [
            {"tag": "div", "text": {
                "tag": "lark_md",
                "content": (
                    f"**已运行：** {int(elapsed_seconds // 60)}分{int(elapsed_seconds % 60)}秒\n"
                    f"**当前迭代：** {iteration}/{max_iterations}\n"
                    f"**当前阶段：** {stage}"
                ),
            }},
            {"tag": "div", "text": {
                "tag": "lark_md",
                "content": (
                    "✅ **已完成：** " + " / ".join(completed or ["初始化"]) + "\n"
                    f"⏳ **进行中：** {in_progress}\n"
                    "🔜 **待完成：** " + " / ".join(pending or ["—"])
                ),
            }},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "中断任务"},
                 "type": "danger", "value": {"action": "interrupt"}},
                {"tag": "button", "text": {"tag": "plain_text", "content": "查看日志"},
                 "type": "default", "value": {"action": "view_log"}},
            ]},
        ],
    }


def final_card(*, task: str, total_seconds: float, iterations: int,
               max_iterations: int, total_cost: float,
               completed: List[str], success: bool = True) -> dict:
    template = "green" if success else "red"
    title = "🎉 任务完成" if success else "❌ 任务失败"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}, "template": template},
        "elements": [
            {"tag": "div", "text": {
                "tag": "lark_md",
                "content": (
                    f"**任务：** {task}\n"
                    f"**总耗时：** {int(total_seconds // 60)}分{total_seconds % 60:.1f}秒\n"
                    f"**总迭代：** {iterations}/{max_iterations}\n"
                    f"**总成本：** ${total_cost:.4f}"
                ),
            }},
            {"tag": "hr"},
            {"tag": "div", "text": {
                "tag": "lark_md",
                "content": "✅ **已完成**\n" + "\n".join(
                    f"{i}. {c}" for i, c in enumerate(completed, 1)
                ),
            }},
        ],
    }


# ---------------------------------------------------------------------------
# ClaudeCodeCard — sends initial card, PATCHes in place, finalizes
# ---------------------------------------------------------------------------

@dataclass
class ClaudeCodeCard:
    receive_id: str
    receive_id_type: str = "open_id"
    task: str = ""
    max_iterations: int = 40
    iterations: int = 0
    stage: str = "初始化"
    completed: List[str] = field(default_factory=list)
    in_progress: str = "等待开始"
    pending: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    message_id: Optional[str] = None
    _last_update: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _seq: int = 0  # for streaming PATCH ordering

    def _throttle(self) -> None:
        now = time.time()
        wait = THROTTLE_INTERVAL - (now - self._last_update)
        if wait > 0:
            time.sleep(wait)
        self._last_update = time.time()

    def _build_card(self) -> dict:
        return progress_card(
            iteration=self.iterations,
            max_iterations=self.max_iterations,
            stage=self.stage,
            elapsed_seconds=time.time() - self.start_time,
            completed=self.completed,
            in_progress=self.in_progress,
            pending=self.pending,
        )

    def _send(self, card: dict) -> str:
        url = (f"https://open.feishu.cn/open-apis/im/v1/messages"
               f"?receive_id_type={self.receive_id_type}")
        r = _request("POST", url, {
            "receive_id": self.receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        })
        if r.get("code") != 0:
            raise RuntimeError(f"card send failed (code={r.get('code')}): {r.get('msg')}")
        return r["data"]["message_id"]

    def _patch(self, message_id: str, card: dict) -> bool:
        self._seq += 1
        url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}"
        r = _request("PATCH", url, {
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
            "seq": str(self._seq),  # monotonic per message_id
        })
        if r.get("code") != 0:
            print(f"[warn] PATCH failed: {r.get('code')} {r.get('msg')}", file=sys.stderr)
            return False
        return True

    def start(self, task: Optional[str] = None) -> str:
        """Send the initial progress card. Returns message_id."""
        if task:
            self.task = task
        self.message_id = self._send(self._build_card())
        return self.message_id

    def update_iteration(self, iteration: int, *, stage: Optional[str] = None,
                         completed: Optional[str] = None,
                         in_progress: Optional[str] = None) -> None:
        """Throttled update of the progress card."""
        with self._lock:
            self.iterations = iteration
            if stage:
                self.stage = stage
            if completed and completed not in self.completed:
                self.completed.append(completed)
            if in_progress:
                self.in_progress = in_progress
            if not self.message_id:
                self.message_id = self.start()
                return
            self._throttle()
            self._patch(self.message_id, self._build_card())

    def complete(self, *, success: bool = True, summary: str = "",
                 total_cost: float = 0.0) -> None:
        """Send the final result card (new message, not a PATCH of progress)."""
        if not self.message_id:
            self.start()
        card = final_card(
            task=self.task or summary,
            total_seconds=time.time() - self.start_time,
            iterations=self.iterations,
            max_iterations=self.max_iterations,
            total_cost=total_cost,
            completed=self.completed or ["任务执行完成"],
            success=success,
        )
        # New message so the progress card history stays intact for the user
        self._send(card)


# ---------------------------------------------------------------------------
# Drive a Claude Code subprocess, parse its JSON event stream
# ---------------------------------------------------------------------------

def run_claude_code(card: ClaudeCodeCard, prompt: str,
                     max_turns: int = 10) -> dict:
    """Spawn ~/.hermes/bin/claude_code -p <prompt> --output-format json,
    parse events, update the card, return the final result."""
    wrapper = Path.home() / ".hermes" / "bin" / "claude_code"
    if not wrapper.exists():
        raise FileNotFoundError(
            f"claude_code wrapper missing: {wrapper}. "
            "See claude-code skill '3P Providers' section for the setup."
        )
    card.start(task=prompt[:80])
    card.update_iteration(0, stage="启动 Claude Code", in_progress="加载上下文")

    proc = subprocess.Popen(
        [str(wrapper), "-p", prompt, "--max-turns", str(max_turns),
         "--output-format", "stream-json", "--verbose"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    final = None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for tc in ev.get("message", {}).get("tool_calls", []) or []:
                fn = tc.get("function", {})
                name = fn.get("name", "?")
                args = json.loads(fn.get("arguments", "{}"))
                path = args.get("file_path", args.get("command", args.get("filePath", "")))
                card.update_iteration(
                    card.iterations + 1,
                    stage=f"调用 {name}",
                    completed=f"调用 {name}",
                    in_progress=f"执行 {name}",
                )
        elif ev.get("type") == "result":
            final = ev
    proc.wait()
    if final is None:
        final = {"is_error": True, "result": proc.stderr.read() or "无输出",
                 "total_cost_usd": 0, "num_turns": card.iterations}
    card.complete(
        success=not final.get("is_error", False),
        summary=(final.get("result", "") or "")[:200],
        total_cost=final.get("total_cost_usd", 0),
    )
    return final


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_demo(args):
    """Simulate 5 iterations without a real Claude Code process."""
    card = ClaudeCodeCard(
        receive_id=args.receive_id, task=args.task or "演示任务",
        max_iterations=5,
    )
    for i in range(1, 6):
        time.sleep(args.delay)
        card.update_iteration(
            i,
            stage=f"步骤 {i}",
            completed=f"步骤 {i-1}" if i > 1 else "初始化",
            in_progress=f"执行步骤 {i}",
        )
    card.complete(success=True, summary="演示完成", total_cost=0.001)
    print(f"✅ demo card: message_id={card.message_id}")


def cmd_run(args):
    """Real Claude Code run."""
    card = ClaudeCodeCard(receive_id=args.receive_id, max_iterations=args.max_turns)
    result = run_claude_code(card, args.prompt, args.max_turns)
    print(json.dumps({
        "success": not result.get("is_error"),
        "result_preview": (result.get("result", "") or "")[:300],
        "iterations": result.get("num_turns"),
        "cost_usd": result.get("total_cost_usd"),
        "duration_ms": result.get("duration_ms"),
    }, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description="Claude Code 飞书进度卡片")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("demo", help="模拟进度卡片（无 Claude Code）")
    s1.add_argument("receive_id")
    s1.add_argument("--task", default="")
    s1.add_argument("--delay", type=float, default=1.0)
    s1.set_defaults(func=cmd_demo)

    s2 = sub.add_parser("run", help="真跑 Claude Code + 流式推卡片")
    s2.add_argument("receive_id")
    s2.add_argument("prompt")
    s2.add_argument("--max-turns", type=int, default=10)
    s2.set_defaults(func=cmd_run)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
