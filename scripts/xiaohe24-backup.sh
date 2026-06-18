#!/bin/bash
# xiaohe24 记忆备份脚本
# 把 ~/.hermes/memories/ 和 ~/.hermes/SOUL.md 增量提交到 liyu9/xiaohe24 仓库并 push

set -e
set -o pipefail

REPO="/home/ubuntu/xiaohe24"
LOG_DIR="/home/ubuntu/.hermes/logs/xiaohe24-backup"
LOG_FILE="$LOG_DIR/backup.log"
SOURCE_FILES=(
  "/home/ubuntu/.hermes/memories/MEMORY.md"
  "/home/ubuntu/.hermes/memories/USER.md"
  "/home/ubuntu/.hermes/SOUL.md"
)
# 强制 git SSH 用这个私钥文件（避开 ssh-agent 跨进程问题）
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/github_xiaohe24 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

mkdir -p "$LOG_DIR"
echo "========================================" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup start" >> "$LOG_FILE"

cd "$REPO" || { echo "FAIL: cd $REPO" >> "$LOG_FILE"; exit 1; }

# 1. 先 fetch + fast-forward 远端更新（避免和远端落后太多）
git fetch origin main 2>>"$LOG_FILE" || echo "WARN: fetch failed" >> "$LOG_FILE"
git merge --ff-only origin/main 2>>"$LOG_FILE" || echo "WARN: ff-merge skipped" >> "$LOG_FILE"

# 2. 把最新的源文件拷进仓库（先拷再判断，避免提前 short-circuit）
for src in "${SOURCE_FILES[@]}"; do
  if [ -f "$src" ]; then
    cp -f "$src" "$REPO/$(basename "$src")" 2>>"$LOG_FILE"
  fi
done

# 3. 维护 .gitignore（锁文件绝不入库）
cat > "$REPO/.gitignore" <<'EOF'
*.lock
EOF

# 4. 检查是否有未提交的改动（包括 untracked）
git add -A
if git diff --cached --quiet; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] no changes, skip" >> "$LOG_FILE"
  exit 0
fi

# 5. 提交
COMMIT_MSG="backup: memories snapshot $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$COMMIT_MSG" 2>>"$LOG_FILE" || { echo "FAIL: commit" >> "$LOG_FILE"; exit 1; }

# 6. 推送（用 SSH，避开 HTTPS QoS）
if git push origin main 2>>"$LOG_FILE"; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] push OK" >> "$LOG_FILE"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] push FAIL" >> "$LOG_FILE"
  exit 1
fi

# 7. 滚动日志（保留最近 30 份按天的日志）
find "$LOG_DIR" -name "*.log.*" -mtime +30 -delete 2>/dev/null || true
echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup done" >> "$LOG_FILE"
