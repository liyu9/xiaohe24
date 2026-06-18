---
name: feishu-message-format
description: "Author text the agent sends to Feishu (Lark) so it actually renders. Hermes' default Feishu transport sends `msg_type: text` and strips markdown to plain text on fallback; tables / headers / nested lists / multi-line code blocks all degrade badly. Use when the user complains 'format didn't render right', 'table is broken', 'this looks like plain text', when writing a long explanation that needs structure, or when the user explicitly asks 'give me a card / use Feishu-friendly formatting'."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [feishu, lark, messaging, format, markdown, rendering]
---

# Feishu Message Format Constraints

Hermes Agent delivers text to Feishu via `gateway/platforms/feishu.py`. The
default path is `msg_type: text` (with a `post` rich-text attempt, falling
back to stripped plain text on any error — see `feishu.py:1789-1797`). The
plain-text fallback calls `_strip_markdown_to_plain_text(chunk)` which removes
bold, headers, table pipes, and most formatting. This is why users see
"格式未正常展示" even though the agent wrote pretty markdown.

**Goal:** write responses that survive the text-type transport AND look
structured in the Feishu client, without rewriting Hermes or the gateway.

## When the user hands you a Feishu config/integration guide

**Stop. Load `doc-against-reality-audit` first** and audit the doc against
the live system before executing anything. Feishu community guides almost
always contain tag names / config keys / version defaults that don't match
the real CardKit 2.0 API or the current Hermes gateway. The 4-step audit
(extract claims → probe live system → delta table → execute truthful
subset) is the right pattern; the
[`doc-against-reality-audit/references/feishu-card-schema-mismatches.md`](../doc-against-reality-audit/references/feishu-card-schema-mismatches.md)
catalog has the specific tag/property mismatches already verified
(`markdown` vs `lark_md`, `schema: "2.0"` at root, `tag: "form"`,
`tag: "collapse"`, `tag: "divider"` vs `hr`, etc.) so you don't have to
re-probe. Then use the 7-element matrix below as the ground-truth reference
when you actually build a card.

## What renders correctly in Feishu text messages

| Construct | Renders? | Notes |
|-----------|----------|-------|
| `**bold**` | ✅ | Becomes bold inline |
| `*italic*` | ✅ | Italic inline |
| `` `inline code` `` | ✅ | Monospace inline |
| `[label](https://url)` | ✅ | Real link |
| `- list item` (single dash) | ✅ | Bulleted list |
| `1. numbered list` | ⚠️ | Sometimes renders, sometimes not — use `① ② ③` for safety |
| `# ## ### headers` | ❌ | Stripped to plain text — replace with **bold lead-in + newline** |
| `> blockquote` | ❌ | Stripped — replace with `"…"` or indent with full-width spaces |
| **Markdown tables** `\| \| \|` | ❌ | **Feishu does not render markdown tables at all** — even the `post` rich-text path strips pipes. The only way to get table-like layout in Feishu is the `interactive` card with the `table` element, or the `post` path's `tag: "table"` block. Both require non-default message types; in the default `text` path a table collapses to a line of pipes. **Replace with bulleted field lists.** |
| Nested list (indent) | ❌ | Indentation lost — flatten |
| Multi-line code block ` ``` ` | ❌ | Often triggers fallback / truncation — use inline code with short lines |
| Emojis `🔍 ⚠ ✅ ❌` | ✅ | Render fine, good for structure |

**Two-layer rule of thumb for tables:** (1) Feishu's renderer does not
have a markdown table code path, period; (2) Hermes' default transport
_strips_ tables even if you sent them in `post` form. So you can never
rely on a table reaching the user. If you must show two-dimensional data,
either use a card or fall back to a vertical bulleted list.

## Translation table — markdown to Feishu-friendly

| Markdown | Feishu-friendly |
|----------|---------------|
| `# Header` | `**Header**\n` |
| `## Subhead` | `**Subhead**\n` |
| `\| Col A \| Col B \|\n\|---\|---\|\n\| a \| b \|` | `- **Col A**: a\n- **Col B**: b\n` (or `①②` numbered list) |
| `> quoted` | `"quoted"` (full-width quotes) |
| `1. step 1\n2. step 2` | `① step 1\n② step 2\n` |
| Multi-line code | Convert to single line: `key=value, key2=value2` |
| Nested list | Flatten with `①②` markers |
| Long code block | Show only the changed line + `[...] for full file, see <path>` |

