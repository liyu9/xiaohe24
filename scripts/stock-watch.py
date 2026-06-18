#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股盯盘 / 收盘复盘 - 主人"星耀提醒"规则集
- 盘中 cron: 每 3 分钟查一次, 跌到阈值立即推送微信
- 收盘 cron: 15:30 后跑一次, 给出当日全清单
- 防骚扰: 同一标的同一档位每天最多推 1 次
- 数据源: qt.gtimg.cn 腾讯行情 (GBK, 1 条 HTTP 拿到 50+ 票)
"""
import os, sys, json, time, urllib.request, urllib.parse, re, subprocess, tempfile
from datetime import datetime, time as dtime
from pathlib import Path

# === 标的 + 阈值 ===
# 格式: (name, code, drop_pct)   # 跌这个 % 就提醒 (正数, 比较 |当日跌幅| >= drop_pct)
# 't' = t 操作 (持仓日内做T, 触发后推"可T"提醒, 阈值口径不同)
WATCHLIST = [
    # === ETF ===
    ("创业板ETF",  "sz159205", 4.0),
    ("科创ETF",   "sz159335", 5.0),
    ("芯片ETF",   "sz159310", 8.0),
    ("通信ETF",   "sz159507", 8.0),
    ("矿业ETF",   "sh561330", 5.0),
    ("煤炭ETF",   "sh515220", 2.0),
    ("卫星ETF",   "sz159206", 3.0),

    # === 跌 15-20% 可接 ===
    ("欧科亿",    "sh688308", 15.0),
    ("晶丰明源",  "sh688368", 15.0),
    ("金海通",    "sh603061", 15.0),
    ("和林微纳",  "sh688661", 15.0),
    ("南亚新材",  "sh688519", 15.0),
    ("长川科技",  "sz300604", 15.0),

    # === 跌 10-15% 可接 ===
    ("铜冠铜箔",  "sz301217", 10.0),
    ("生益电子",  "sh688183", 10.0),
    ("日联科技",  "sh688531", 10.0),
    ("鼎龙股份",  "sz300054", 10.0),
    ("行云科技",  "sz300209", 10.0),
    ("科顺股份",  "sz300737", 10.0),
    ("胜宏科技",  "sz300476", 10.0),
    ("国瓷材料",  "sz300285", 10.0),

    # === 跌 8% 可接 ===
    ("北方铜业",  "sz000737", 8.0),
    ("云南锗业",  "sz002428", 8.0),
    ("锡业股份",  "sz000960", 8.0),
    ("骄成超声",  "sh688392", 8.0),
    ("联特科技",  "sz301205", 8.0),
    ("太极实业",  "sh600667", 8.0),
    ("博杰股份",  "sz002975", 8.0),
    ("芯原股份",  "sh688521", 8.0),
    ("思泉新材",  "sz301489", 8.0),
    ("征和工业",  "sz003033", 8.0),
    ("华通线缆",  "sh605196", 8.0),
    ("卓胜微",    "sz300782", 8.0),
    ("华特气体",  "sh688268", 8.0),
    ("科翔股份",  "sz300903", 8.0),
    ("天孚通信",  "sz300394", 8.0),

    # === 跌 5-8% 可接 ===
    ("东方电气",  "sh600875", 5.0),
    ("荣昌生物",  "sh688331", 5.0),
    ("歌尔股份",  "sz002241", 5.0),
    ("亿纬锂能",  "sz300014", 5.0),
    ("泰豪科技",  "sh600590", 5.0),
    ("科士达",    "sz002518", 5.0),
    ("紫金矿业",  "sh601899", 5.0),
    ("洛阳钼业",  "sh603993", 5.0),
    ("华康洁净",  "sz301235", 5.0),
    ("可立克",    "sz002782", 5.0),
    ("通富微电",  "sz002156", 5.0),

    # === 可 T (持仓做T) - 阈值: 涨 1-3% 或 跌 1-3% 都算可T信号 ===
    # 暂用: 跌 1.5% 触发(弱势) / 涨 1.5% 触发(强势) 都给提醒
    ("特锐德",    "sz300001", "T"),
    ("亚翔集成",  "sh603929", "T"),
    ("飞龙股份",  "sz002536", "T"),
    ("温州宏丰",  "sz300283", "T"),
    ("中控技术",  "sh688777", "T"),
    ("红星发展",  "sh600367", "T"),
    ("思源电气",  "sz002028", "T"),
    ("海天瑞声",  "sh688787", "T"),
    ("欧科亿T",   "sh688308", "T"),  # 同时是跌15-20和可T
]

# 同一只票的"跌 X% 档"和"T 档"分开计数
# 把 "欧科亿T" 在数据层做成独立行, 推送时合并显示

STATE_FILE = Path.home() / ".hermes" / "scripts" / "stock-watch-state.json"

def load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: return {}
    return {}

def save_state(s):
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))

def today_key():
    return datetime.now().strftime("%Y-%m-%d")

def fetch_quotes(codes):
    """qt.gtimg.cn 批量, 一次拉 50 条, 返回 dict[code] -> dict"""
    url = "http://qt.gtimg.cn/q=" + ",".join(codes)
    raw = urllib.request.urlopen(url, timeout=6).read().decode("gbk", "ignore")
    result = {}
    for line in raw.strip().split("\n"):
        m = re.match(r'v_(\w+)="([^"]*)"', line)
        if not m: continue
        code, payload = m.group(1), m.group(2)
        parts = payload.split("~")
        if len(parts) < 40: continue
        try:
            cur = float(parts[3] or 0)
            prev_close = float(parts[4] or 0)
            open_p = float(parts[5] or 0)
            pct = ((cur - prev_close) / prev_close * 100) if prev_close else 0
            result[code] = {
                "name": parts[1],
                "code": code,
                "cur": cur,
                "prev_close": prev_close,
                "open": open_p,
                "pct": pct,
                "high": float(parts[33] or 0) if len(parts) > 33 else 0,
                "low":  float(parts[34] or 0) if len(parts) > 34 else 0,
                "time": parts[30] if len(parts) > 30 else "",
                "limit_up":   parts[47] == "1" if len(parts) > 47 else False,  # 涨停
                "limit_down": parts[48] == "1" if len(parts) > 48 else False,  # 跌停
            }
        except (ValueError, IndexError):
            continue
    return result

def is_trading_time():
    """A 股盘中: 9:30-11:30, 13:00-15:00"""
    now = datetime.now()
    if now.weekday() >= 5: return False
    t = now.time()
    return (dtime(9,30) <= t <= dtime(11,30)) or (dtime(13,0) <= t <= dtime(15,0))

def is_close_summary_time():
    """收盘后 15:30 跑复盘"""
    now = datetime.now()
    if now.weekday() >= 5: return False
    t = now.time()
    return dtime(15,30) <= t <= dtime(16,0)

def check_alerts(quotes, state, mode="intraday"):
    """
    盘中: 逐只检查, 触发档位返回 list
    收盘: 全清单
    返回 list of (name, code, type, pct, threshold, cur, info_str)
    """
    alerts = []
    seen_codes = set()
    for name, code, threshold in WATCHLIST:
        if code in seen_codes: continue  # 欧科亿出现两次 (可接 + T) 单独处理
        q = quotes.get(code)
        if not q: continue
        cur, pct, ld, lu = q["cur"], q["pct"], q.get("limit_down"), q.get("limit_up")
        # 跌停/涨停直接跳过所有档位
        if (ld and pct <= -9.9) or (lu and pct >= 9.9):
            continue
        if mode == "intraday":
            # 跌档
            if isinstance(threshold, (int, float)) and pct <= -threshold:
                k = f"{today_key()}|{name}|down|{threshold}"
                if state.get(k) != "sent":
                    alerts.append((name, code, "down", pct, threshold, cur, "可接"))
                    state[k] = "sent"
            # T 档: 双向 ±1.5% 都提示
            elif threshold == "T" and abs(pct) >= 1.5:
                k = f"{today_key()}|{name}|T|{round(pct,1)}"
                if state.get(k) != "sent":
                    tag = "可T(弱)" if pct < 0 else "可T(强)"
                    alerts.append((name, code, "T", pct, 1.5, cur, tag))
                    state[k] = "sent"
        elif mode == "close":
            # 收盘: 全清单, 标注是否到档
            if isinstance(threshold, (int, float)) and pct <= -threshold:
                alerts.append((name, code, "down", pct, threshold, cur, "可接"))
            elif threshold == "T" and abs(pct) >= 1.5:
                tag = "可T(弱)" if pct < 0 else "可T(强)"
                alerts.append((name, code, "T", pct, 1.5, cur, tag))
    return alerts

def format_intraday(alerts):
    if not alerts: return None
    lines = ["【星耀·盘中提醒】"]
    down = [a for a in alerts if a[2]=="down"]
    tlist = [a for a in alerts if a[2]=="T"]
    if down:
        lines.append(f"📉 跌到接档 ({len(down)}):")
        for name, code, _, pct, th, cur, _ in sorted(down, key=lambda x: x[3]):
            lines.append(f"  {name} {pct:+.2f}% (现 {cur:.2f} / 阈值 -{th}%)")
    if tlist:
        lines.append(f"🔄 可T ({len(tlist)}):")
        for name, code, _, pct, th, cur, tag in sorted(tlist, key=lambda x: x[3]):
            lines.append(f"  {name} {pct:+.2f}% {tag} (现 {cur:.2f})")
    return "\n".join(lines)

def format_close(quotes):
    """收盘复盘: 全清单 + 标记到档"""
    lines = ["【星耀·收盘复盘】", f"数据时间: {datetime.now().strftime('%H:%M')}"]
    by_band = {}
    no_alert = []
    for name, code, threshold in WATCHLIST:
        q = quotes.get(code)
        if not q: continue
        cur, pct = q["cur"], q["pct"]
        if isinstance(threshold, (int, float)) and pct <= -threshold:
            band = f"跌{int(threshold)}%+可接"
            by_band.setdefault(band, []).append(f"{name} {pct:+.2f}% (现 {cur:.2f})")
        elif threshold == "T" and abs(pct) >= 1.5:
            tag = "可T(弱)" if pct < 0 else "可T(强)"
            by_band.setdefault("T档", []).append(f"{name} {pct:+.2f}% {tag}")
        else:
            no_alert.append(f"{name} {pct:+.2f}%")
    for band in ["跌15%+可接","跌10%+可接","跌8%可接","跌5%可接","T档","跌4%ETF","跌5%ETF","跌8%ETF"]:
        items = by_band.get(band, [])
        if items:
            lines.append(f"\n🎯 {band} ({len(items)}):")
            for it in items: lines.append(f"  {it}")
    lines.append(f"\n📊 未触发 ({len(no_alert)}):")
    lines.append("  " + " | ".join(no_alert[:30]))
    if len(no_alert) > 30:
        lines.append(f"  ... 还有 {len(no_alert)-30} 只")
    return "\n".join(lines)

DRY_RUN = os.environ.get("STOCK_DRY_RUN") == "1"
def send(msg):
    """用 hermes send 推到 home channel (微信), 异步不等返回"""
    if DRY_RUN:
        print(f"[DRY-RUN] would send {len(msg)} chars")
        print(msg[:300])
        return
    chunks, cur, cur_len = [], [], 0
    for line in msg.split("\n"):
        if cur_len + len(line) + 1 > 1800:
            chunks.append("\n".join(cur)); cur, cur_len = [], 0
        cur.append(line); cur_len += len(line) + 1
    if cur: chunks.append("\n".join(cur))
    for i, ck in enumerate(chunks, 1):
        if len(chunks) > 1:
            ck = f"[{i}/{len(chunks)}]\n{ck}"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(ck)
            tmp = f.name
        subprocess.Popen(
            ["hermes", "send", "--quiet", "-t", "weixin", "-f", tmp],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

def main():
    args = sys.argv[1:]
    mode = args[0] if args else "intraday"
    force = "--force" in args
    if not force:
        if mode == "intraday" and not is_trading_time():
            return  # 非交易时间静默退出，不推送任何消息
        if mode == "close" and not is_close_summary_time():
            return  # 非收盘后时间静默退出，不推送任何消息
    state = load_state()
    # 新一天重置 state
    if state.get("__date__") != today_key():
        state = {"__date__": today_key()}
    codes = list({c for _, c, _ in WATCHLIST})
    quotes = fetch_quotes(codes)
    if not quotes:
        print(f"[{datetime.now():%H:%M}] 行情拉取失败")
        return
    if mode == "intraday":
        alerts = check_alerts(quotes, state, "intraday")
        msg = format_intraday(alerts)
        if msg:
            print("---SEND---")
            print(msg)
            send(msg)
        else:
            print(f"[{datetime.now():%H:%M}] 全部未到档, 静默")
    elif mode == "close":
        msg = format_close(quotes)
        print("---SEND---")
        print(msg)
        send(msg)
    save_state(state)

if __name__ == "__main__":
    main()
