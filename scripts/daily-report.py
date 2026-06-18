#!/usr/bin/env python3
"""每日 18:00 推送 Hermes 状态日报到飞书"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERMES = Path("/home/ubuntu/.hermes")
CRON_JOBS = HERMES / "cron" / "jobs.json"
BACKUP_LOG = HERMES / "logs" / "xiaohe24-backup" / "backup.log"
SINCE_HOURS = 24

def run(cmd, timeout=10):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return type("R", (), {"stdout": "", "stderr": str(e), "returncode": 1})()

def header():
    now = datetime.now()
    return f"📊 **Hermes 日报** · {now.strftime('%Y-%m-%d %H:%M')}"

def section_cron():
    if not CRON_JOBS.exists():
        return "⏰ **定时任务**：无"
    try:
        data = json.loads(CRON_JOBS.read_text())
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        if not jobs:
            return "⏰ **定时任务**：未配置"
        lines = ["⏰ **定时任务**（共 {} 个）".format(len(jobs))]
        for j in jobs:
            name = j.get("name", "unnamed")
            # schedule 可能是 dict（含 expr 字段）也可能是 string
            sched = j.get("schedule", "?")
            if isinstance(sched, dict):
                sched = sched.get("display") or sched.get("expr") or str(sched)
            next_run = j.get("next_run_at") or "?"
            last = j.get("last_run_at") or "未跑"
            last_status = j.get("last_status") or "—"
            lines.append(f"  • `{name}` · `{sched}` · 上次 {last}（{last_status}） · 下次 {next_run}")
        return "\n".join(lines)
    except Exception as e:
        return f"⏰ **定时任务**：读取失败 `{e}`"

def section_backup():
    if not BACKUP_LOG.exists():
        return "💾 **xiaohe24 备份**：日志不存在（还没跑过）"
    try:
        # 读最近 24h 的日志行
        cutoff = datetime.now() - timedelta(hours=SINCE_HOURS)
        recent = []
        for line in BACKUP_LOG.read_text(errors="ignore").splitlines()[-200:]:
            if "[" in line and "]" in line:
                try:
                    ts_str = line.split("[", 1)[1].split("]", 1)[0]
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    if ts >= cutoff:
                        recent.append(line)
                except (ValueError, IndexError):
                    pass
        if not recent:
            return "💾 **xiaohe24 备份**：24h 内无活动"
        last_line = recent[-1]
        ok_count = sum(1 for l in recent if "OK" in l or "no changes" in l or "done" in l)
        fail_count = sum(1 for l in recent if "FAIL" in l or "WARN" in l)
        return f"💾 **xiaohe24 备份**（24h）: ✅ {ok_count} 成功 / ⚠️ {fail_count} 警告\n  最近：`{last_line[:120]}`"
    except Exception as e:
        return f"💾 **xiaohe24 备份**：读取失败 `{e}`"

def section_health():
    parts = []
    # 磁盘
    df = run("df -h /home 2>/dev/null | tail -1")
    if df.returncode == 0 and df.stdout.strip():
        parts.append(f"  • 磁盘：`{df.stdout.split()[4]}` 已用")
    # 内存
    mem = run("free -h 2>/dev/null | grep Mem")
    if mem.returncode == 0 and mem.stdout.strip():
        parts.append(f"  • 内存：`{mem.stdout.split()[2]}` 已用 / `{mem.stdout.split()[1]}`")
    # Load
    up = run("uptime 2>/dev/null")
    if up.returncode == 0 and up.stdout.strip():
        load = up.stdout.split("load average:")[-1].strip() if "load average" in up.stdout else "—"
        parts.append(f"  • Load：`{load}`")
    return "🖥 **容器健康**\n" + "\n".join(parts) if parts else "🖥 **容器健康**：检测失败"

def section_reminders():
    reminders = []
    # 检查临时 token 是否还存于飞书历史（不能查飞书，跳过）
    # 提醒 SSH key 存在
    ssh_key = Path("/home/ubuntu/.ssh/github_xiaohe24")
    if ssh_key.exists():
        reminders.append("🔐 SSH key 仍存在（`github_xiaohe24`）— 每周检查 GitHub authorized keys")
    # 备份日志大小
    if BACKUP_LOG.exists():
        size_kb = BACKUP_LOG.stat().st_size / 1024
        if size_kb > 1024:
            reminders.append(f"📝 备份日志 {size_kb:.0f}KB，建议手动 truncate")
    # 内存占用
    memory_size = 0
    mem_md = HERMES / "memories" / "MEMORY.md"
    if mem_md.exists():
        memory_size = mem_md.stat().st_size
    if memory_size > 1500:
        reminders.append(f"🧠 MEMORY.md 占用 {memory_size} chars（小赤需精简）")
    return "🔔 **提醒项**\n" + "\n".join(f"  {r}" for r in reminders) if reminders else "🔔 **提醒项**：无"

def main():
    sections = [
        header(),
        section_cron(),
        section_backup(),
        section_health(),
        section_reminders(),
        "_—— 小赤 · 每日 18:00 自动生成_",
    ]
    msg = "\n\n".join(sections)
    print(msg)
    # 也保存一份到本地文件，方便调试
    log_dir = HERMES / "logs" / "daily-report"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md").write_text(msg)

if __name__ == "__main__":
    main()
