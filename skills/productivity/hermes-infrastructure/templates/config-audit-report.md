# Hermes config audit report template

Follow this structure when rendering an audit. The 6 sections are in
order; skip the optional 7th unless the user asks for diffs.

## Section 1: file inventory

```
# 主人，配置盘点
N 个核心文件，N 个用户 plugin

① ~/.hermes/.env  (凭证 + 启动 env, NNN chars / NN 行)
② ~/.hermes/config.yaml  (hermes 性能 / 行为核心, NNN chars / NN 行)
③ ~/.hermes/SOUL.md  (小赤身份 + 对话原则, NNN chars / NN 行)
④ ~/.hermes/memories/MEMORY.md  (主人偏好, NNN chars / NN 行)
⑤ ~/.hermes/memories/USER.md  (主人档案, NNN chars / NN 行)
⑥ ~/.openclaw/openclaw.json  (openclaw gateway, NNN chars / NN 行)
⑦ ~/.hermes/plugins/  (N 个 plugin: <list>)
```

## Section 2: .env dump (masked)

Group by block. List the 4-5 actively-populated blocks; mention the
count of commented-out templates.

```
LLM Provider: <active>
  - MINIMAX_CODING_API_KEY=***REDACTED(125)***  ✓ active
  - MINIMAX_CODING_BASE_URL=https://api.minimaxi.com/anthropic
Feishu:
  - FEISHU_APP_ID=cli_xxx
  - FEISHU_APP_SECRET=***REDACTED(32)***  ✓ active
... (active blocks)
... 20+ commented-out provider / integration templates, not active
```

## Section 3: config.yaml — top-level summary

```
# Performance knobs (5 most-edited)
agent.max_turns = 40
agent.gateway_timeout = 1800s
memory.memory_char_limit = 2200  ⚠️ 接近满
compression.threshold = 0.5
tool_output.max_bytes = 50000

# Tools / plugins
toolsets = [hermes-cli]
mcp_servers.MiniMax = enabled
plugins.enabled = [lightclawbot]

# Behavior UX
display.personality = concise
display.show_cost = false
approvals.mode = off
human_delay.mode = off
```

## Section 4: SOUL.md full content

Dump verbatim. If the user wrote English, offer to translate to
Chinese — the user often wants both the verbatim (for "is this
exactly what I wrote?") and a translated version (for "what does it
say in Chinese?").

## Section 5: memories full content

Same — dump verbatim. MEMORY.md and USER.md are short enough
(typically 1-3k chars) that no summary is needed.

## Section 6: plugins summary

```
~/.hermes/plugins/
├── hermes_allergy_logger  v0.2.0
│   用途: 飞书过敏药自动记表
│   env: OPENCLAW_GATEWAY_URL, OPENCLAW_GATEWAY_TOKEN,
│        ALLERGY_BITABLE_APP_TOKEN, ALLERGY_BITABLE_TABLE_ID
└── ... (others)
```

## Section 7: openclaw.json (only if relevant)

If the user is using OpenClaw, dump the full file with `json.dumps(indent=2)`.
The `gateway.auth.token` value should be **masked** if the bind is
`0.0.0.0` (exposed) but can be shown if it's `loopback` (local-only).

## Section 8: tuning recommendations (only if asked)

If the user asked "what should I tune" or "what's the bottleneck",
include 5-8 specific recommendations with their current vs
recommended values. Otherwise skip this section.

## Optional section 9: diffs (only if asked)

If the user asked "what changed since last audit" or "compare to the
template", include a unified diff against the canonical template or
the previous audit. Skip by default — most audits are point-in-time
snapshots, not comparisons.

## Tone

The audit is a **reference document the user reads**, not a
conversation. Use ① ② ③ numbering for the file groups. Use `- key: value`
bullets within each group. No headings (`## ###`) — they degrade
badly in Feishu. No markdown tables — they render as pipes in
Feishu. No `**bold**` on individual words — only bold full
paragraphs if needed.

End the report with one line:

```
主人要改哪条直接说，告诉我具体动作。
```

## Length

The audit should be **1,500-3,000 chars total** for a normal
review. The SOUL.md and memories dumps are the bulk. If the user
asks for a deeper audit (e.g. "show me every section of config.yaml"
or "diff against the template"), expand the relevant section, don't
dump the whole 14k-char `config.yaml` at once.
