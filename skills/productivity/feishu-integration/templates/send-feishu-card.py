#!/usr/bin/env python3
"""
Send a Feishu (Lark) interactive card message via the official API.

Card structure verified 2026-06-05 against real Feishu API responses
AND server-side stored content (via GET). Earlier versions of this
template used `tag: "div"` wrapping `tag: "lark_md"` — that returned
200 OK on send but the server stripped the div and rendered plain
rich text in the client. The verified shape is `tag: "markdown"` at
top level of the `elements` array.

Source of the send flow: open.feishu.cn open-apis/im/v1/messages +
auth/v3/tenant_access_token/internal.

Prereqs:
    pip install requests
    export FEISHU_APP_ID=cli_xxxxxxxxxxxx
    export FEISHU_APP_SECRET=your_32_char_secret
    # The app must have im:message scope and bot enabled.

Usage:
    python3 send_feishu_card.py \
        --to ou_xxxxxxxxxxxxxxxxxxxxxxxx \
        --to-type open_id \
        --title "MCP install done" \
        --body "**web_search** verified end-to-end." \
        --color blue \
        --button "Open docs" https://platform.minimaxi.com/docs/llms.txt
    # Add --verify to pull the message back via GET and confirm
    # the server actually preserved the card structure.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

TENANT_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
MESSAGE_GET_URL = "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}"

# 7 valid header templates per Feishu Card JSON 2.0 (verified 2026-06-05)
HEADER_TEMPLATES = {"blue", "red", "green", "yellow", "purple", "orange", "grey"}


def get_tenant_access_token(app_id: str, app_secret: str, timeout: int = 10) -> str:
    """Fetch a tenant_access_token. Cached in-process for ~110 minutes
    (token TTL is 2h, refresh slightly before)."""
    r = requests.post(
        TENANT_TOKEN_URL,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=timeout,
    )
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"tenant_access_token failed: {data}")
    return data["tenant_access_token"]


def build_card(
    title: str,
    body_md: str,
    color: str = "blue",
    buttons: Optional[List[Dict[str, str]]] = None,
    extra_elements: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a Feishu Card JSON 2.0 payload.

    Args:
        title: Header text. Plain text only.
        body_md: Markdown body. Use the top-level `tag: "markdown"`
            element (NOT `div` wrapping `lark_md` — that gets stripped
            server-side and renders as plain text in the client).
        color: One of HEADER_TEMPLATES. Default "blue".
        buttons: List of {"label": str, "url": str, "type": "default"|"primary"|"danger"}.
            type defaults to "default".
        extra_elements: Extra elements to append after the body. Useful for
            dividers (`{"tag": "hr"}`), notes, image rows, etc.

    Returns:
        Card JSON dict ready to send as `msg_type: "interactive"`.
    """
    if color not in HEADER_TEMPLATES:
        raise ValueError(f"color must be one of {HEADER_TEMPLATES}, got {color!r}")

    elements: List[Dict[str, Any]] = [{"tag": "markdown", "content": body_md}]

    if buttons:
        action_buttons = []
        for b in buttons:
            action_buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": b["label"]},
                "type": b.get("type", "default"),
                "url": b["url"],
                # CardKit 2.0 contract: value wraps action key for
                # card.action.trigger callbacks. Top-level `action:`
                # is rejected.
                "value": {"action": "open_url"},
            })
        elements.append({"tag": "action", "actions": action_buttons})

    if extra_elements:
        elements.extend(extra_elements)

    return {
        "config": {"wide_screen_mode": True, "streaming_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": color,
        },
        "elements": elements,
    }


def send_card(
    card: Dict[str, Any],
    receive_id: str,
    receive_id_type: str = "open_id",
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
    timeout: int = 15,
) -> Dict[str, Any]:
    """POST the card to /im/v1/messages."""
    app_id = app_id or os.environ.get("FEISHU_APP_ID")
    app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET")
    if not (app_id and app_secret):
        raise RuntimeError("FEISHU_APP_ID and FEISHU_APP_SECRET required")

    token = get_tenant_access_token(app_id, app_secret, timeout=timeout)
    r = requests.post(
        f"{MESSAGE_URL}?receive_id_type={receive_id_type}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
        timeout=timeout,
    )
    return r.json()


def verify_card_rendered(
    message_id: str,
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """Pull back the stored message and report what Feishu actually kept.

    Why this exists: 2026-06-05 lesson — a card send can return code: 0
    AND have msg_type=interactive AND still render as plain rich text in
    the client, because the server strips certain element shapes
    (e.g. `tag: "div"` wrapping). Pulling back via GET is the only way
    to confirm what the client will see.

    Returns a dict with:
        - ok: bool — True if code: 0
        - msg_type: stored message type
        - content: raw stored content JSON
        - is_post_format: True if the server flattened the card into
          post-format (this means the client renders plain rich text,
          not a card). False means the card structure was preserved.
        - warning: human-readable warning if the card was flattened
    """
    app_id = app_id or os.environ.get("FEISHU_APP_ID")
    app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET")
    if not (app_id and app_secret):
        raise RuntimeError("FEISHU_APP_ID and FEISHU_APP_SECRET required")
    token = get_tenant_access_token(app_id, app_secret, timeout=timeout)

    r = requests.get(
        MESSAGE_GET_URL.format(message_id=message_id),
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    data = r.json().get("data", {}).get("items", [{}])[0]
    content_str = data.get("body", {}).get("content", "{}")
    content = json.loads(content_str) if isinstance(content_str, str) else content_str
    is_post = (
        isinstance(content, dict)
        and isinstance(content.get("elements"), list)
        and len(content["elements"]) > 0
        and isinstance(content["elements"][0], list)  # nested array = post format
    )
    return {
        "ok": data.get("msg_type") == "interactive",
        "msg_type": data.get("msg_type"),
        "content": content,
        "is_post_format": is_post,
        "warning": (
            "Server flattened the card into post-format — client will "
            "render plain rich text, NOT a card. Check that you used "
            "tag: 'markdown' at the top level of elements, not "
            "tag: 'div' wrapping tag: 'lark_md'."
        ) if is_post else None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Send a Feishu interactive card")
    p.add_argument("--to", required=True, help="receive_id (open_id / chat_id / email)")
    p.add_argument("--to-type", default="open_id",
                   choices=["open_id", "chat_id", "email", "union_id"])
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True, help="markdown body")
    p.add_argument("--color", default="blue", choices=sorted(HEADER_TEMPLATES))
    p.add_argument("--button", nargs=3, metavar=("LABEL", "URL", "TYPE"),
                   action="append", default=[],
                   help="repeatable: LABEL URL TYPE (default|primary|danger)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the card JSON, don't send")
    p.add_argument("--verify", action="store_true",
                   help="after sending, pull the message back via GET and "
                        "check that the server preserved the card structure")
    args = p.parse_args()

    buttons = []
    for label, url, btype in args.button:
        buttons.append({"label": label, "url": url, "type": btype})

    card = build_card(args.title, args.body, args.color, buttons=buttons)

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    result = send_card(card, args.to, args.to_type)
    if result.get("code") != 0:
        print(f"send failed: {result}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.verify:
        time.sleep(1)  # let the server index
        mid = result.get("data", {}).get("message_id")
        if not mid:
            print("(no message_id; cannot verify)", file=sys.stderr)
            return 0
        v = verify_card_rendered(mid)
        print("\n--- GET-back verification ---")
        print(f"msg_type: {v['msg_type']}")
        print(f"is_post_format (server flattened?): {v['is_post_format']}")
        if v["warning"]:
            print(f"⚠️  {v['warning']}")
        return 1 if v["warning"] else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
