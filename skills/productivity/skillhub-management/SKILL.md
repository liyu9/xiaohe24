---
name: skillhub-management
description: Manage the SkillHub CLI and skill lifecycle — check installation, search the registry, install/update/remove skills, and recover from common pitfalls (slug collisions, registry mismatches, missing CLI). Use when the user asks to install, update, or search for a skill, or when a "请先检查是否已安装" / "install skill X" / "find a skill for X" prompt arrives.
---

# SkillHub Management

SkillHub is a skill registry + CLI. The CLI binary is `skillhub`; the official install path is the one-liner at https://skillhub.cn/install/skillhub.md. Skills install to `/home/ubuntu/skills/<slug>` (or whatever the CLI reports).

## Standard workflow

When the user says "请先检查是否已安装 SkillHub 商店，若未安装…安装…然后安装 X 技能" (or any variant), follow this:

1. **Check CLI presence**:
   ```bash
   which skillhub && skillhub --version
   ```
   If missing, install from the official doc — *CLI only*, never grab the full workspace bundle unless asked:
   ```bash
   curl -fsSL https://skillhub.cn/install/install.sh | bash -s -- --no-skills
   ```
   The `--no-skills` flag skips the workspace-level skill installation; only the CLI is added (typically `/home/ubuntu/.local/bin/skillhub`).

2. **Search before installing** — many slugs collide. Common patterns you'll see:
   - `-pro`, `-lite`, `-1-0-0`, `-bak`, `-litiao`, `-conflict` suffixes
   - Same slug claimed by multiple authors
   - **Always grep the description for the user's exact requirement** (e.g. "持仓盈亏" → A股分析; "策略研报" → `-pro` / `-lite`).
   ```bash
   skillhub search <keyword>
   ```

3. **Install the best match**:
   ```bash
   skillhub install <exact-slug>
   ```
   If the slug is not in the local index, the CLI falls back to the remote registry — note the `info: "X" not in index, using remote registry exact match` warning, but it still works.

4. **Verify install** (optional but cheap):
   ```bash
   ls /home/ubuntu/skills/<slug>
   ```
   The CLI's `✓ Installed: <slug> -> <path>` line is the ground truth.

## Pitfalls

