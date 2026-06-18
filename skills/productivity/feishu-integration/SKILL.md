---
name: feishu-integration
description: "Hermes ↔ Feishu (Lark) integration: how the agent **writes** structured data to Feishu Bitable/Doc/Drive via the OpenClaw gateway, and how the agent **renders** text/cards so they actually show up in the Feishu client. Load when the user says '记一下我刚 X 了' / '记录 Y' / '写进飞书表格' / 'log my X to a table' / 'auto-write to a Feishu Bitable' (intake path), OR '格式没渲染对' / '表格是乱的' / '用卡片输出' / 'give me a card' / 'Feishu-friendly formatting' (render path), OR 'create a Hermes plugin that writes to Feishu' (build path). Covers the OpenClaw /tools/invoke contract for 14 Feishu tools, the pre_llm_call keyword-scrape + intake-signal pattern for silent auto-capture, the Feishu CardKit 2.0 verified-correct shapes (tag: markdown at top level, NOT lark_md), the 7-element matrix of what actually renders, the markdown-to-Feishu translation table (no headers, no tables, no blockquotes, ≤ 1 bold short, ≤ 2 bold long, ① ② ③ for ordered), and the never-invent-data honesty contract for real-world event logging."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [feishu, lark, bitable, plugin, auto-log, openclaw, card, cardkit, markdown, render, pre-llm-call]
    absorbed_from: [feishu-message-format, bitable-auto-logger]
    related_skills: [hermes-infrastructure, agent-execution-anti-stall-rules]
---

# Feishu Integration (Hermes ↔ Feishu)

Two surfaces, one platform. Hermes interacts with Feishu in two distinct ways that **must not be confused**:

1. **Output / render** — the text and cards the agent **sends** to the user, and how they survive Hermes' default `text` transport.
2. **Intake / auto-capture** — the structured rows the agent **writes** to Feishu Bitable on the user's behalf, in the background, when an event keyword is detected in chat.

Plus the build path: how to **create a Hermes plugin** that does (2) via the OpenClaw gateway.

This umbrella is the dispatch surface. Each labeled section below is self-contained — load just the one you need.

## When to load