## Length rules

- **Single message**: keep under 1500 characters. Above ~4000 chars Hermes
  starts hitting the text-type payload limit and the fallback strip activates.
- **Long answers**: split into 2-3 messages with `---` separators and
  a one-line headline at the top of each. Hermes sends these as separate
  `msg_type: text` payloads.
- **Avoid emoji-only messages** — they read as low-effort in work context.
- **Bold restraint** (2026-06-05 lesson, user pushed back: "你回复的内容有大量的加粗，很多事非必要的"; 2026-06-06 reinforcement: "你输出内容有太多符号了"):
  - **Short text messages** (≤ 300 chars): **≤ 1 `**bold**`** total. A whole-message bold lead is fine; a 3-word bold phrase is not.
  - **Long analysis** (> 300 chars): **≤ 2 `**bold**`** total, **and** the bolded text must be a **full self-contained statement** (complete sentence or paragraph), not a 2-4 character noun/verb/adjective phrase.
  - **Heuristic**: take the 3-4 characters inside `**...**`. If it stands alone as a complete claim ("no offline install" ✓), keep. If it's a word/noun that only makes sense with surrounding text ("the **doc**" ✗ / "**install**" ✗ / "**schema 2.0**" ✗), drop the bold.
  - **Don't bold enumeration labels** ("**Layer 1**: long-term memory") — write `Layer 1: long-term memory` with colon-space, no bold.
  - **Don't bold inside a `code` span** — code blocks don't render bold and the `**` comes through as literal characters.
  - **Don't bold short Chinese phrases** ("**飞书**插件", "**openclaw** 网关") — Feishu's text transport renders these as visual noise. Use plain text with a colon or dash separator: `飞书插件:`, `openclaw 网关:`.
  - This stacks on top of the table-strips-to-pipes and header-strips-to-text rules; bold is the third renderer hazard in the text path.

## "Less symbols" rule (2026-06-06 hardening)

The 2026-06-06 second-pass verification surfaced a new class of complaint
not caught by the per-element rules above: **overall output is too symbol-
heavy**. Even when every individual `**` or `|` obeys the rules, the
*total count* of markdown punctuation in a long reply still reads as
AI-generated noise in the Feishu client. Hard limits when the user is
on Feishu (or any text-transport platform):

| Element | Hard cap per message | When unavoidable, do this |
|---|---|---|
| `**bold**` | ≤ 1 short / ≤ 2 long | Bold the **whole conclusion paragraph** if you must |
| `## ### headers` | **0** | Replace with `① ② ③` numbered intro + plain text body |
| `\| --- \|` tables | **0** | Replace with `- **key**: value` bullets |
| `*` for bullets | **0** | Use `- ` (single dash, single level only) |
| `1. 2. 3.` for ordered | **0** | Use `① ② ③ ④ ⑤ ⑥ ⑦ ⑧ ⑨ ⑩` |
| `> blockquote` | **0** | Use full-width `"…"` quotes or omit |
| `` ``` `` code fences | ≤ 1, ≤ 5 lines | Convert long code to inline `key=value` |
| Emoji-only messages | **0** | Always pair emoji with at least one descriptive word |

**The "self-check" rule**: before sending any reply > 200 chars, count the
markdown punctuation. If `**` + `|` + `##` + `>` + `1.` together exceed ~5,
the reply is **too symbol-heavy** — rewrite as plain Chinese with `① ② ③`
and `- ` bullets before sending. The 2026-06-06 reading was that **the
agent's structural punctuation in a long reply can itself become the
bug** — the user reads it as "AI", not "assistant".

