#!/usr/bin/env python3
"""
vision_probe.py — End-to-end vision probe for a Hermes `auxiliary.vision` config.

Reproduces the exact request Hermes will make when vision_analyze is called
against a custom provider. Use this to verify that:
  - The provider accepts image input (not all custom providers are multimodal)
  - The api_mode/protocol (anthropic_messages, openai_chat, etc.) is right
  - The api_key is valid and has the right scope
  - The model name resolves on the provider's model list

Usage:
  python vision_probe.py \\
    --image /path/to/image.jpg \\
    --provider anthropic_messages \\
    --base-url https://api.minimaxi.com/anthropic \\
    --model MiniMax-M3 \\
    --api-key sk-cp-... \\
    --question "Describe this image in detail."

Exit codes:
  0  probe returned 200 with non-empty assistant content
  1  configuration / network error (printed)
  2  HTTP error from the provider (status + body printed)
  3  probe returned 200 but no assistant content (likely model doesn't support vision)
"""

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request


def build_anthropic_request(image_b64, media_type, model, question, api_key, max_tokens=1024):
    return urllib.request.Request(
        "https://api.example.invalid/v1/messages",  # placeholder, replaced below
        data=json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64,
                    }},
                    {"type": "text", "text": question},
                ],
            }],
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )


def build_openai_request(image_b64, media_type, model, question, api_key, max_tokens=1024):
    return urllib.request.Request(
        "https://api.example.invalid/v1/chat/completions",  # placeholder, replaced below
        data=json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:{media_type};base64,{image_b64}",
                    }},
                    {"type": "text", "text": question},
                ],
            }],
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True, help="Path to image file (JPEG/PNG/WebP)")
    p.add_argument("--provider", required=True,
                   choices=["anthropic_messages", "openai_chat"],
                   help="API protocol to use")
    p.add_argument("--base-url", required=True,
                   help="Provider base URL, e.g. https://api.minimaxi.com/anthropic")
    p.add_argument("--model", required=True)
    p.add_argument("--api-key", required=True)
    p.add_argument("--question", default="Describe this image in detail.")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--timeout", type=int, default=60)
    args = p.parse_args()

    # Load + encode image
    if not os.path.isfile(args.image):
        print(f"ERROR: image not found: {args.image}", file=sys.stderr)
        sys.exit(1)
    media_type, _ = mimetypes.guess_type(args.image)
    if media_type is None:
        media_type = "image/jpeg"
    with open(args.image, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("ascii")

    # Build request
    if args.provider == "anthropic_messages":
        url = args.base_url.rstrip("/") + "/v1/messages"
        req = build_anthropic_request(
            image_b64, media_type, args.model, args.question,
            args.api_key, args.max_tokens)
    else:
        url = args.base_url.rstrip("/") + "/v1/chat/completions"
        req = build_openai_request(
            image_b64, media_type, args.model, args.question,
            args.api_key, args.max_tokens)
    req.full_url = url  # override the placeholder

    # Fire
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            print(f"STATUS: {r.status}")
            print(f"BODY: {body[:4000]}")
            # Check that there's actual assistant content
            if args.provider == "anthropic_messages":
                data = json.loads(body)
                content = data.get("content", [])
                text_blocks = [b for b in content if b.get("type") == "text"]
                if not text_blocks or not text_blocks[0].get("text", "").strip():
                    print("PROBE FAILED: 200 OK but no text content (model not multimodal?)",
                          file=sys.stderr)
                    sys.exit(3)
            else:
                data = json.loads(body)
                choices = data.get("choices", [])
                if not choices or not choices[0].get("message", {}).get("content", "").strip():
                    print("PROBE FAILED: 200 OK but no content (model not multimodal?)",
                          file=sys.stderr)
                    sys.exit(3)
            print("\nPROBE OK: vision pipeline works end-to-end")
            sys.exit(0)
    except urllib.error.HTTPError as e:
        print(f"HTTP ERROR: {e.code}", file=sys.stderr)
        print(f"BODY: {e.read().decode('utf-8', errors='replace')[:2000]}", file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print(f"NETWORK ERROR: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON PARSE ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
