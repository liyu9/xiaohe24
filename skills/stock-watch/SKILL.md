---
name: stock-watch
description: A股盘中盯盘 + 收盘复盘 - 主人"星耀提醒"规则集。跌到指定阈值推微信,同档位每天只推一次防骚扰。
---

# A 股盯盘 (星耀提醒)

## 适用场景
主人给一组"跌 X% 可接 / 可T"规则后,搭一个自动化盯盘脚本 + cron,跌到档位推微信。

## 核心文件
- **脚本**: `~/.hermes/scripts/stock-watch.py`
- **状态**: `~/.hermes/scripts/stock-watch-state.json` (防骚扰计数, 新一天自动重置)
- **行情源**: `http://qt.gtimg.cn/q=sh000001,sz000001,...`  (腾讯, 批量 50 条一次拉, GBK 编码, 需 decode('gbk'))
- **标的代码查询**: `https://searchapi.eastmoney.com/api/suggest/get?input=<名字>&type=14&token=D43BF722C8E33BDC906FB84D85E326E8`

## 配套文件
- `references/hermes-send-pitfalls.md` — `hermes send` 必须 Popen+DEVNULL, os.system 会卡死
- `references/code-lookup.md` — eastmoney suggest API 长版 + 行云科技(旧天泽信息) 等改名陷阱
- `scripts/dry-run-test.sh` — 5 步端到端验证脚本 (行情源 / dry-run / 状态 / cron), 不真发微信

## 推送方式
`hermes send --quiet -t weixin -f <tmpfile>` (用文件, 避免 shell 转义; 异步 Popen 不等返回)

## 阈值类型
- **可接**: `跌 X%` 单向触发 (e.g. 创业板ETF 跌 4-5% 可接 → 阈值 -4%)
- **可T**: 双向 ±1.5% 都推, 区分 "可T(强)" / "可T(弱)" (强=涨, 弱=跌)
- **过滤**: 跌停/涨停都跳过 (无法操作)
- **防骚扰**: 同一标的同一档位当天只推 1 次, state key = `日期|名|档位|阈值`

## 模式
- `intraday` (默认): 盘中 9:30-11:30 / 13:00-15:00, 跌到档才推, 没触发静默
- `close`: 收盘后 15:30-16:00, 全清单复盘 (到档 + 未到档都列)

## Cron 模板
```
# 盘中 3 分钟
*/3 9-15 * * 1-5  python3 ~/.hermes/scripts/stock-watch.py intraday
# 收盘复盘 15:30
30 15 * * 1-5    python3 ~/.hermes/scripts/stock-watch.py close
```

## 调用方式
```
python3 ~/.hermes/scripts/stock-watch.py intraday
python3 ~/.hermes/scripts/stock-watch.py close
python3 ~/.hermes/scripts/stock-watch.py intraday --force  # 跳过时间门
STOCK_DRY_RUN=1 python3 ~/.hermes/scripts/stock-watch.py intraday  # 不真发, 只打印
```

## 增减标的
编辑 `WATCHLIST` 列表, 格式 `(name, code, threshold)`, threshold 为正数(跌幅)或 `"T"`(双向 T 票)。新增后无需重启 cron, 下个 tick 自动生效。

## 易踩的坑
1. **qt.gtimg.cn 返回 GBK**, 不是 UTF-8 → 必须 `.decode("gbk","ignore")`
2. **smartbox.gtimg.cn 已 404**, 不要用
3. **field 47/48 才是涨停/跌停标记**, 不是 `parts[3]` 比较 -10%
4. **hermes send 走 os.system 会卡死**, 必须 subprocess.Popen + DEVNULL, 不等返回 (详见 references/hermes-send-pitfalls.md)
5. **股票名带 "T" 后缀** (e.g. "欧科亿T") 是数据层去重技巧, 避免同票在跌档 + T 档冲突
6. **多只同名 ETF**: 创业板/科创/芯片/通信 ETF 各有多只, 选了规模较大的代表; 主人要换具体代码直接改 `WATCHLIST`
7. **eastmoney 搜索 "行云科技" → 300209**, 实测这票现在名字就是"行云科技", 但 6-08 之前叫"天泽信息", 复盘时若用旧名搜不到 (完整改名列表见 references/code-lookup.md)

## 关联 skill
- `finance-data` (research) — 数据层: 同一个 qt.gtimg.cn 端点、eastmoney suggest 名称查代码、字段位置表。本 skill 是它的"上层应用" (watchlist + cron + wechat 推送)。

## 验证步骤
1. 拿样本代码 `python3 ~/.hermes/scripts/stock-watch.py close --force` 跑一次, 确认行情源通
2. `STOCK_DRY_RUN=1 python3 ~/.hermes/scripts/stock-watch.py intraday` 看是否生成正确消息
3. 真实环境跑 `intraday` (不 dry-run) 验微信收到
4. 检查 `~/.hermes/scripts/stock-watch-state.json` 的 sent 标记是否累加正确