## When the user wants "real" Feishu cards

The user said it: "用卡片输出" / "give me a card". Feishu's
**`msg_type: interactive` (card JSON 2.0)** is the only message type that
reliably renders multi-column data, dividers, and button rows. The
default `text` path cannot show a table, no matter what markdown you
write. So if the user asks for a card, take the request literally —
either send a real card or use the `post` path's inline `tag: "table"`
blocks, **not** a markdown table in a text message.

### CardKit 2.0 — what actually works (verified 2026-06-05)

User-supplied "complete guide" docs and even official-looking community
templates often get the tag names wrong. The schema below is verified
by sending each element to a real Feishu app and observing both the
**API response (code)** AND the **server-side stored content pulled
back via GET** — not from a doc. **The stored content is what the
client renders; that's the only ground truth.** Earlier versions of
this skill got the div+lark_md story wrong because they only checked
the API code (200 OK) and never pulled back the stored content.

**7-element matrix, all from real probe (2026-06-05):**

| Top-level element | API code | Stored content (after GET) | Renders as card? |
|---|---|---|---|
| `{"tag":"div","text":{"tag":"lark_md","content":"**x**"}}` | 0 | `{"tag":"text","text":"x"}` (div stripped, `**` lost) | **❌ Rich text fallback** |
| `{"tag":"lark_md","content":"**x**"}` | 230099 | — | — (rejected at top level) |
| `{"tag":"markdown","content":"**x**"}` | 0 | `{"tag":"text","text":"x"}` (markdown rendered, then stripped) | **✅ Real card with bold** |
| `{"tag":"plain_text","content":"x"}` | 230099 | — | — (rejected) |
| `[[{tag:"lark_md"}]]` (post format top-level) | 230001 | — | — (wrong content shape) |
| `{"tag":"hr"}` | 0 | empty row | ✅ (visible rule) |
| `{"tag":"note","elements":[...]}` | 0 | note elements flattened | ✅ for short captions |
| `{"tag":"form","elements":[input,selectMenu,datePicker,button]}` | 0 | form subtree dropped | **❌ entire form invisible** (schema 1.0 only) |

**The right way to send a card with markdown body (verified):**

```json
{
  "config": {"wide_screen_mode": true, "streaming_mode": true},
  "header": {"title": {"tag": "plain_text", "content": "🤖 Title"}, "template": "blue"},
  "elements": [
    {"tag": "markdown", "content": "**bold** *italic* `code`\n\n- list\n- list\n\n```python\nprint('hi')\n```"}
  ]
}
```

The `tag: "markdown"` element at top level (NOT wrapped in `div`, NOT
renamed to `lark_md`) is the one Feishu actually renders as a card with
real markdown formatting. **Do not trust any "lark_md" advice** — it
gets 230099 at top level and gets stripped when wrapped in `div`.

**⚠️ 2026-06-05 second-pass verification — important correction:**

The 7-element matrix above was correct for **content-only** cards. In a
follow-up probe the user pasted back the **actual rendered output** of
both `tag:"markdown"` and `div+lark_md` variants. Findings:

- `tag: "markdown"` at top level (with or without `"schema":"2.0"`) —
  the user **confirmed** it renders as a real card in the IM client
  (header bar + bold/list/links work).
- `tag: "div"` wrapping `tag: "lark_md"` — also **confirmed** by user
  to render as a card, BUT the markdown is **not parsed** inside
  `lark_md`: bold/italic/list markers come through as literal
  `**...**` and `- ...` characters. The GET-back trace that showed
  `tag:"text"` was a server-side flatten; the IM client at that point
  had already started honoring `div+lark_md` but was rendering the
  literal escape characters — that's why the user pasted back text
  like `**+ - 列表项` and `print('hi')` with backslashes preserved.