- **Slug collision noise.** Searches for popular skills return 5–10 variants. Do NOT install the first one blindly — read the description and pick the one that matches the user's stated need. The unversioned name (`a-stock-analysis`, `word-docx`) is usually the canonical / recommended one; `-pro` / `-lite` are feature-bundled forks.
- **`--no-skills` is important.** The default install script also installs a workspace-level skill bundle. If the user only wants the CLI (and to pick their own skills), always pass `--no-skills`.
- **`which` can lie.** `which skillhub` returns success if the binary is on PATH, but the binary may be from a previous version. Use `skillhub --version` as the source of truth.
- **OpenClaw plugin step is skipped on this host.** The installer prints `Warn: openclaw not found on PATH; skipped plugin disable.` — that's expected, not an error.
- **Hub-installed skills are protected.** Skills installed via `skillhub install` are tagged hub-installed and Hermes refuses to edit them in-place. To modify one, uninstall + reinstall a local fork, or use a different skill that wraps it.
- **Concurrent installs are safe.** Multiple `skillhub install` calls in parallel finish cleanly — each is independent and idempotent. When the user packs two or more install requests into one message ("先装 X，再装 Y"), do the CLI check + each `skillhub search` in one parallel block, then the installs in a second parallel block. Don't serialize.
- **`terminal()` shells are ephemeral — `cd` does not persist across calls.** Each `terminal(...)` invocation starts a fresh bash in the default cwd. If you need to run a multi-step git/file sequence, either (a) pass `workdir="/abs/path"` to every call, or (b) chain commands with `&&` inside a single call, or (c) use `execute_code` and call `terminal(command, workdir=...)` from inside. Forgetting this is the #1 reason a perfectly good `git add && git commit && git push` chain silently runs `git add` in the wrong directory.
- **The user's "执行" / "install X then Y" pattern.** When the user says "请先检查是否已安装 SkillHub 商店…然后安装 X" (or "执行" on a prior list of tasks), treat it as a deterministic script: check → search → install → report. Don't re-explain unless something failed. A bare "ok" with the install log is usually enough.
- **The "duplicate-pasted instruction" pattern.** When the user pastes a tutorial block in the middle of their own request (Chinese tutorials often include a copy-paste-ready "执行命令" section, and the user sometimes pastes the whole thing as if it were instructions TO the agent), the actual user intent is usually "try this" — not "read this and explain it back". Detect by: the block ends with no question and contains shell commands. Run the commands, report what happened, and ignore the tutorial's framing text.
- **The "six-installs-in-a-row" pattern.** If the user fires 5+ install requests back-to-back across messages (very common for someone setting up a fresh Hermes workspace), do NOT spend a turn re-reading the skill each time. The workflow is mechanical: `which skillhub && skillhub --version` once (cache the result), then for each install: `skillhub search <slug>` (in parallel batches of 3) → `skillhub install <slug>` (in parallel batches of 3). Don't re-explain what SkillHub is between installs. Don't show full search output — `head -10` to find the canonical slug, then install. The user knows what they asked for.
- **`--no-skills` is critical when the user says "只安装CLI" (CLI only).** The default install script also pulls a workspace-level skill bundle that may overwrite / shadow hub-installed skills. Always re-pass `--no-skills` if the user's instruction says anything like "只装 CLI"、"skip the skills"、"只装商店不装技能" — the re-install is idempotent.
- **The "post-install credential ritual" pattern.** Many skills ship a `SKILL.md` that says "configure X in `TOOLS.md`" but the actual scripts read env vars (e.g., `FEISHU_APP_ID` / `FEISHU_APP_SECRET` from `os.environ`, `GH_TOKEN` for `gh`). When the user provides app_id + app_secret (or token + key) right after `skillhub install X`:
  1. **Skip the doc, read the skill's actual code/scripts** (`cat $SKILL_DIR/scripts/*.sh` / look for `os.environ` / `process.env`). The code is the source of truth; skill docs lag code.
  2. **Write to `~/.hermes/.env`** (chmod 600 — defaults to 666). Hermes's gateway `source`s this file at process start, so env-var-based tools pick it up automatically. Do NOT add to `~/.bashrc` (leaks to unrelated subprocesses).
  3. **End-to-end verify** with a real call (e.g., for `feishu-enhanced`, run `bash <skill>/scripts/feishu-api.sh token` and confirm a `tenant_access_token` comes back; for `gh`, run `gh auth status` and confirm `Logged in`).
  4. **Report the verification result** in the completion message. "已写入 .env" is NOT a completion; "写入 .env + `gh auth status` 返 `Logged in to liyu9`" IS one.
  5. **Remind the user to revoke at the source** if they pasted a high-value token. See `references/token-hygiene.md` (in `github-auth`) for the revocation flow.
- **The `which` false-positive pattern.** `which skillhub` says the binary exists, but it might be an older version on `PATH` that no longer supports a new flag. Always run `skillhub --version` (and compare to the registry's recommended version) before relying on subcommands that may have changed between releases.
- **The "search returns 8 lookalikes" trap.** When `skillhub search <keyword>` returns multiple close variants (`-pro`, `-lite`, `-1-0-0`, `-bak`, `-litiao`, `-cn`, `-hami-` prefix, etc.), do NOT just install the first or the unversioned one. Read each description's first line and match against the user's stated trigger words. Document your pick in one line in the report ("picked `a-stock-analysis-pro` because user asked for '策略研报', which is in its description, not the unversioned one").

## Common user phrasings

- "请先检查是否已安装 SkillHub 商店…然后安装 X 技能" → exactly the workflow above.
- "安装 a-stock-analysis 技能" / "装一下 find-skills" → skip the check, just search + install.
- "更新 X 技能" / "升级 X" → `skillhub install <slug>` re-installs and upgrades in place.
- "列出已安装的技能" → `ls /home/ubuntu/skills/` (or `skillhub list` if available).
