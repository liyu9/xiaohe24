#!/usr/bin/env python3
"""
template_send.py — 用模板快速发卡片（自动变量替换）

用法:
  python template_send.py alert <receive_id> --title "服务异常" --severity "严重" --time "2026-06-04 17:30" --description "CPU > 90%" --button-url "https://grafana.example.com" --alert-id "AL-001"
  python template_send.py progress <receive_id> --title "数据备份" --current 2 --total 5 --status "备份中..." --steps "1. 启动 ✓\n2. 备份 /home ✓\n3. 备份 /etc\n4. 备份 /var\n5. 验证"
  python template_send.py report <receive_id> --title "腾讯 00700" --subtitle "今日行情" --items "**现价：456.200**\n**涨跌：-2.19%**" --button-url "https://quote.eastmoney.com/hk/00700.html"

变量替换：模板里 {VAR_NAME} 会被命令行 --<var> 替换。
"""
import sys
import json
import argparse
from pathlib import Path

# 允许从同目录 import
sys.path.insert(0, str(Path(__file__).parent))
import feishu_card as fc

TEMPLATE_DIR = Path(__file__).parent / "templates"


def load_template(name: str) -> dict:
    """加载模板，去掉 _description/_usage 字段。"""
    path = TEMPLATE_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"模板不存在: {path}")
    tmpl = json.loads(path.read_text(encoding="utf-8"))
    # 卡片 content 在 card 字段（feishu API 期望 content 字段）
    if "card" in tmpl:
        return tmpl["card"]
    return tmpl


def fill_template(card: dict, replacements: dict) -> dict:
    """递归替换 {VAR} 占位符。"""
    if isinstance(card, str):
        out = card
        for k, v in replacements.items():
            out = out.replace("{" + k + "}", str(v))
        return out
    if isinstance(card, list):
        return [fill_template(x, replacements) for x in card]
    if isinstance(card, dict):
        return {k: fill_template(v, replacements) for k, v in card.items()}
    return card


def cmd_alert(args):
    card = load_template("alert")
    card = fill_template(card, {
        "TITLE": args.title,
        "SEVERITY": args.severity,
        "TIME": args.time,
        "DESCRIPTION": args.description,
        "BUTTON_URL": args.button_url,
        "ALERT_ID": args.alert_id,
        "TRACE_ID": args.trace_id or "n/a",
    })
    msg_id = fc.send_card(args.receive_id, card, args.receive_id_type)
    print(f"✅ 告警卡片已发送: {msg_id}")
    return msg_id


def cmd_progress(args):
    # 自动构造步骤列表（带 ✓ / 进行中 / 未开始）
    steps_text = args.steps
    if args.current and args.steps:
        # 自动在第 N 行加 ✅
        lines = steps_text.split("\n")
        for i in range(args.current):
            if "✓" not in lines[i] and "✅" not in lines[i]:
                lines[i] = lines[i] + " ✅"
        if args.current <= len(lines):
            lines[args.current - 1] = lines[args.current - 1] + " ⏳"
        steps_text = "\n".join(lines)

    card = load_template("progress")
    card = fill_template(card, {
        "TITLE": args.title,
        "CURRENT_STEP": args.current,
        "TOTAL_STEPS": args.total,
        "STEPS_LIST": steps_text,
        "STATUS": args.status,
        "TIME": args.time or "just now",
    })
    msg_id = fc.send_card(args.receive_id, card, args.receive_id_type)
    print(f"✅ 进度卡片已发送: {msg_id}")
    return msg_id


def cmd_report(args):
    card = load_template("report")
    card = fill_template(card, {
        "TITLE": args.title,
        "SUBTITLE": args.subtitle,
        "ITEMS": args.items,
        "BUTTON_URL": args.button_url,
        "BUTTON_LABEL": args.button_label or "查看详情",
    })
    msg_id = fc.send_card(args.receive_id, card, args.receive_id_type)
    print(f"✅ 报告卡片已发送: {msg_id}")
    return msg_id


def main():
    parser = argparse.ArgumentParser(description="飞书卡片模板发送")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_alert = sub.add_parser("alert", help="告警卡片")
    p_alert.add_argument("receive_id")
    p_alert.add_argument("--receive-id-type", default="open_id")
    p_alert.add_argument("--title", required=True)
    p_alert.add_argument("--severity", default="严重")
    p_alert.add_argument("--time", required=True)
    p_alert.add_argument("--description", required=True)
    p_alert.add_argument("--button-url", required=True)
    p_alert.add_argument("--alert-id", default="AL-001")
    p_alert.add_argument("--trace-id", default=None)
    p_alert.set_defaults(func=cmd_alert)

    p_prog = sub.add_parser("progress", help="任务进度")
    p_prog.add_argument("receive_id")
    p_prog.add_argument("--receive-id-type", default="open_id")
    p_prog.add_argument("--title", required=True)
    p_prog.add_argument("--current", type=int, required=True)
    p_prog.add_argument("--total", type=int, required=True)
    p_prog.add_argument("--status", required=True)
    p_prog.add_argument("--steps", required=True, help="换行分隔的步骤列表")
    p_prog.add_argument("--time", default=None)
    p_prog.set_defaults(func=cmd_progress)

    p_rep = sub.add_parser("report", help="数据报告")
    p_rep.add_argument("receive_id")
    p_rep.add_argument("--receive-id-type", default="open_id")
    p_rep.add_argument("--title", required=True)
    p_rep.add_argument("--subtitle", default="")
    p_rep.add_argument("--items", required=True)
    p_rep.add_argument("--button-url", required=True)
    p_rep.add_argument("--button-label", default=None)
    p_rep.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