- `tag: "lark_md"` directly under `body.elements` (no `div` wrapper) —
  user confirmed this also renders as a real card. This is the **JSON
  2.0 standard structure**: `{schema:"2.0", body:{elements:[{tag:"lark_md", content:"..."}]}}`.

**Practical rule, post-2026-06-05 second-pass:**

- **Default for content-heavy cards**: `tag: "markdown"` at the top of
  the elements list. Survives all clients, parses full markdown,
  simplest structure.
- **If you need `div` for layout** (column_set, fields, two-line text):
  use `{"tag": "div", "text": {"tag": "lark_md", "content": "..."}}` —
  it renders as a card, but **don't expect markdown to be parsed
  inside `lark_md`**. Use plain text formatting or split into multiple
  `div` blocks.
- **Never** put `tag: "lark_md"` at the elements-array top level outside
  of `body` — 230099 rejected. Inside `body.elements` (JSON 2.0
  structure) it works.

**Common pitfalls verified by 230099 / 230001 errors:**

- `tag: "markdown"` inside `div` text field — gets div stripped, the
  `**xx**` becomes literal characters
- `tag: "lark_md"` anywhere — 230099 unsupported
- `tag: "code"` as a top-level element — use fenced ```block``` inside
  a `markdown` element instead
- `tag: "collapse"` with sub-elements — unsupported; use a `markdown`
  list with clear separators
- Top-level `schema: "2.0"` — 230099 unknown property `elements`; omit it
- `tag: "form"` / `tag: "input"` / `tag: "selectMenu"` / `tag: "datePicker"`
  at any nesting level — **all silently dropped** in CardKit 2.0 / `interactive`
  message type. The API returns `code:0` and the message_id, but the
  Feishu IM client renders these elements as **nothing** (button does
  not appear, form fields do not appear, only sibling `hr` / `note`
  elements that happen to use the same schema show up). Verified
  2026-06-05 by sending a 4-field form (`input` + `selectMenu` +
  `datePicker` + submit `button` wrapped in `form`) to a real DM;
  HTTP 200 + `code:0` + valid `message_id`, but user reported "没有按钮"
  (no button visible) — the entire form subtree was dropped on the
  client. These are **schema 1.0-only** elements; they survive in the
  old `post` rich-text transport but are stripped from `interactive`
  cards. There is no in-card way to collect structured user input in
  CardKit 2.0 — buttons with `value: {"action": "..."}` are the only
  reliable interactive primitive. Treat any "guide" that shows a
  `form` container in an `interactive` card as stale schema 1.0 docs.

**`header.template` accepts these colors:** `blue`, `red`, `green`,
`yellow`, `purple`, `orange`, `grey`. Anything else is silently
ignored or rejected depending on the field validator.

**Interactive elements that actually work in `interactive` / CardKit 2.0** (verified 2026-06-05):
- `tag: "markdown"` — text with full markdown (bold/italic/list/code/links)
- `tag: "button"` inside an `actions` container — clickable; value
  must be `value: {"action": "..."}`; subscribed via `card.action.trigger`
  event; **the only reliable way to collect a click from the user**
