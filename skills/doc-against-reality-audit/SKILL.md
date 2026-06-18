---
name: doc-against-reality-audit
description: When the user hands you an AI-generated config/setup guide (Xmind, Markdown, PDF, web page) that claims to walk through configuring the current system, DO NOT execute it. Audit the doc's claims against the actual live system first, output a "real vs. claimed" delta table, and only execute the truthful subset. Use when the user pastes a 部署指南 / 接入教程 / 配置文件模板 / 自动化手册 / "按这个文档配置" prompt and the doc mentions specific filenames, CLI commands, or yaml keys.
---

# Doc-against-Reality Audit

AI-generated setup guides (Xmind maps, Markdown walkthroughs, vendor PDFs) almost always contain claims that don't match the live system: hallucinated CLI commands, invented config keys, deprecated flags, version-skewed defaults. **Executing them blind burns turns and can break working state.**

The right pattern is to treat the doc as a hypothesis and **audit it against the actual system** before touching anything.

## When to use

- User pastes a 部署指南 / 接入教程 / 配置文件模板 / 自动化手册
- Doc says things like "create `~/.foo/personas/primary.yaml`" or "set `auto_improve: true`"
- User says "按这个文档配置" / "按这个接入" / "follow this guide" / "apply this config"
- Doc has version numbers, file paths, or specific yaml/json keys

## The 4-step audit

### 1. Extract claims into a structured list

