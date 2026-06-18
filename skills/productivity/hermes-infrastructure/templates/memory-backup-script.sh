#!/bin/bash
# backup-memory.sh — Hermes memory backup to a git repository
# Idempotent: no changes -> exit 0 with "no changes" log
# Self-healing: fetch + ff-only merge before commit
# Silent on success, noisy on failure
#
# Cron-compatible: no agent, no interactive prompts, no ssh-agent dependency.
# Uses GIT_SSH_COMMAND to point git at the dedicated ed25519 key directly —
# works in cron, in interactive shells, and in execute_code python invocations.
#
# Configuration: edit REPO and SOURCE_FILES below. If your key has a different
# name, override the GIT_SSH_COMMAND line.

set -e
set -o pipefail

REPO="${HERMES_BACKUP_REPO:-$HOME/hermes-memory-backup}"
LOG_DIR="${HERMES_BACKUP_LOG_DIR:-$HOME/.hermes/logs/hermes-memory-backup}"
LOG_FILE="$LOG_DIR/backup.log"

SOURCE_FILES=(
  "$HOME/.hermes/memories/MEMORY.md"
  "$HOME/.hermes/memories/USER.md"
  "$HOME/.hermes/SOUL.md"
)

# Force git to use this SSH key directly — bypasses ssh-agent (which doesn't
# survive across Hermes's terminal() subshells and can refuse ed25519 keys
# loaded under a different UID). The key should be generated with empty
# passphrase (`ssh-keygen -N ""`) so this never prompts.
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/hermes_backup -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

mkdir -p "$LOG_DIR"
echo "========================================" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup start" >> "$LOG_FILE"

if [ ! -d "$REPO/.git" ]; then
  echo "FAIL: $REPO is not a git repo (run the install steps first)" >> "$LOG_FILE"
  exit 1
fi

cd "$REPO" || { echo "FAIL: cd $REPO" >> "$LOG_FILE"; exit 1; }

# 1. Sync with remote (fast-forward only — never refuse a remote update)
git fetch origin main 2>>"$LOG_FILE" || echo "WARN: fetch failed (offline?)" >> "$LOG_FILE"
git merge --ff-only origin/main 2>>"$LOG_FILE" || echo "WARN: ff-merge skipped (diverged?)" >> "$LOG_FILE"

# 2. Copy the current source files into the repo
for src in "${SOURCE_FILES[@]}"; do
  if [ -f "$src" ]; then
    cp -f "$src" "$REPO/$(basename "$src")" 2>>"$LOG_FILE"
  fi
done

# 3. Maintain .gitignore (lock files must never be tracked)
cat > "$REPO/.gitignore" <<'EOF'
*.lock
.DS_Store
EOF

# 4. Stage everything
git add -A

# 5. Idempotency check: if nothing staged, exit cleanly
if git diff --cached --quiet; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] no changes, skip" >> "$LOG_FILE"
  exit 0
fi

# 6. Commit
COMMIT_MSG="backup: memory snapshot $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$COMMIT_MSG" 2>>"$LOG_FILE" || { echo "FAIL: commit failed" >> "$LOG_FILE"; exit 1; }

# 7. Push (over SSH, never over HTTPS+token URL)
if git push origin main 2>>"$LOG_FILE"; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] push OK" >> "$LOG_FILE"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup done" >> "$LOG_FILE"
  exit 0
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] push FAIL — see git output above" >> "$LOG_FILE"
  exit 1
fi