- `tag: "hr"` — visible divider
- `tag: "note"` — small caption text under the main card
- `tag: "collapsible_panel"` — folded/expanded section (mentioned in
  the user's guide, not independently verified in this session)
- `tag: "standard_icon"` — icon prefix on a markdown element
- `actions` container — wraps one or more buttons in a row

**Interactive elements that DO NOT work in `interactive` (silent drop):**
form / input / selectMenu / datePicker / checkbox / picker (person/date)
— all schema 1.0-only. The card sends fine (HTTP 200, `code:0`) but
the client renders nothing for the dropped subtree. See the pitfall
entry above for the full reproduction. If you need structured input
from the user, use buttons that branch the conversation or ask in a
follow-up text message.

**`action` button values** must use `value: {"action": "..."}` not
`action: {...}` — the former is the callback-data contract for
`card.action.trigger` events. Subscribe to that event in the app
config or clicks return `200340`.

**Streaming / PATCH updates:** set `streaming_mode: true` in config,
then PATCH the same `message_id` to update content in place. Throttle
to 200ms (Feishu app-level limit is 10/sec). Use `seq` field for
ordering to avoid out-of-order PATCHes during long-running tasks.

**Direct test recipe** (use this to verify any card before sending in
production — ALWAYS pull back via GET, do not trust 200 OK alone):

```python
# Send the card
import json, time, urllib.request
url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
body = {"receive_id": "ou_xxx", "msg_type": "interactive",
        "content": json.dumps(card_json, ensure_ascii=False)}
req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
        method="POST")
result = json.loads(urllib.request.urlopen(req, timeout=10).read())
assert result["code"] == 0, f"send failed: {result}"
mid = result["data"]["message_id"]

# Pull back to confirm stored structure
time.sleep(1)
get_url = f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}"
get_req = urllib.request.Request(get_url,
        headers={"Authorization": f"Bearer {token}"})
stored = json.loads(urllib.request.urlopen(get_req, timeout=10).read())
content = stored["data"]["items"][0]["body"]["content"]
# If content starts with {"title":...,"elements":[[{tag:text}...]]}
# your div/markdown structure was STRIPPED. Use tag:"markdown" at top.
# code 230099 = schema error; check tag names and properties
# code 200340 = button click without card.action.trigger subscription
```

Card features Feishu supports that text messages do NOT:

- `tag: "table"` — two-dimensional layout that survives in `post` rich-text
  messages (this is the closest you can get to a "real" table in a message
  the user is going to forward)
- `tag: "hr"` — visible horizontal rule
- Multi-line code blocks with monospace background (use fenced ``` inside
  a `markdown` element)
- Clickable buttons, image carousels, `select` menus
- Headers with colored backgrounds

To get cards via Hermes:

1. **Option A — explicit card payload via the `feishu-enhanced` skill**:
   write the card JSON to a file and call `feishu-api.sh send` with
   `msg_type=interactive` or `msg_type=post`. Requires
   `FEISHU_APP_ID` + `FEISHU_APP_SECRET` in `~/.hermes/.env` and the app
   to have `im:message` scope. **This is the right path** when the user
   explicitly asks for a card.

**2. **Option B — patch `gateway/platforms/feishu.py:_build_interactive_card_payload`**:
   the function builds card JSON; the verified-correct structure is
   `tag: "markdown"` at top level (not `div` wrapping `lark_md`).
   Earlier patches using `div`+`lark_md` were 200 OK but rendered as
   rich text in the client — always pull back via GET to confirm.
   Reverts on `hermes update`.

   **Pitfall (2026-06-05, in-session)**: the agent's session memory
   contained a stale claim "tag: markdown → tag: lark_md is the fix
   for real Feishu cards". That memory is **inverted**. In CardKit
   2.0 the only verified-working approach is `tag: "markdown"` at
   top level. `tag: "lark_md"` gets 230099 at top level, 230001 in
   post shape, or gets stripped if wrapped in `div`. The user
   confirmed a `div+lark_md` patch was still showing as escape
   characters (`\+`, `\*\*`) in the IM client — definitive proof
   the patch was wrong. **Before patching `_build_interactive_card_payload`**,
   search this skill (or its previous version) for the verified
   matrix; do not trust session-memory notes that pre-date the
   2026-06-05 verification probe.

   **Workflow pitfall (2026-06-05)**: when 4+ direct API calls all
   returned code=0 and the user is still seeing wrong output, **stop
   testing and ask the user what they see in the client**. The
   server stores `elements: [[{tag:"text"}...]]` (post-format
   flattening) regardless of what element shape you sent — the API
   response is not ground truth. Only the user's screen is ground
   truth.

3. **Option C (recommended for routine answers)**: keep using text
   messages, but follow this skill's translation table. The user gets
   80% of the card's visual quality with 0% of the engineering cost.
   Save cards for high-stakes deliverables (release notes, incident
   reports) where the work justifies it.

4. **Option D — `msg_type: "post"` with `zh_cn.title`** (the *historical*
   real-card path, confirmed in this session 2026-06-05). This is
   distinct from `interactive` and is what produced the original
   "📊 腾讯行情 / 🔄 数据备份" cards the user has seen as real blue-header
   cards in groups. The verified shape:

   ```json
   {
     "msg_type": "post",
     "content": {
       "zh_cn": {
         "title": "📊 腾讯 00700 实时行情",
         "content": [
           [{"tag": "text", "text": "..."}],
           [{"tag": "text", "text": "..."}],
           [{"tag": "hr"}],
           [{"tag": "a", "text": "label", "href": "https://..."}]
         ]
       }
     }
   }
   ```

   `zh_cn.title` is what produces the colored header bar. Inside
   `content`, `tag: "text"`, `tag: "a"`, `tag: "hr"`, and
   `tag: "media"` (images) are the supported row elements. `lark_md`
   does NOT belong in `post` row content either (230001 wrong tag).
   This path is the right choice when you want a real card **without**
   patching `_build_interactive_card_payload` or installing a plugin —
   just send the `post` payload directly.

5. **Option E — `hermes_feishu_plugin` v0.6.0** (path the user
   previously confirmed for "real cards" in groups as of the 6-04
   session). This is a different code path than
   `_build_interactive_card_payload` — the plugin wraps the response
   in a card template using `div`+`lark_md` correctly. If the
   gateway already has this plugin loaded and the user is getting
   real cards in groups but plain text in DMs, the issue is
   `feishu.py:1840-1866` silent fallback to `_strip_markdown_to_plain_text`
   on certain DM-side `interactive` failures — debug by adding
   `logger.warning` around the fallback path, not by patching card
   element shape.

**Decision rule:** if the answer is more than 5 rows of multi-column data
**or** the user said "卡片" / "card" / "表格不乱" explicitly, build a
`post` rich-text message with `tag: "table"`. Otherwise, use the
translation table above in a regular text message.

## Workflow — when you finish a long answer, audit it

Before sending anything >500 chars to Feishu, scan once:

- [ ] No `## headers` → replaced with `**Bold**`
- [ ] No markdown tables → replaced with `- **key**: value` lists
- [ ] No `> quotes` → replaced with `"…"` or removed
- [ ] No nested indentation → flattened
- [ ] No multi-line code blocks >3 lines → collapsed to inline or omitted
- [ ] Total length under 1500 chars (or split with `---` and headline)
- [ ] Lists use `-` not `*` and not `1.`

If you catch yourself about to write a table, **stop and rewrite as a list
right then** — tables will not survive the text transport, and rewriting
post-hoc is more work than getting it right the first time.

## Verification pitfall (2026-06-05 lesson)

A card that returns `code: 0` and has `msg_type: "interactive"` in the
response can **still** render as plain rich text in the Feishu client
if the `tag: "div"` wrapping or `tag: "lark_md"` inner element got
stripped on the server side. **Always** pull the stored message back
via `GET /im/v1/messages/{message_id}` and inspect the `body.content`
JSON — if it shows `elements: [[{tag: "text"}...]]` (post-format
flattening), the client is going to render plain text, not a card.
This is a server-side transformation you cannot see from the send
response alone.

## Reference files

- `references/feishu-transport-flow.md` — what feishu.py actually does
  on the wire for text/post/interactive message types (line numbers, the
  silent fallback, what the strip removes, the card JSON path)
- `templates/send_feishu_card.py` — drop-in Python script that posts an
  interactive card via `im/v1/messages`. Card JSON structure uses
  `tag: "markdown"` at top level (the verified-correct shape), with
  optional header color (7 templates) and action buttons. Use this
  when you need a real card right now, without the `feishu-enhanced`
  skill.