| User says | Jump to |
|---|---|
| "记一下我刚 X 了" / "记录 Y" / "写进飞书表格" / "log my Z to a table" / "auto-write to a Bitable" | [§1 Bitable auto-capture (intake)](#1-bitable-auto-capture-intake) |
| "create a Hermes plugin that writes to Feishu" / "auto-log X to a Bitable" | [§1.2 Build a Hermes plugin](#12-build-a-hermes-plugin-via-openclaw) |
| "格式没渲染对" / "表格是乱的" / "格式未正常展示" / "use a card" / "give me a card" / "Feishu-friendly formatting" | [§2 Feishu message format constraints](#2-feishu-message-format-constraints-render) |
| "用卡片输出" / "build a Feishu card" / "send_feishu_card" | [§2.4 When the user wants a real card](#24-when-the-user-wants-a-real-card) |
| "hermes_allergy_logger 怎么写" / "openclaw 怎么调 feishu_bitable_*" | Cross-ref `hermes-infrastructure` §4 + `references/bitable-hermes-allergy-logger-example.py` |
| "What does this Feishu guide / 接入教程 claim?" | [§3 Doc-against-reality-audit dispatch](#3-doc-against-reality-audit-dispatch) |

Skip this skill if the user wants a single API call to a Feishu tool without rendering concerns and without auto-capture — that is just calling OpenClaw, see `hermes-infrastructure` §4.

---

## 1. Bitable auto-capture (intake)

End-to-end pattern for a Hermes plugin that **watches every inbound user message**, detects a defined event (intake of a medication, coffee, a run, a purchase, a payment), and **writes one structured row to a Feishu Bitable** via the OpenClaw gateway — without the user explicitly asking. Built 2026-06-06 for the `hermes_allergy_logger` plugin.

### When

- User says "记一下我刚 X 了" / "记录 Y" / "自动写入" / "log my Z" / "save to table"
- User mentions a recurring personal event and wants passive capture
- The data is small per event (1-5 fields, fits one Bitable row)
- The user is on Feishu (or any text channel that flows into the LLM hook)
- The plugin should be **silent** when the user does not mention the event

Skip this skill if the user wants to log via an explicit command (`/log coffee`), or if the data is large enough to warrant a Doc instead of a Bitable row.

### Why a plugin (not direct LLM tool use)

Three reasons:

1. **Capture is automatic.** The user does not have to remember a slash command. The hook fires on every message; if a keyword + intake-signal is present, a row is written.
2. **The LLM is a great keyword extractor but a poor silent recorder.** If the LLM has to call the tool, it has to also respond to the user, which costs an LLM turn and a confirmation round-trip. The plugin writes in a background thread, the LLM never knows.
3. **Honesty contract.** A plugin that asks the LLM "did the user say they took a drug?" can be tricked; a plugin that scans the raw message and parses fields deterministically is auditable. Critical for any "I'm logging real-world events" use case.

### Architecture

```
User message ─→ Hermes LLM loop
                       │
                       │ pre_llm_call hook
                       ▼
        ┌──────────────────────────────┐
        │ hermes plugin (Python)        │
        │  1. keyword hit?              │
        │  2. intake-signal present?    │
        │  3. parse dose / symptom      │
        │  4. if missing → inject ctx   │
        │  5. if all present →         │
        │     background thread:        │
        │       POST /tools/invoke     │
        │       feishu_bitable_create_  │
        │       record                 │
        └──────────────────────────────┘
                       │
                       ▼
                 OpenClaw gateway
                 (127.0.0.1:18789)
                       │
                       ▼
                 Feishu Bitable
```

The plugin never touches the Feishu API directly. It always goes through OpenClaw's `feishu_bitable_*` tools. The plugin gets LLM-hook integration; OpenClaw owns the Feishu client and its auth/refresh logic. For the OpenClaw install + `POST /tools/invoke` contract, see `hermes-infrastructure` §4.

### Honesty contract (CRITICAL)

The principal pushed back 2026-06-06: **"症状不要瞎编，我是荨麻疹，头、胯下痒"**. The plugin's earlier version auto-filled "鼻塞" as the default symptom because that was a common pattern. The agent had been **making up a value for a real-world event the user actually had data on**. That is a non-trivial trust violation — the user relies on the log to look back at their allergy history, and a fabricated "鼻塞" entry corrupts that history permanently.

**Encode the rule in the plugin's parsing layer, not in the LLM's behavior.** The LLM can be re-prompted, will sometimes guess, will sometimes hallucinate. The plugin code is the durable guard. The parser returns `""` for any field the user did not explicitly state, and the writer refuses to write a row with any empty field.

**The same pattern applies to:**

- Coffee: do not guess "小杯" if the user said "喝了杯咖啡" without specifying size. Leave the column empty.
- Expense: do not guess the amount from a fuzzy "花了几十块" — refuse to write.
- Workout: do not guess the duration from a vague "跑了会儿" — leave the duration column empty.
- Medication: do not guess dose, do not guess symptom (the original bug), do not guess the drug if only an alias is used and the alias-to-generic mapping is ambiguous.

**The "ask the user" branch (return `{"context": ...}`) is the right behavior when a required field is missing.** The user explicitly prefers "ask" to "guess" for real-world event logging. The LLM can deliver the question naturally as part of its reply.

### Reference files for §1

- `references/bitable-rest-cheatsheet.md` — direct Feishu REST endpoints, field types, error codes, the setup-to-runtime handoff (one-time setup path; runtime always goes through OpenClaw)
- `references/bitable-keyword-patterns.md` — common keyword/intake-signal sets by event class (drug names, food names, exercise names, expense phrasing) the parser can lean on
- `references/bitable-hermes-allergy-logger-example.py` — full working plugin source (the 2026-06-06 `hermes_allergy_logger`, canonical example)
- `templates/bitable-plugin-skeleton.py` — minimal ready-to-fill-in plugin skeleton
- `templates/bitable-plugin.yaml` — manifest template with config schema and `pre_llm_call` hook declaration
- `templates/bitable-setup.sh` — one-shot Feishu REST setup script (create app + table + fields, write test row, clean up)

### Pitfalls (intake path)

1. **Plugin location: `~/.hermes/plugins/`, not `~/.hermes/hermes-agent/plugins/`.** The latter is the in-repo tree and gets clobbered on `hermes update`. The user-local tree is durable.
2. **Write-protect on `~/.hermes/.env` and `~/.hermes/config.yaml`.** Use shell `cat >> .env <<EOF` to append; or have the user paste the block manually.
3. **Don't write a row with empty fields.** Downstream table reader sees `症状=空`, etc., and the data is permanently lost. Refuse to write; inject a `context` reminder to the LLM.
4. **Don't write via direct urllib + tenant_access_token at runtime.** That is the one-time setup path. Runtime goes through OpenClaw. Mixing the two means two different auth/refresh flows.
5. **Don't store the OpenClaw token in `MEMORY.md`.** Belongs in `~/.hermes/.env` only. `MEMORY.md` is injected into every session prompt — chat history is the leak vector.
6. **Don't block the LLM on the write.** The hook returns immediately, the write happens in a daemon thread. If the LLM is waiting for the hook to return, you have the threading wrong.
7. **Don't invent a default column value because "most users mean X".** The principal reads the Bitable back and notices the lie.
8. **Don't use `tag: "form"` / `tag: "input"` / `tag: "selectMenu"` for the data-entry UI.** Feishu CardKit 2.0 silently drops these. Use a plain text message + LLM-asks-follow-up-question pattern (see §2.4).
9. **Background process pattern: use `terminal(background=true)`, not `nohup ... &`.** Hermes blocks shell-level background wrappers.
10. **Restart the gateway after writing the plugin.** New plugins are only discovered on gateway startup. A plugin that "isn't working" often just hasn't been loaded yet.

### End-to-end smoke test (BEFORE reporting done)

The `verification = done` rule from the agent's standing preferences: **do not report the plugin as working until a real chat-style message produces a real Bitable row.** Minimum smoke:

```python
import importlib.util
spec = importlib.util.spec_from_file_location("h", "/path/to/plugin/__init__.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.on_pre_llm_call(messages=[{"role": "user", "content": "我刚吃了10mg氯雷他定，荨麻疹又发了"}])
assert result == {}, f"expected silent write, got {result}"

import time; time.sleep(2)
verify_resp = openclaw_invoke("feishu_bitable_list_records", {
    "app_token": APP_TOKEN, "table_id": TABLE_ID, "page_size": 5
})
records = json.loads(verify_resp["result"]["content"][0]["text"])["records"]
assert any("氯雷他定" in str(r.get("fields", {})) for r in records), \
    f"no row found in {records}"
print("✅ end-to-end smoke passed")
```

Then do the three negative cases (each must behave as designed):

| Message | Expected hook return |
|---|---|
| "我刚吃了10mg氯雷他定，荨麻疹又发了" | `{}` (silent write) |
| "我刚吃了10mg氯雷他定" | `{"context": "请告诉我症状"}` (no write) |
| "这药副作用大不大" | `{}` (no write, no follow-up — bare mention) |
| "我刚服了" (no drug name) | `{}` (no write) |

---

### 1.2 Build a Hermes plugin via OpenClaw

The minimal 5-step recipe. The full worked example (the 2026-06-06 `hermes_allergy_logger`) is in `references/bitable-hermes-allergy-logger-example.py`.

#### Step 1: Decide the schema
For `hermes_allergy_logger`, the 5-column schema was:

| Column | Type | Source |
|---|---|---|
| 服药时间 | DateTime (ms epoch) | `int(time.time() * 1000)` |
| 药品名 | Single-select | regex hit on keyword set |
| 剂量 | Single-select | regex `\d+\s*(mg\|片\|颗)` |
| 症状 | Single-select | keyword match |
| 备注 | Text | first 200 chars of message |

For a coffee-tracker: 时间 / 咖啡类型 / 杯型 / 备注. Rule: ≤ 8 columns, every column has a deterministic regex parse path OR is left empty. **No column that requires LLM reasoning to populate.** LLM calls inside the hook defeat the silent-recorder property.

#### Step 2: Pre-create the Bitable (one-time setup)
Before the plugin can write, the Bitable must exist. **Pre-create at install time** so the user is not asked "is the table ready?" at runtime. The 2026-06-06 approach used direct Feishu REST calls (urllib + `tenant_access_token`) to create the app + table + 5 fields + write a test row. That is a one-shot script (`templates/bitable-setup.sh`), **not** a runtime path. Runtime path always goes through OpenClaw.

The script's structure: get `tenant_access_token` → create app → add fields (one POST per field) → write a test row → verify with `list_records` → batch_delete the test rows (the 2026-06-06 lesson: 10 retries during dev created 10 empty rows because token was unset; the user has to see clean data) → print APP_TOKEN + TABLE_ID, paste into `~/.hermes/.env`.

The 5-column pattern (date / single-select / single-select / single-select / text) is the most common. For Chinese-language events, keep column names and option labels in Chinese — the user reads them in the Bitable UI, not in code.

#### Step 3: Write the plugin
Location: `~/.hermes/plugins/<plugin-name>/__init__.py`
Manifest: `~/.hermes/plugins/<plugin-name>/plugin.yaml`

Both files go under the user-local plugin tree (`~/.hermes/plugins/`, **not** `~/.hermes/hermes-agent/plugins/`). In-repo plugin tree gets clobbered on `hermes update`.

The minimal plugin skeleton (`templates/bitable-plugin-skeleton.py`) covers:
- Lazy config from env vars
- Keyword sets (intake vs bare mention) and dose regex
- `openclaw_invoke(tool_name, args, timeout)` thin HTTP client
- `do_write(text, drug, dose, symptom)` background-thread writer
- `on_pre_llm_call(messages, user_message, ...)` hook entry point
- `register(ctx)` to attach the hook to Hermes's plugin lifecycle

#### Step 4: Wire the env vars
`~/.hermes/.env` is write-protected by the `patch` tool. Use shell `cat >> .env <<EOF ... EOF` to append. Or, since the user has full filesystem access, ask the user to paste the block manually — that's the lowest-friction path and preserves the protection's audit trail.

#### Step 5: Restart the gateway
The plugin is discovered on gateway startup. `systemctl --user restart hermes-gateway` is the standard path, but it can hang in this host's user-systemd environment. The reliable alternative is `kill -TERM <PID>` then let systemd auto-respawn. If the gateway is not running, start it fresh:
```bash
terminal(background=true, command="<hermes gateway run command>")
```
Verify the plugin loaded with `journalctl --user -u hermes-gateway -n 200 | grep <plugin-name>`. A clean load shows the plugin's logger line ("registered pre_llm_call hook"); an `ImportError` shows a stack trace.

For the OpenClaw install, the `/tools/invoke` body schema (`{name, args}` not `{name, arguments}`), the auth header, and the double-encoded response shape, see `hermes-infrastructure` §4.5.

### Verification checklist
- [ ] Bitable app + table + fields pre-created via direct Feishu REST
- [ ] APP_TOKEN + TABLE_ID written to `~/.hermes/.env` (shell append)
- [ ] Plugin file at `~/.hermes/plugins/<name>/__init__.py`
- [ ] Manifest at `~/.hermes/plugins/<name>/plugin.yaml`
- [ ] OPENCLAW_GATEWAY_URL + OPENCLAW_GATEWAY_TOKEN in `~/.hermes/.env`
- [ ] `parse_drug/dose/symptom` return `""` for any field the user did not explicitly state (no defaults)
- [ ] `do_write` refuses to call openclaw if any required field is empty (the honesty contract guard)
- [ ] `on_pre_llm_call` returns `{"context": ...}` for missing-field case, `{}` for complete-payload case, `{}` for bare-mention case
- [ ] End-to-end smoke: simulated hook call + `feishu_bitable_list_records` confirms a new row
- [ ] Three negative cases verified: no intake signal, no symptom, no drug
- [ ] Gateway restarted, plugin loaded line visible in `journalctl --user -u hermes-gateway`
- [ ] Real Feishu DM: complete-payload message → Bitable row within 2 seconds
- [ ] Real Feishu DM: missing-field message → LLM reply asks the right follow-up question
- [ ] Done. Stop here. Do not "test more thoroughly".

---

## 2. Feishu message format constraints (render)

Hermes Agent delivers text to Feishu via `gateway/platforms/feishu.py`. The default path is `msg_type: text` (with a `post` rich-text attempt, falling back to stripped plain text on any error — see `feishu.py:1789-1797`). The plain-text fallback calls `_strip_markdown_to_plain_text(chunk)` which removes bold, headers, table pipes, and most formatting. This is why users see "格式未正常展示" even though the agent wrote pretty markdown.

**Goal:** write responses that survive the text-type transport AND look structured in the Feishu client, without rewriting Hermes or the gateway.

### When

- User complains 'format didn't render right' / 'table is broken' / 'this looks like plain text'
- Writing a long explanation that needs structure
- User explicitly asks 'give me a card' / 'use Feishu-friendly formatting'
- The response would include a markdown table, headers, nested lists, or multi-line code blocks

### What renders correctly in Feishu text messages

| Construct | Renders? | Notes |
|-----------|----------|-------|
| `**bold**` | ✅ | Bold inline |
| `*italic*` | ✅ | Italic inline |
| `` `inline code` `` | ✅ | Monospace inline |
| `[label](https://url)` | ✅ | Real link |
| `- list item` (single dash) | ✅ | Bulleted list |
| `1. numbered list` | ⚠️ | Sometimes renders, sometimes not — use `① ② ③` for safety |
| `# ## ### headers` | ❌ | Stripped to plain text — replace with **bold lead-in + newline** |
| `> blockquote` | ❌ | Stripped — replace with `"…"` or indent with full-width spaces |
| **Markdown tables** `\| \| \|` | ❌ | **Feishu does not render markdown tables at all** — even the `post` rich-text path strips pipes. Replace with bulleted field lists. |
| Nested list (indent) | ❌ | Indentation lost — flatten |
| Multi-line code block ` ``` ` | ❌ | Often triggers fallback / truncation — use inline code with short lines |
| Emojis `🔍 ⚠ ✅ ❌` | ✅ | Render fine, good for structure |

**Two-layer rule of thumb for tables:** (1) Feishu's renderer does not have a markdown table code path, period; (2) Hermes' default transport _strips_ tables even if you sent them in `post` form. So you can never rely on a table reaching the user. If you must show two-dimensional data, either use a card or fall back to a vertical bulleted list.

### Translation table — markdown to Feishu-friendly

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

### Length rules

- **Single message**: keep under 1500 characters. Above ~4000 chars Hermes starts hitting the text-type payload limit and the fallback strip activates.
- **Long answers**: split into 2-3 messages with `---` separators and a one-line headline at the top of each.
- **Avoid emoji-only messages** — read as low-effort in work context.
- **Bold restraint** (2026-06-05 lesson, user pushed back: "你回复的内容有大量的加粗，很多事非必要的"; 2026-06-06 reinforcement: "你输出内容有太多符号了"):
  - **Short text messages** (≤ 300 chars): **≤ 1 `**bold**`** total. A whole-message bold lead is fine; a 3-word bold phrase is not.
  - **Long analysis** (> 300 chars): **≤ 2 `**bold**`** total, **and** the bolded text must be a **full self-contained statement** (complete sentence or paragraph), not a 2-4 character noun/verb/adjective phrase.
  - **Heuristic**: take the 3-4 characters inside `**...**`. If it stands alone as a complete claim ("no offline install" ✓), keep. If it's a word/noun that only makes sense with surrounding text ("the **doc**" ✗ / "**install**" ✗), drop the bold.
  - **Don't bold enumeration labels** ("**Layer 1**: long-term memory") — write `Layer 1: long-term memory` with colon-space, no bold.
  - **Don't bold inside a `code` span** — code blocks don't render bold and the `**` comes through as literal characters.
  - **Don't bold short Chinese phrases** ("**飞书**插件", "**openclaw** 网关") — Feishu's text transport renders these as visual noise. Use plain text with colon or dash separator.

### "Less symbols" rule (2026-06-06 hardening)

The 2026-06-06 second-pass verification surfaced a new class of complaint: **overall output is too symbol-heavy**. Even when every individual `**` or `|` obeys the rules, the *total count* of markdown punctuation in a long reply still reads as AI-generated noise. Hard limits when the user is on Feishu (or any text-transport platform):

| Element | Hard cap per message | When unavoidable, do this |
|---|---|---|
| `**bold**` | ≤ 1 short / ≤ 2 long | Bold the **whole conclusion paragraph** |
| `## ### headers` | **0** | Replace with `① ② ③` numbered intro + plain text body |
| `\| --- \|` tables | **0** | Replace with `- **key**: value` bullets |
| `*` for bullets | **0** | Use `- ` (single dash, single level only) |
| `1. 2. 3.` for ordered | **0** | Use `① ② ③ ④ ⑤ ⑥ ⑦ ⑧ ⑨ ⑩` |
| `> blockquote` | **0** | Use full-width `"…"` quotes or omit |
| `` ``` `` code fences | ≤ 1, ≤ 5 lines | Convert long code to inline `key=value` |
| Emoji-only messages | **0** | Always pair emoji with descriptive word |

**The "self-check" rule**: before sending any reply > 200 chars, count the markdown punctuation. If `**` + `|` + `##` + `>` + `1.` together exceed ~5, the reply is **too symbol-heavy** — rewrite as plain Chinese with `① ② ③` and `- ` bullets before sending.

### Reference files for §2
- `references/message-format-transport-flow.md` — what `feishu.py` actually does on the wire for `text`/`post`/`interactive` message types (line numbers, the silent fallback, what the strip removes, the card JSON path)

### Workflow — when you finish a long answer, audit it
Before sending anything > 500 chars to Feishu, scan once:
- [ ] No `## headers` → replaced with `**Bold**`
- [ ] No markdown tables → replaced with `- **key**: value` lists
- [ ] No `> quotes` → replaced with `"…"` or removed
- [ ] No nested indentation → flattened
- [ ] No multi-line code blocks > 3 lines → collapsed to inline or omitted
- [ ] Total length under 1500 chars (or split with `---` and headline)
- [ ] Lists use `-` not `*` and not `1.`
- [ ] Bold restraint: ≤ 1 bold for short, ≤ 2 for long, full self-contained statements only

If you catch yourself about to write a table, **stop and rewrite as a list right then** — tables will not survive the text transport, and rewriting post-hoc is more work.

---

### 2.4 When the user wants a real card

The user said it: "用卡片输出" / "give me a card". Feishu's **`msg_type: interactive` (card JSON 2.0)** is the only message type that reliably renders multi-column data, dividers, and button rows. The default `text` path cannot show a table, no matter what markdown you write. So if the user asks for a card, take the request literally — either send a real card or use the `post` path's inline `tag: "table"` blocks, **not** a markdown table in a text message.

#### CardKit 2.0 — what actually works (verified 2026-06-05)

User-supplied "complete guide" docs and even official-looking community templates often get the tag names wrong. The schema below is verified by sending each element to a real Feishu app and observing both the **API response (code)** AND the **server-side stored content pulled back via GET** — not from a doc. **The stored content is what the client renders; that's the only ground truth.**

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

The `tag: "markdown"` element at top level (NOT wrapped in `div`, NOT renamed to `lark_md`) is the one Feishu actually renders as a card with real markdown formatting. **Do not trust any "lark_md" advice** — it gets 230099 at top level and gets stripped when wrapped in `div`.

**⚠️ 2026-06-05 second-pass verification — important correction:**

The 7-element matrix above was correct for **content-only** cards. In a follow-up probe the user pasted back the **actual rendered output** of both `tag:"markdown"` and `div+lark_md` variants. Findings:

- `tag: "markdown"` at top level (with or without `"schema":"2.0"`) — user **confirmed** it renders as a real card in the IM client (header bar + bold/list/links work).
- `tag: "div"` wrapping `tag: "lark_md"` — also **confirmed** by user to render as a card, BUT the markdown is **not parsed** inside `lark_md`: bold/italic/list markers come through as literal `**...**` and `- ...` characters. The GET-back trace that showed `tag:"text"` was a server-side flatten; the IM client at that point had already started honoring `div+lark_md` but was rendering the literal escape characters — that's why the user pasted back text like `**+ - 列表项` and `print('hi')` with backslashes preserved.
- `tag: "lark_md"` directly under `body.elements` (no `div` wrapper) — user confirmed this also renders as a real card. This is the **JSON 2.0 standard structure**: `{schema:"2.0", body:{elements:[{tag:"lark_md", content:"..."}]}}`.

**Practical rule, post-2026-06-05 second-pass:**

- **Default for content-heavy cards**: `tag: "markdown"` at the top of the elements list. Survives all clients, parses full markdown, simplest structure.
- **If you need `div` for layout** (column_set, fields, two-line text): use `{"tag": "div", "text": {"tag": "lark_md", "content": "..."}}` — it renders as a card, but **don't expect markdown to be parsed inside `lark_md`**. Use plain text formatting or split into multiple `div` blocks.
- **Never** put `tag: "lark_md"` at the elements-array top level outside of `body` — 230099 rejected. Inside `body.elements` (JSON 2.0 structure) it works.

**Common pitfalls verified by 230099 / 230001 errors:**

- `tag: "markdown"` inside `div` text field — gets div stripped, the `**xx**` becomes literal characters
- `tag: "lark_md"` anywhere — 230099 unsupported
- `tag: "code"` as a top-level element — use fenced ```block``` inside a `markdown` element instead
- `tag: "collapse"` with sub-elements — unsupported; use a `markdown` list with clear separators
- Top-level `schema: "2.0"` — 230099 unknown property `elements`; omit it
- `tag: "form"` / `tag: "input"` / `tag: "selectMenu"` / `tag: "datePicker"` at any nesting level — **all silently dropped** in CardKit 2.0 / `interactive` message type. The API returns `code:0` and the `message_id`, but the Feishu IM client renders these elements as **nothing** (button does not appear, form fields do not appear, only sibling `hr` / `note` elements that happen to use the same schema show up). Verified 2026-06-05 by sending a 4-field form (`input` + `selectMenu` + `datePicker` + submit `button` wrapped in `form`) to a real DM; HTTP 200 + `code:0` + valid `message_id`, but user reported "没有按钮" (no button visible) — the entire form subtree was dropped on the client. These are **schema 1.0-only** elements; they survive in the old `post` rich-text transport but are stripped from `interactive` cards. There is no in-card way to collect structured user input in CardKit 2.0 — buttons with `value: {"action": "..."}` are the only reliable interactive primitive. Treat any "guide" that shows a `form` container in an `interactive` card as stale schema 1.0 docs.

**`header.template` accepts these colors:** `blue`, `red`, `green`, `yellow`, `purple`, `orange`, `grey`. Anything else is silently ignored or rejected depending on the field validator.

**Interactive elements that actually work in `interactive` / CardKit 2.0** (verified 2026-06-05):
- `tag: "markdown"` — text with full markdown (bold/italic/list/code/links)
- `tag: "button"` inside an `actions` container — clickable; value must be `value: {"action": "..."}`; subscribed via `card.action.trigger` event; **the only reliable way to collect a click from the user**
- `tag: "hr"` — visible divider
- `tag: "note"` — small caption text under the main card
- `tag: "collapsible_panel"` — folded/expanded section (mentioned in the user's guide, not independently verified in this session)
- `tag: "standard_icon"` — icon prefix on a markdown element
- `actions` container — wraps one or more buttons in a row

**Interactive elements that DO NOT work in `interactive` (silent drop):** form / input / selectMenu / datePicker / checkbox / picker (person/date) — all schema 1.0-only. The card sends fine (HTTP 200, `code:0`) but the client renders nothing for the dropped subtree. See the pitfall entry above for the full reproduction. If you need structured input from the user, use buttons that branch the conversation or ask in a follow-up text message.

**`action` button values** must use `value: {"action": "..."}` not `action: {...}` — the former is the callback-data contract for `card.action.trigger` events. Subscribe to that event in the app config or clicks return `200340`.

**Streaming / PATCH updates:** set `streaming_mode: true` in config, then PATCH the same `message_id` to update content in place. Throttle to 200ms (Feishu app-level limit is 10/sec). Use `seq` field for ordering to avoid out-of-order PATCHes during long-running tasks.

**Direct test recipe** (use this to verify any card before sending in production — ALWAYS pull back via GET, do not trust 200 OK alone):

```python
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

A drop-in Python script is at `templates/send-feishu-card.py`. Card JSON structure uses `tag: "markdown"` at top level (the verified-correct shape), with optional header color (7 templates) and action buttons. Use this when you need a real card right now.

#### Card features Feishu supports that text messages do NOT:
- `tag: "table"` — two-dimensional layout that survives in `post` rich-text messages (the closest you can get to a "real" table in a message the user is going to forward)
- `tag: "hr"` — visible horizontal rule
- Multi-line code blocks with monospace background (use fenced ``` inside a `markdown` element)
- Clickable buttons, image carousels, `select` menus
- Headers with colored backgrounds

#### Five paths to a real card

1. **Option A — explicit card payload via the `feishu-enhanced` skill**: write the card JSON to a file and call `feishu-api.sh send` with `msg_type=interactive` or `msg_type=post`. Requires `FEISHU_APP_ID` + `FEISHU_APP_SECRET` in `~/.hermes/.env` and the app to have `im:message` scope. **This is the right path** when the user explicitly asks for a card.

2. **Option B — patch `gateway/platforms/feishu.py:_build_interactive_card_payload`**: the function builds card JSON; the verified-correct structure is `tag: "markdown"` at top level (not `div` wrapping `lark_md`). Earlier patches using `div`+`lark_md` were 200 OK but rendered as rich text in the client — always pull back via GET to confirm. Reverts on `hermes update`.

   **Pitfall (2026-06-05, in-session)**: the agent's session memory contained a stale claim "tag: markdown → tag: lark_md is the fix for real Feishu cards". That memory is **inverted**. In CardKit 2.0 the only verified-working approach is `tag: "markdown"` at top level. `tag: "lark_md"` gets 230099 at top level, 230001 in post shape, or gets stripped if wrapped in `div`. The user confirmed a `div+lark_md` patch was still showing as escape characters (`\+`, `\*\*`) in the IM client — definitive proof the patch was wrong. **Before patching `_build_interactive_card_payload`**, search this skill (or its previous version) for the verified matrix; do not trust session-memory notes that pre-date the 2026-06-05 verification probe.

   **Workflow pitfall (2026-06-05)**: when 4+ direct API calls all returned code=0 and the user is still seeing wrong output, **stop testing and ask the user what they see in the client**. The server stores `elements: [[{tag:"text"}...]]` (post-format flattening) regardless of what element shape you sent — the API response is not ground truth. Only the user's screen is ground truth.

3. **Option C (recommended for routine answers)**: keep using text messages, but follow §2's translation table. 80% of the card's visual quality with 0% of the engineering cost. Save cards for high-stakes deliverables (release notes, incident reports) where the work justifies it.

4. **Option D — `msg_type: "post"` with `zh_cn.title`** (the *historical* real-card path, confirmed in this session 2026-06-05). This is distinct from `interactive` and is what produced the original "📊 腾讯行情 / 🔄 数据备份" cards the user has seen as real blue-header cards in groups. The verified shape:
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
   `zh_cn.title` is what produces the colored header bar. Inside `content`, `tag: "text"`, `tag: "a"`, `tag: "hr"`, and `tag: "media"` (images) are the supported row elements. `lark_md` does NOT belong in `post` row content either (230001 wrong tag). This path is the right choice when you want a real card **without** patching `_build_interactive_card_payload` or installing a plugin — just send the `post` payload directly.

5. **Option E — `hermes_feishu_plugin` v0.6.0** (path the user previously confirmed for "real cards" in groups as of the 6-04 session). This is a different code path than `_build_interactive_card_payload` — the plugin wraps the response in a card template using `div`+`lark_md` correctly. If the gateway already has this plugin loaded and the user is getting real cards in groups but plain text in DMs, the issue is `feishu.py:1840-1866` silent fallback to `_strip_markdown_to_plain_text` on certain DM-side `interactive` failures — debug by adding `logger.warning` around the fallback path, not by patching card element shape.

**Decision rule:** if the answer is more than 5 rows of multi-column data **or** the user said "卡片" / "card" / "表格不乱" explicitly, build a `post` rich-text message with `tag: "table"`. Otherwise, use the translation table in §2 in a regular text message.

### Verification pitfall (2026-06-05 lesson)
A card that returns `code: 0` and has `msg_type: "interactive"` in the response can **still** render as plain rich text in the Feishu client if the `tag: "div"` wrapping or `tag: "lark_md"` inner element got stripped on the server side. **Always** pull the stored message back via `GET /im/v1/messages/{message_id}` and inspect the `body.content` JSON — if it shows `elements: [[{tag: "text"}...]]` (post-format flattening), the client is going to render plain text, not a card. This is a server-side transformation you cannot see from the send response alone.

### Reference files for §2.4
- `templates/send-feishu-card.py` — drop-in Python script that posts an interactive card via `im/v1/messages`

---

## 3. Doc-against-reality-audit dispatch

When the user hands you a Feishu configuration / integration guide ("这是飞书接入教程", "按这个文档配置 feishu 卡片", "用这个 schema 2.0 的 JSON"), the right move is **not** to execute it. Run the doc-against-reality-audit pattern first:

1. **Extract claims** into a structured list (tag names, properties, schema versions, API endpoints)
2. **Probe each claim** against the live system (`curl` to a real Feishu API, send a test card, GET it back, inspect `body.content`)
3. **Build a delta table** — what's correct, what's hallucinated, what's version-skewed
4. **Execute ONLY the truthful subset** — never a claim marked wrong

The `doc-against-reality-audit/references/feishu-card-schema-mismatches.md` reference has the specific tag/property mismatches already verified (`markdown` vs `lark_md`, `schema: "2.0"` at root, `tag: "form"`, `tag: "collapse"`, `tag: "div"` vs `hr`, etc.) so you don't have to re-probe. Then use §2.4's 7-element matrix as the ground-truth reference when you actually build a card.

The most common Feishu-guide hallucination patterns: the doc invents tag names that look plausible (`lark_md` at top level, `form` containers in `interactive` cards, `collapse` with sub-elements, `schema: "2.0"` at the root); the doc references an old `post`-only transport that was deprecated; the doc shows API response `code: 0` as proof the card rendered, but the client-side `body.content` is a flattened `[[{tag: text}...]]` which renders as plain rich text.

---

## Cross-skill rules

- When rendering into Feishu DMs, always apply §2's bold-restraint + "less symbols" rules.
- When writing a Hermes plugin for §1, always apply the honesty contract — never invent a column value.
- When installing OpenClaw for §1, follow `hermes-infrastructure` §4 (gateway install, `openclaw.json`, `/tools/invoke` body schema).
- When installing MCP servers for §1 (if your plugin needs them), follow `hermes-infrastructure` §3.1.
- After every completed task, apply `agent-execution-anti-stall-rules` — report success, stop, do not enumerate next steps.

## See also (related skills)

- `hermes-infrastructure` — umbrella for Hermes + OpenClaw + OpenViking operations. §4 is the gateway contract §1's plugin calls into; §3.1 is the MCP install pattern.
- `agent-execution-anti-stall-rules` — the "stop after success" rule; applies to every Feishu integration task.
- `doc-against-reality-audit` — when the user hands you a Feishu guide / CardKit template / 接入教程, audit before execute.
- `feishu-enhanced` — the broader Feishu API surface (Bitables, Docs, Drive, IM, full OpenAPI) for non-Hermes-plugin work.
