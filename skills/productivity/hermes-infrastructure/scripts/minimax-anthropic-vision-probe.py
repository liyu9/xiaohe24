#!/usr/bin/env python3
"""
MiniMax-M3 vision probe via the Anthropic-compatible endpoint.

Use this when you've pointed auxiliary.vision at a provider whose base_url
ends in /anthropic and api_mode=anthropic_messages, and you want to verify
the upstream accepts image base64 input before claiming "vision works".

Exits 0 on HTTP 200 + non-empty assistant text. Non-zero with a one-line
error on any failure mode.

Usage:
    MINIMAX_API_KEY=sk-cp-... python3 minimax_anthropic_vision_probe.py \
        --image /home/ubuntu/.hermes/image_cache/img_xxx.jpg

Optional flags:
    --query "Describe the layout"   # custom text prompt
    --max-tokens 1024               # default 1024
    --model MiniMax-M3              # default MiniMax-M3
    --base-url https://api.minimaxi.com/anthropic
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.minimaxi.com/anthropic"
DEFAULT_MODEL = "MiniMax-M3"
DEFAULT_QUERY = (
    "Describe this image in detail. Include all visible text, layout, "
    "structure, and the relationship between elements."
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True, help="Path to JPEG/PNG image")
    p.add_argument("--query", default=DEFAULT_QUERY)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = p.parse_args()

    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        print("ERROR: MINIMAX_API_KEY env var not set", file=sys.stderr)
        return 2

    try:
        with open(args.image, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
    except OSError as e:
        print(f"ERROR: cannot read image: {e}", file=sys.stderr)
        return 2

    # Detect media type from extension (Anthropic protocol requires exact media_type)
    ext = args.image.rsplit(".", 1)[-1].lower()
    media_type = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    }.get(ext, "image/jpeg")

    payload = {
        "model": args.model,
        "max_tokens": args.max_tokens,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": img_b64
                }},
                {"type": "text", "text": args.query},
            ],
        }],
    }

    req = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"FAIL HTTP {e.code}: {e.read().decode('utf-8')[:500]}")
        return 1
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return 1

    # Anthropic response: content is a list of blocks; find the text block
    text_parts = [
        c.get("text", "") for c in body.get("content", [])
        if c.get("type") == "text"
    ]
    text = "".join(text_parts).strip()
    if not text:
        print(f"FAIL: 200 OK but no text content. Full body: {json.dumps(body)[:1000]}")
        return 1

    print(f"OK (model={body.get('model', '?')}, "
          f"input_tokens={body.get('usage', {}).get('input_tokens', '?')}, "
          f"output_tokens={body.get('usage', {}).get('output_tokens', '?')})")
    print("---")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