Scan the doc for **concrete, testable** claims:
- Filenames and directory paths (does the file/dir exist?)
- CLI commands (does the command exist? does `--flag` work?)
- yaml/json keys (does the key exist? what's its current value?)
- Version numbers (what's the actual version of the system?)
- API endpoints (do they resolve? do they 200?)

Group by category: paths, commands, config keys, endpoints, claims about behavior.

### 2. Probe each claim against the live system

For each claim, run the minimum-viable check:

```bash
# Paths
ls -la <path> 2>&1

# Commands
which <cmd> && <cmd> --help 2>&1 | head -10

# Config keys (the BIG one — these are the most common hallucination)
grep -E "^\s*<key>:" ~/.hermes/config.yaml          # for hermes
# OR: just read the relevant config file fully and grep for the claim

# Endpoints
curl -sI -o /dev/null -w "%{http_code} %{time_total}s" --connect-timeout 5 <url>

# Behavior
# Read the source if needed: grep -rn "<claim>" ~/.hermes/hermes-agent/
```

**Don't trust the doc's defaults.** Read the actual current value — not the doc's stated default. They differ often (e.g., doc says `max_turns: 5`, actual is `60`; doc says `persona: soul`, actual field is `display.personality`).

### 3. Build a delta table

Output a two-column table for the user:

| 文档项 | 实际系统状态 | 结论 |
|---|---|---|
| `~/.hermes/personas/soul.md` | ❌ 目录不存在；实际是 `~/.hermes/SOUL.md` | 文档错：路径错 |
| `auto_improve: true` | ❌ `agent.disabled_toolsets: []` 才是真字段 | 文档错：字段错 |
| `hermes profile create product-manager` | ❌ 命令不存在 | 文档错：CLI 错 |
| `agent.max_turns: 5` | ✅ 真实存在（当前值 60） | 文档对：值建议改 |
| `display.language: zh` | ✅ 真实存在（当前值 en） | 文档对：值建议改 |

The user can then see exactly which claims are trustworthy and which are wrong — without me silently executing the wrong ones.

### 4. Execute ONLY the truthful subset

After the user confirms the delta (or says "按真的做" / "execute the real ones"), do only those. **Never execute a claim that the audit marked wrong** even if the user originally said "do all of it" — the user is trusting you to filter the hallucinated parts, and a wrong command in a cron unit or a non-existent yaml key can take minutes to recover from.

## Common hallucination patterns to watch for

These appear in AI-generated guides with suspicious frequency:

1. **Invented directory layouts** — `personas/`, `teams/`, `agent_profiles/`, `knowledge/` — the doc invents a nice tidy structure that doesn't exist
2. **Invented yaml keys** — `auto_improve`, `lazy_load`, `embedding_model`, `max_loaded_skills`, `long_term`, `episodic` — sounds plausible, not in the schema
3. **Invented CLI subcommands** — `hermes config validate`, `hermes doctor`, `hermes memory import`, `hermes profile create` (check `hermes --help` first; many of these don't exist)
4. **Cross-version defaults** — doc references an old `config.yaml` default from 2 versions ago; current is different
5. **Custom-provider slots** — `provider: "anthropic"` when the actual provider id is `custom:minimax_coding` or similar
6. **"Security" fields** that don't exist — `api_key: ...`, `allowed_ips: [...]`, `require_tls: true` — fabricated
7. **Multi-persona files** — `personas/product-manager.md` etc. — the actual system has one `SOUL.md` and a fixed personality enum

**Rule of thumb:** if a field name is a noun phrase with no verb ("memory/embedding_model") it might be invented. Real config fields tend to be `<section>.<verb_or_status>` (`memory.memory_enabled`, `security.tirith_enabled`, `agent.reasoning_effort`).

## Output format for the user

Don't dump the audit as a long monologue. Use this compact form:

```
## 文档 vs 实际
| # | 文档项 | 实际 | 结论 |
|---|---|---|---|
| 1 | 路径/命令/字段 X | 存在/不存在/值=... | ✅ 文档对 / ❌ 文档错 / ⚠️ 字段在但语义不同 |

## 我准备做的（N 项，主人授权就执行）
1. ...
2. ...

## 我拒绝做的（M 项，越界/不存在/有风险）
1. ...
2. ...
```

The user can then say "全做" or pick by number.

## Pitfalls

- **Don't just "search the codebase" and conclude.** A doc can have a plausible claim that does technically exist in the source but is **never wired up** (deprecated, behind a feature flag, defined but unused). Always probe the runtime, not the static source.
- **The user may be testing you.** "按这个文档配置" is sometimes a check on whether you'll detect the hallucinations or just blindly execute. The audit is the value-add.
- **Even after auditing, ask before executing destructive steps.** The audit answers "is this real?" — it does not answer "do you want this?". The user might say "I know X is wrong, do it anyway for compat" or "skip that one". Always confirm before touching the system.
- **The Xmind and Markdown formats hide structure.** A 思维导图 in a single `.xmind` file looks authoritative but is just text rendered in a specific shape. Don't let visual layout trick you into assuming the content has been validated.
- **Some "wrong" items are partial truths.** A doc might have the right field name but the wrong section (e.g., `auto_improve` under `skills:` vs. the real `disabled_toolsets` under `agent:`). Note these as "⚠️ field exists elsewhere" rather than just "❌ wrong".
- **Don't let key/config decisions block the install phase.** When a doc says "install X, configure with key Y, start service Z", don't pause the install to ask about key Y. Audit, then run the install steps that don't need runtime keys. Ask one consolidated question about runtime config **after** install succeeds. User signal: "我都说了要安装了，没有 key 也不影响安装，不应该卡住任务". Self-check: is this question needed for `pip install` / `npm i` / `cargo build` to succeed? If no, defer it.

## Reference

- `references/hallucination-catalog.md` — running list of specific field names, paths, and CLI commands that have appeared in user-supplied guides and been verified wrong, with the correct alternative. Includes the npm-global install layout, openviking real config (viking:// paradigm, 5 viking:// subdirs, required env vars, OpenAI-compat VLM trick), and PyPI-version-vs-doc-claim mismatches
- `references/feishu-card-schema-mismatches.md` — CardKit 2.0 specific: the tag names and properties that community "complete guide" docs get wrong (`markdown` vs `lark_md`, `schema: "2.0"` at root, top-level `tag: "code"`, `tag: "collapse"`), with the exact API error codes and the audit recipe to fix them
