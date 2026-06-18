# Feishu CardKit 2.0 Schema — Verified Mismatches in User-Supplied Guides

When a user (or a community post) hands you a "Feishu card template"
JSON or a "complete Hermes-Feishu integration guide" that includes
sample cards, the JSON almost always contains at least one tag or
property the real CardKit 2.0 API rejects with `code 230099` or
`code 200621`. The reason: a lot of circulating templates were
written against older CardKit 1.0 docs, or transcribed by humans
who mixed up the markdown flavor (Feishu `lark_md` vs. standard
markdown vs. Lark legacy `markdown`).

The 4-step audit workflow in `SKILL.md` is the right pattern; this
reference is the shortcut catalog so the next audit doesn't have to
re-probe.

## Mismatches (verified 2026-06-05 against `https://open.feishu.cn`)

| Doc / community claim | What API actually expects | API error when wrong |
|---|---|---|
| `{"tag": "markdown", "content": "..."}` **at any level** (top-level or inside `div`) | `{"tag": "div", "text": {"tag": "lark_md", "content": "..."}}` — `lark_md` **must** be nested under `div.text`, never at root | **200 OK** but rendered as plain rich-text with literal `**asterisks**` visible (no card visual, no header bar) — the **silent** failure mode that makes users think "private chat is broken" |
| `{"tag": "lark_md", "content": "..."}` directly in `elements` (not under `div`) | Wrap in `div`: `{"tag": "div", "text": {"tag": "lark_md", ...}}` | `230001 message_content has wrong tag:{lark_md}` |
| `{"tag": "div", "text": "string content"}` (text as string) | `text` must be an object: `{"tag": "div", "text": {"tag": "lark_md", "content": "..."}}` | `230099 ErrCode 200621: parse card json err` |
| `{"tag": "code", "language": "python", "content": "..."}` as a top-level element in `elements` | Embed ` ```python\n...\n``` ` inside a `lark_md` div, or use the `code` element only at the **message root** in the `post` rich-text path (different transport, not the interactive card path) | `230099` (in interactive card path) |
| `{"tag": "collapse", "title": {...}, "expanded": false, "elements": [...]}` | Flatten to a `lark_md` list, or use `>` blockquote, or just a fenced code block | `230099 unsupported type of block` |
| `{"tag": "divider"}` | `{"tag": "hr"}` (this is the real CardKit 2.0 tag name; `divider` is a no-op that confuses readers because it doesn't render) | `230099` (silently rejected) |
| `{"tag": "form", "elements": [input, selectMenu, datePicker, button]}` at any nesting level | **There is no in-card replacement** for form containers in CardKit 2.0. Use one or more `button` elements with `value: {"action": "..."}` for user input; the action callback carries the click but **no form values** (so for multi-field input, ask in a follow-up text message or branch the conversation into a button-driven flow) | **HTTP 200 + code:0 + valid message_id**, but the entire form subtree is silently dropped on the client — buttons and form fields do not appear. Only sibling `hr` / `note` elements that use the same schema survive. Confirmed 2026-06-05 by sending a 4-field form to a real DM; user reported "没有按钮" (no button visible). `form` / `input` / `selectMenu` / `datePicker` are schema 1.0-only — they work in the old `post` rich-text transport but are stripped from `interactive` cards. |
| Top-level `"schema": "2.0"` together with `"elements": [...]` | Omit `schema` at root; put schema in `config` if you need it | `230099 ErrCode 200621: unknown property` |
| `{"action": {"type": "callback", "value": {"action": "ok"}}}` | `{"value": {"action": "ok"}}` directly on the button | Button click returns `200340` if the app isn't subscribed to `card.action.trigger` event; the `action: {...}` nested form is silently ignored |
| `header.template: "primary"` / `"info"` / `"success"` | One of: `blue`, `red`, `green`, `yellow`, `purple`, `orange`, `grey` | Silently ignored (falls back to blue) |
| `streaming_mode: true` without `seq` field on PATCH | Add `seq: <incrementing-int>` to PATCH body | PATCHes arrive out of order under load, content flickers |
| `"markdown"` table syntax inside `lark_md` content (`\| \| \|`) | Markdown tables do **not** render in cards at all — use `tag: "table"` (interactive) or rewrite as a vertical list with `**Header:**` | Pipes show as literal pipes, no layout |

## Why guides keep getting it wrong

1. **CardKit 1.0 used `markdown`**, CardKit 2.0 renamed to `lark_md`.
   Older guides copy-paste the old tag name.
2. **The `schema: "2.0"` field exists in OpenClaw template examples**
   but in raw CardKit 2.0 interactive messages, the root accepts only
   `config`, `header`, `elements` (and the `i18n_*` variants for
   localized cards). `schema` is not a recognized top-level property.
3. **Markdown inside `lark_md` is not full CommonMark.** Bold,
   italic, lists, code fences, and `>` quotes work. Tables, nested
   lists, and HTML do not. Templates that show "rich markdown" render
   to nothing or to literal pipes.
4. **The "collapse" pattern from the docs is for `post` rich-text
   blocks, not interactive cards.** Same with the `tag: "code"`
   element. Confusing the two transports causes the silent
   230099s.

## Audit recipe (fastest path to a working card)

When a user-supplied template fails, run this in order:

1. **Identify the root**: should be a dict with `config` + optional
   `header` + `elements` list. No `schema: "2.0"` at root.
2. **Walk every element**: replace `tag: "markdown"` → `tag: "lark_md"`,
   replace `tag: "code"` (top-level) → fenced code block inside lark_md,
   replace `tag: "collapse"` → flat list / `>` quote / fenced block.
3. **Test against the live API** (the only ground truth):

   ```python
   import json, urllib.request, urllib.error
   token = get_tenant_token()  # from feishu_credentials.json
   url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
   body = {"receive_id": "ou_xxx", "msg_type": "interactive",
           "content": json.dumps(card, ensure_ascii=False)}
   req = urllib.request.Request(url, data=json.dumps(body).encode(),
           headers={"Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8"},
           method="POST")
   try:
       r = json.loads(urllib.request.urlopen(req, timeout=10).read())
   except urllib.error.HTTPError as e:
       r = {"code": e.code, "http_error": True,
            **json.loads(e.read() or b"{}")}
   if r.get("code") != 0:
       # 230099 → schema mismatch; walk the elements again
       # 200340 → subscribe to card.action.trigger event
       # 230020/230021 → app permission missing
       raise RuntimeError(f"card rejected: {r}")
   ```

4. **Verify rendering**: after a successful send, the receiver
   should see the header color, the bold/list/quote in the body, and
   the buttons. If the receiver sees `**literal asterisks**` in the
   card, the body is being delivered as plain text — that means the
   message is falling back to `msg_type: "text"` somewhere in the
   Hermes transport, not a card problem. Check
   `gateway/platforms/feishu.py:_build_outbound_payload` and
   `_POST_CONTENT_INVALID_RE` fallbacks.

## PATCH / streaming specifics (for long-running task cards)

When updating a card mid-task (e.g., Claude Code progress card
PATCHing every 200ms):

- Throttle: 200ms minimum between PATCHes (10/sec/app is the hard cap).
- `seq` field: increment monotonically per message_id. Without it,
  PATCHes reorder under concurrent updates.
- The same `message_id` is the only thing that needs to be tracked
  on the caller side; Feishu returns it from the initial `create`.
- On completion, send a **new** card (different `message_id`) with
  the final result — do not PATCH the progress card into a result
  card, because recipients forwarding the message get the progress
  history either way.
- Token caching: `tenant_access_token` has a 2h TTL, refetch with
  60s buffer. Don't re-fetch on every call.

## How to extend this catalog

When a new mismatch turns up that isn't here:

1. Add a row in the **Mismatches** table with the doc claim, the
   real API expectation, and the exact `code + ErrCode` you got back.
2. Note the Hermes / CardKit version you verified against
   (e.g. "verified CardKit 2.0, June 2026").
3. If the rejection was on a Hermes-internal fallback (not the raw
   Feishu API), note that separately — the fix is in
   `gateway/platforms/feishu.py`, not in the card JSON.
