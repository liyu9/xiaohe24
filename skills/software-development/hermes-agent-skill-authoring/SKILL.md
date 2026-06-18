---
name: hermes-agent-skill-authoring
description: "Author in-repo SKILL.md: frontmatter, validator, structure."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [skills, authoring, hermes-agent, conventions, skill-md]
    related_skills: [writing-plans, requesting-code-review]
---

# Authoring Hermes-Agent Skills (in-repo)

## Overview

There are two places a SKILL.md can live:

1. **User-local:** `~/.hermes/skills/<maybe-category>/<name>/SKILL.md` — personal, not shared. Created via `skill_manage(action='create')`.
2. **In-repo (this skill is about this case):** `/home/bb/hermes-agent/skills/<category>/<name>/SKILL.md` — committed, shipped with the package. Use `write_file` + `git add`. `skill_manage(action='create')` does NOT target this tree.

## When to Use

- User asks you to add a skill "in this branch / repo / commit"
- You're committing a reusable workflow that should ship with hermes-agent
- You're editing an existing skill under `/home/bb/hermes-agent/skills/` (use `patch` for small edits, `write_file` for rewrites; `skill_manage` still works for patch on in-repo skills, but not for `create`)

## Required Frontmatter

Source of truth: `tools/skill_manager_tool.py::_validate_frontmatter`. Hard requirements:

- Starts with `---` as the first bytes (no leading blank line).
- Closes with `\n---\n` before the body.
- Parses as a YAML mapping.
- `name` field present.
- `description` field present, ≤ **1024 chars** (`MAX_DESCRIPTION_LENGTH`).
- Non-empty body after the closing `---`.

Peer-matched shape used by every skill under `skills/software-development/`:

```yaml
---
name: my-skill-name               # lowercase, hyphens, ≤64 chars (MAX_NAME_LENGTH)
description: Use when <trigger>. <one-line behavior>.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [short, descriptive, tags]
    related_skills: [other-skill, another-skill]
---
```

`version` / `author` / `license` / `metadata` are NOT enforced by the validator, but every peer has them — omit and your skill sticks out.

## Size Limits

- Description: ≤ 1024 chars (enforced).
- Full SKILL.md: ≤ 100,000 chars (enforced as `MAX_SKILL_CONTENT_CHARS`, ~36k tokens).
- Peer skills in `software-development/` sit at **8-14k chars**. Aim for that range. If you're pushing past 20k, split into `references/*.md` and reference them from SKILL.md.

## Peer-Matched Structure

Every in-repo skill follows roughly:

```
# <Title>

## Overview
One or two paragraphs: what and why.

## When to Use
- Bulleted triggers
- "Don't use for:" counter-triggers

## <Topic sections specific to the skill>
- Quick-reference tables are common
- Code blocks with exact commands
- Hermes-specific recipes (tests via scripts/run_tests.sh, ui-tui paths, etc.)

## Common Pitfalls
Numbered list of mistakes and their fixes.

## Verification Checklist
- [ ] Checkbox list of post-action verifications

## One-Shot Recipes (optional)
Named scenarios → concrete command sequences.
```

Not every section is mandatory, but `Overview` + `When to Use` + actionable body + pitfalls are the minimum for the skill to feel like a peer.

## Directory Placement

```
skills/<category>/<skill-name>/SKILL.md
```

Categories currently in repo (confirm with `ls skills/`): `autonomous-ai-agents`, `creative`, `data-science`, `devops`, `dogfood`, `email`, `gaming`, `github`, `leisure`, `mcp`, `media`, `mlops/*`, `note-taking`, `productivity`, `red-teaming`, `research`, `smart-home`, `social-media`, `software-development`.

Pick the closest existing category. Don't invent new top-level categories casually.

## Workflow

1. **Survey peers** in the target category:
   ```
   ls skills/<category>/
   ```
   Read 2-3 peer SKILL.md files to match tone and structure.
2. **Check validator constraints** in `tools/skill_manager_tool.py` if unsure.
3. **Draft** with `write_file` to `skills/<category>/<name>/SKILL.md`.
4. **Validate locally**:
   ```python
   import yaml, re, pathlib
   content = pathlib.Path("skills/<category>/<name>/SKILL.md").read_text()
   assert content.startswith("---")
   m = re.search(r'\n---\s*\n', content[3:])
   fm = yaml.safe_load(content[3:m.start()+3])
   assert "name" in fm and "description" in fm
   assert len(fm["description"]) <= 1024
   assert len(content) <= 100_000
   ```
5. **Git add + commit** on the active branch.
6. **Note:** the CURRENT session's skill loader is cached — `skill_view` / `skills_list` will not see the new skill until a new session. This is expected, not a bug.

