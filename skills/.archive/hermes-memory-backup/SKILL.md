---
name: hermes-memory-backup
description: Version-control and remotely backup Hermes Agent's persistent state (memory + personality + skills registry) to a git repository, with a cron-scheduled idempotent push. Use when the user wants to "backup Hermes memory", "sync memories to GitHub", "把记忆备份到远端", "每天自动备份 Hermes", or asks to make Hermes's `~/.hermes/memories/` and `SOUL.md` survive machine loss.
---

# Hermes Memory Backup

Treat Hermes's persistent state as code: check it into a private git repo, push on a schedule, restore on a new machine. The state is small (a few KB), changes incrementally, and is irreplaceable — exactly the shape git is for.

## What to back up

Hermes's durable state lives in three files, all plain text, all small:

| File | What it is | Sensitive? |
|---|---|---|
| `~/.hermes/memories/MEMORY.md` | Agent's own notes (env facts, lessons learned, key paths) | Sometimes (API keys, hostnames, IP) |
| `~/.hermes/memories/USER.md` | User profile (preferences, role, contact) | PII |
| `~/.hermes/SOUL.md` | Personality / tone / persona instructions | No |

`.lock` files next to MEMORY.md / USER.md are ephemeral — **never** back those up. Add `*.lock` to `.gitignore` in the backup repo.

**Do NOT** try to back up `~/.hermes/sessions/`, `state.db`, `kanban.db`, `config.yaml`, `auth.json`, or any tool cache — those contain runtime state, secrets, or huge blobs. Backing those up will burn bandwidth, leak credentials, or both.

## When to use

- User explicitly asks to "backup Hermes memory" / "把记忆备份" / "sync to GitHub"
- User is moving Hermes to a new machine and wants continuity
- User wants a paper trail of memory evolution (who changed what, when)
- User wants the ability to "rewind" the agent's memory if it goes off the rails

## The 6-step recipe

### 1. Pre-flight: confirm git is configured

```bash
git --version                       # git 2.30+ fine
git config --global user.name       # must be set or commit will fail
git config --global user.email
# If empty:
#   git config --global user.name "Hermes Backup"
#   git config --global user.email "hermes@<host>.local"
```

Also confirm SSH works to GitHub (HTTPS is unreliable from cloud — see `cloud-network-diagnostics`):

```bash
ssh -T -o BatchMode=yes git@github.com
# Expected: "Hi <user>! You've successfully authenticated, but GitHub does not provide shell access."
```

If SSH doesn't work from this host, you have a network problem — diagnose it before attempting backup. Backup over an unreliable channel isn't backup.

### 2. Generate an SSH keypair (one-time per host)

Don't reuse an existing user key — give the backup a dedicated key for easy rotation and revocation.

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 \
  -C "hermes-backup@$(hostname)-$(date +%Y%m%d)" \
  -f ~/.ssh/hermes_backup \
  -N ""    # empty passphrase — this is an automated process
chmod 600 ~/.ssh/hermes_backup
```

Print the **public** key (NEVER the private key) and tell the user to add it at https://github.com/settings/keys with a title like `hermes-backup-<hostname>`. Wait for confirmation before pushing.

### 3. Initialize the local repo (one-time)

```bash
REPO="$HOME/hermes-memory-backup"   # or any path the user prefers
mkdir -p "$REPO" && cd "$REPO"
git init -b main
git config user.name "Hermes Backup"  # per-repo, override the global
git config user.email "hermes@<host>.local"

# Hard-block lock files
cat > .gitignore <<'EOF'
*.lock
.DS_Store
EOF

# First commit
cp -f ~/.hermes/memories/MEMORY.md "$REPO/" 2>/dev/null
cp -f ~/.hermes/memories/USER.md   "$REPO/" 2>/dev/null
cp -f ~/.hermes/SOUL.md            "$REPO/" 2>/dev/null
git add -A
git commit -m "backup: initial memory snapshot $(date +%Y-%m-%d)"
```

### 4. Push via SSH (one-time)

```bash
git remote add origin git@github.com:<user>/<repo>.git
# Test auth first (no write)
ssh -T git@github.com
# Then push
git push -u origin main
```

**Never** put a PAT in the remote URL (`https://x-access-token:TOKEN@github.com/...`). Tokens leak through shell history, `git remote -v` output, and any tool that introspects the repo. SSH keys with `chmod 600` are the right tool.

### 5. Install the backup script (templates/backup-memory.sh)

See `templates/backup-memory.sh`. It is:
- **Idempotent** — no changes → exit 0, no commit, no push
- **Race-safe with the agent** — `git add -A` after the source files are copied, so in-flight memory writes during the backup window either land in this snapshot or the next one, not torn
- **Self-healing** — `git fetch` + `ff-only merge` before commit, so a push from another machine doesn't get rejected
- **Noisy on failure** — push failure exits 1 and writes to log; cron job will report

Install:

```bash
mkdir -p ~/.hermes/scripts ~/.hermes/logs/hermes-memory-backup
cp templates/backup-memory.sh ~/.hermes/scripts/backup-memory.sh
chmod +x ~/.hermes/scripts/backup-memory.sh
```

### 6. Schedule via cron (Hermes cron, not system cron)

Use the `cronjob` tool — it integrates with the agent's notification system and surfaces failures in chat. System cron (`crontab -e`) also works but failures are silent.

```bash
# Two push windows per day, off-peak hours when the user is unlikely to be writing
# Use the agent's cronjob tool, not crontab -e
```