## Cross-Referencing Other Skills

`metadata.hermes.related_skills` unions both trees (`skills/` in-repo and `~/.hermes/skills/`) at load time. You CAN reference a user-local skill from an in-repo skill, but it won't resolve for other users who clone the repo fresh. Prefer referencing only in-repo skills from in-repo skills. If a frequently-referenced skill lives only in `~/.hermes/skills/`, consider promoting it to the repo.

## Editing Existing In-Repo Skills

- **Small fix (typo, added pitfall, tightened trigger):** `skill_manage(action='patch', name=..., old_string=..., new_string=...)` works fine on in-repo skills.
- **Major rewrite:** `write_file` the whole SKILL.md. `skill_manage(action='edit')` also works but requires supplying the full new content.
- **Adding supporting files:** `write_file` to `skills/<category>/<name>/references/<file>.md`, `templates/<file>`, or `scripts/<file>`. `skill_manage(action='write_file')` also works and enforces the references/templates/scripts/assets subdir allowlist.
- **Always commit** the edit — in-repo skills are source, not runtime state.

## User-Embedded Preferences (HARD-CODED from owner session 2026-06-04)

These are **the owner's standing preferences** for how skills should be authored and how the agent (小赤) should execute them. They were expressed directly by the user and override generic best-practice defaults above.

### Persona + role-name
- The agent persona is **`小赤`** (NOT the default `Hermes` or any of the built-in `personalities:`). When authoring example prompts, the example agent should refer to itself as "小赤".
- Address the user as **`主人`** (master). Never use "你" + question-framed closers like "需要我帮你查一下吗？".

### Communication style
- **No question-framed closers.** "需要我帮你X吗？" / "还有什么可以帮您？" / "Want me to..." are forbidden endings. End with a result statement ("完成" / "已记下" / "待主人审阅") or a single concrete next step.
- **Proactive execution, not interrogative planning.** When the owner gives a direction, pick a default → execute → verify → report. Do not chain clarifying questions. The single allowed form of `clarify` is **single-question multiple-choice with ≤ 4 options** (open-ended long questions are forbidden).
- **No "I'm a small model, I might be wrong" hedging.** State findings; flag uncertainty only at the bit that's actually uncertain.
- **No summary-of-self openings.** Never start with "我理解..." / "好的，我来..." / "以下是...". Get to the action or the answer in the first sentence.

### Verification policy (CRITICAL — this is the owner's strongest signal)
The owner explicitly said: **"你验证可行性"** / **"改完配置必须自己验证跑通再交付，不让用户当测试员"**. Encode as a hard rule:
- **Any change to config, scripts, skill installs, or scheduled jobs must be self-verified end-to-end before reporting "done".**
- Verification = the same call path the owner will use, exercised in-session, with the output inspected.
- A bare "X was installed" or "Y was configured" is NOT a valid completion report. The report must include the verification result (command + observed output).
- **Bad:** "已安装 gh 2.81.0". **Good:** "已装 gh 2.81.0；`gh repo view liyu9/xiaohe24` 返 `name:'xiaohe24'` 验证通过".

### Root-cause-first debugging
- The owner wants **根因修复**, not 创可贴. When a network/auth/permission failure surfaces:
  1. Diagnose the actual layer (DNS / TCP / TLS / HTTP / application / auth / firewall / rate-limit)
  2. State the root cause
  3. Propose the fix at the root layer, not a workaround
- **Workarounds (HTTP mirror, retry tuning) must be flagged as workarounds** with a one-line note on the proper fix.
- Surface **environmental facts the user can't see** (e.g., "this host's egress blocks `github.com:443` write ops but `:22` SSH is open") — these are the highest-leverage findings.

### Token / secret hygiene (CRITICAL — repeated in many skills)
- When the user pastes a token / API key / private key, the agent must:
  1. **Not store it in memory** (it goes in `~/.hermes/.env` or the official secrets file only).
  2. **Not paste it back into chat** after the initial use (the chat history is the leak vector).
  3. **Recommend immediate revocation** at the source after use: GitHub https://github.com/settings/tokens, Feishu https://open.feishu.cn/app, etc. — with a one-liner reason.
  4. **chmod 600** any file the token lands in. The default `~/.hermes/.env` starts as 666; fix immediately.
  5. Recommend **fine-grained over classic** when offering a token-creation walkthrough (classic has over-broad scopes like `admin:public_key` that can edit the user's own SSH keys).
- The user is a **产品经理** with private Obsidian notes and personal prompt-engineering repos on GitHub — so the privacy blast radius of any token leak is wider than a typical "demo" project.

### Skill-bundled credential discovery
- When a skill's `SKILL.md` says "configure X in `TOOLS.md`" but its actual code reads `process.env.X` / `os.environ['X']`, **trust the code, not the doc**. Skill docs lag code. The script's import/env access is the source of truth.

### Six-installs-in-a-row
- The owner fires 3–6 install requests per session. Do NOT spend a turn re-reading the skill each time. The workflow is mechanical: `which skillhub && skillhub --version` once (cache the result for the session), then for each install: `skillhub search <slug>` (parallel batch) → `skillhub install <slug>` (parallel batch). Re-explain what SkillHub is **once** per session, max. After the first install, just say "✓ <slug> v<ver>" per subsequent request.

### Cloud-VM observation pattern
- The host is a **腾讯云 CVM 轻量 `VM-0-8-ubuntu`**, 4 核 4G, with `YJ-FIREWALL-INPUT` (云镜) iptables. Egress to `github.com:443` HTTPS write is QoS-throttled; `:22` SSH is fully open; `api.github.com:443` is fully open. **Default assumption for any new network operation: SSH-first, HTTPS-read-OK, HTTPS-write-throttled.** Verify before assuming the worst.
- `terminal()` shells are ephemeral. `cd` does not persist. Use `workdir=` on every multi-step git/file sequence, or chain with `&&` in a single call, or call `execute_code` with `terminal(command, workdir=...)`. The single most common silent-failure mode is "git did the wrong thing in /home/ubuntu instead of in the repo".

### Don't claim you did something you didn't
- The owner will spot-check (`验证可行性` is literally a command they issued). The cost of a fabricated "done" report is much higher than the cost of "I tried X, it failed, here's the transcript".

## How to apply these preferences when authoring or patching a skill

When you write or patch a skill, you are not just documenting a workflow — you are encoding how `小赤` should execute that workflow for `主人`. So:

1. **Embed owner-specific phrasing** (the persona + the verification rule) directly in the skill's "When to Use" or "Common Pitfalls" sections. Example pitfall to add: *"`已安装 X` 不是一个完成报告 — 报告必须附上 `X --do-thing` 验证输出"*.
2. **Embed the host's network assumptions** (SSH-first, HTTPS-read-OK) in any skill that triggers network operations. Don't repeat the diagnostic every time, but reference it.
3. **If a skill touches credentials**, add a "Secret hygiene" subsection. Owner has been burned by leaked tokens; the reminder is cheap.
4. **If a skill is "fire-and-forget"** (e.g., backup cron, push to remote), the verification step MUST include a real round-trip: read the destination, not just write the source.
5. **When you discover the skill's own docs are wrong** (e.g., `SKILL.md` says `TOOLS.md` but the script reads `ENV`), patch the skill with a `Pitfall: Skill doc <-> code drift` note. The next agent will hit the same trap.

The next sections cover the **generic best-practice defaults** that apply to every skill regardless of owner. Use both sets together.

## Common Pitfalls

1. **Using `skill_manage(action='create')` for an in-repo skill.** It writes to `~/.hermes/skills/`, not the repo tree. Use `write_file` for in-repo creation.

2. **Leading whitespace before `---`.** The validator checks `content.startswith("---")`; any leading blank line or BOM fails validation.

3. **Description too generic.** Peer descriptions start with "Use when ..." and describe the *trigger class*, not the one task. "Use when debugging X" > "Debug X".

4. **Forgetting the author/license/metadata block.** Not validator-enforced, but every peer has it; omitting makes the skill look half-finished.

5. **Writing a skill that duplicates a peer.** Before creating, `ls skills/<category>/` and open 2-3 peers. Prefer extending an existing skill to creating a narrow sibling.

6. **Expecting the current session to see the new skill.** It won't. The skill loader is initialized at session start. Verify in a fresh session or via `skill_view` using the exact path.

7. **Linking to skills that don't exist in-repo.** `related_skills: [some-user-local-skill]` works for you but breaks for other clones. Prefer only in-repo links.

## Verification Checklist

- [ ] File is at `skills/<category>/<name>/SKILL.md` (not in `~/.hermes/skills/`)
- [ ] Frontmatter starts at byte 0 with `---`, closes with `\n---\n`
- [ ] `name`, `description`, `version`, `author`, `license`, `metadata.hermes.{tags, related_skills}` all present
- [ ] Name ≤ 64 chars, lowercase + hyphens
- [ ] Description ≤ 1024 chars and starts with "Use when ..."
- [ ] Total file ≤ 100,000 chars (aim for 8-15k)
- [ ] Structure: `# Title` → `## Overview` → `## When to Use` → body → `## Common Pitfalls` → `## Verification Checklist`
- [ ] `related_skills` references resolve in-repo (or are explicitly OK to be user-local)
- [ ] `git add skills/<category>/<name>/ && git commit` completed on the intended branch