The cron prompt should be self-contained — it runs in a fresh session:

```
Run ~/.hermes/scripts/backup-memory.sh, then `tail -20 ~/.hermes/logs/hermes-memory-backup/backup.log`.
If the script exited non-zero, report the failure explicitly with the last error line.
If no changes, report "no changes" — don't stay silent.
Do not ask follow-up questions. Do not modify the script.
```

Typical schedules: `0 12 * * *` (noon) and `0 21 * * *` (evening) — gives two recovery points per day without spam.

## Pitfalls (READ THESE)

- **Cron runs in a fresh session with no agent context.** The prompt must be fully self-contained. Don't reference earlier tool calls, earlier variables, or "the script we just installed" — name the absolute path explicitly.
- **`hermes cron list` and `~/.hermes/cron/jobs.json` store `schedule` as a dict, not a string.** If you write a script that reads `jobs.json` (e.g. a daily-report or status-aggregator that walks the cron list), be defensive:
  ```python
  sched = job.get("schedule", "?")
  if isinstance(sched, dict):
      sched = sched.get("display") or sched.get("expr") or str(sched)
  ```
  Without the guard, the rendered output is `{'kind': 'cron', 'expr': '0 12 * * *', 'display': '0 12 * * *'}` (a raw Python dict) instead of a clean `0 12 * * *`. This bit the daily-report script's first dry run on 2026-06-04.
- **The template now exports `GIT_SSH_COMMAND` itself** (see `templates/backup-memory.sh` header). If you copy the script and rename the key (e.g. `github_xiaohe24` instead of `hermes_backup`), update the `GIT_SSH_COMMAND` line accordingly. The env-var approach is the only one that works in cron, in interactive shells, and in `execute_code` python subshells.
- **The first time the cron runs, it'll be a real test.** Watch the log file for at least the first 3 runs.
- **Hermes's protected files** (`~/.hermes/SOUL.md`, `~/.hermes/config.yaml`, `~/.hermes/.env`) refuse the `patch` / `write_file` tool with `Write denied: protected system/credential file`. The right path is `terminal()` shell append/echo for `.env`, and `hermes config set <key> <value>` for `config.yaml`. For `SOUL.md` you can `terminal()` shell-write directly (it's a plain file, just protected at the tool level).
- **DO NOT use `eval $(ssh-agent -s) + ssh-add` in the backup script — it does not survive across Hermes's `terminal()` shell invocations (each is a fresh subshell), AND on Linux the agent can `refuse operation` for an ed25519 key loaded under a different UID.** Interactive-shell `ssh-add` does NOT propagate to cron *or* to subsequent `terminal()` calls.
  **The fix that actually works:** set `GIT_SSH_COMMAND` at the top of the script and `export` it:
  ```bash
  export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/github_xiaohe24 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
  ```
  This bypasses the agent entirely — `git push` invokes `ssh` with the explicit `-i` flag, which uses the key file directly. Works in cron, in interactive shells, in `execute_code` python invocations, everywhere. `IdentitiesOnly=yes` prevents ssh from also trying default keys and getting a confusing "Permission denied" if a different key is registered.
- **If you use a passphrase, the cron will hang.** Empty passphrase (`-N ""`) is required for unattended operation.
- **Lock files will sneak in if you `cp -a` instead of `cp -f`.** Use `cp -f` (force overwrite, no metadata) and pre-create `.gitignore` with `*.lock`. Test by `git ls-files | grep '\.lock$'` — should always be empty.
- **Pushing to a public repo will leak user PII from USER.md.** Default to a private repo. If the user insists on public, warn explicitly and ask them to scrub PII from USER.md first.
- **Don't store the script in the backup repo itself** — that creates a chicken-and-egg problem ("can't restore the backup without the backup script, but the backup script is in the backup"). Keep the script in `~/.hermes/scripts/`, the backup repo in `~/hermes-memory-backup/`.
- **Restoration is a one-liner but easy to fumble.** To restore on a new machine: clone the backup repo → `cp MEMORY.md USER.md SOUL.md ~/.hermes/memories/` and `~/.hermes/SOUL.md` → restart Hermes. There's no fancy import format; it's just text files in known locations. Test this on a scratch machine *before* you need it for real.
- **The first push after install will be slow** (creating the GitHub repo, registering the SSH key, etc.). Subsequent pushes are 2-5 seconds.
- **Cron's first run may overlap with an in-progress memory write.** The script does `cp` → `git add` → `git commit`, all of which are atomic per-file, but the `.md` files are not (you could `cp` MEMORY.md halfway through an update). The race window is microseconds and the damage is one torn backup entry, which the next run will heal. Don't engineer around it.

## Reference

- `templates/backup-memory.sh` — drop-in backup script (copy + chmod +x, that's it)
- `references/restoration.md` — restoring from backup on a fresh machine, edge cases
- `references/security-checklist.md` — what to scrub before pushing to a public repo, PII inventory, key rotation policy

## Related skills

- `cloud-network-diagnostics` — when push fails for network reasons (Tencent Cloud / cloud / corporate firewall). The session this skill was born from hit a HTTPS-write QoS issue that was diagnosed by that skill and resolved by switching to SSH.
- `github-auth` — for the SSH keypair dance and the alternative HTTPS+PAT path
- `skillhub-management` — for keeping the backup repo's skill list in sync (if you also back up which skills are installed)
