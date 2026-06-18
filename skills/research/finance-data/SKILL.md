---
name: finance-data
description: Fetch real-time and historical stock/equity quotes from free public endpoints without API keys. Covers A股 (沪深北交所 via tencent qt.gtimg.cn, sina), HK stocks (Tencent Finance qt.gtimg.cn, AAStocks), and US stocks (Stooq, Yahoo unofficial). Use when the user asks for stock price, market quote, 实时行情, 分时, K线, 涨跌, 成交额, or any "查一下 X 的股价" / "X 行情" / "X quote" request.
---

# Finance Data (free public endpoints)

Real-time quotes without API keys. The endpoints are public, rate-limited per-IP, and return GBK-encoded Chinese on Chinese sources — decode or pipe to `iconv`/`python3` for clean output.

## Endpoints

### A股 + 港股 (Tencent Finance) — primary

`https://qt.gtimg.cn/q=<market><code>` returns a single-line GBK string in the format
`v_<key>="~<name>~<code>~<price>~<prev_close>~<open>~<volume>~...~<change>~<pct>~..."`.

| Market | Prefix | Example          |
|--------|--------|------------------|
| 上证    | `sh`   | `sh600519`        |
| 深证    | `sz`   | `sz000001`        |
| 北证    | `bj`   | `bj830799`        |
| 港股    | `hk`   | `hk00700` (腾讯)  |

Quick quote (one-liner):
```bash
curl -sL "https://qt.gtimg.cn/q=hk00700" -H "User-Agent: Mozilla/5.0" \
  | iconv -f gbk -t utf-8
```

For multiple symbols, separate with commas:
```bash
curl -sL "https://qt.gtimg.cn/q=sh600519,sz000001,hk00700" -H "User-Agent: Mozilla/5.0" \
  | iconv -f gbk -t utf-8
```

### A股 realtime snapshot (Sina) — fallback
`https://hq.sinajs.cn/list=sh600519` — requires `Referer: https://finance.sina.com.cn` header. Returns a similar single-line string.

### A股 K线 / 历史K线 (Sina)
`https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=1023`
- `scale`: `240` = 日K, `60` = 小时, `30` = 30分钟, `15` = 15分钟, `5` = 5分钟, `1` = 1分钟
- Returns JSON array of `[day, open, high, low, close, volume]`.

### 美股 (Stooq) — primary
`https://stooq.com/q/l/?s=aapl.us&f=sd2t2ohlcv&h&e=csv`
- Append `.us` for US, `.uk` for LSE, etc.
- Returns CSV: `Symbol,Date,Time,Open,High,Low,Close,Volume`.

### 美股 (Yahoo unofficial) — flaky
`https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&range=1d`
- Often blocked or rate-limited. Try Stooq first.

## Parsing the Tencent string

Field positions for `qt.gtimg.cn` (delimiter `~`):
1. 名称 (name)
2. 代码 (code)
3. 当前价 (current price)
4. 昨收 (prev close)
5. 今开 (open)
6. 成交量 (lots for A股, shares for HK)
7. … (intraday buy/sell volumes)
8. … (intraday prices)
9. 涨跌额 (change)
10. 涨跌幅% (pct change)
11. 最高 (high)
12. 最低 (low)
13. … price/volume ladder
14. 成交额 (turnover, 元/HKD)
15. 52w high, 52w low, …

The full schema varies by market. Parse defensively (split on `~`, skip empty fields) rather than hard-coding positions. For full field reference per market, see `references/tencent-qt-schema.md` if you generate it; otherwise rely on the standard `~`-split.

## Stock-name → code lookup (Eastmoney Suggest)

When the user gives a stock by Chinese name (e.g. "行云科技", "科顺股份") and you need the 6-digit code + market prefix for `qt.gtimg.cn`:

```
GET https://searchapi.eastmoney.com/api/suggest/get
  ?input=<URL-encoded name>
  &type=14
  &token=D43BF722C8E33BDC906FB84D85E326E8
Headers: User-Agent: Mozilla/5.0, Referer: https://www.eastmoney.com/
```

Returns JSON with `QuotationCodeTable.Data[]` — each item has `Code`, `Name`, `SecurityTypeName` ("沪深A股", "科创板", "创业板", "基金"), `MarketType` ("1"=沪市, "0"=深市).

**Disambiguation rules:**
- 沪深A股/上证A股/深证A股/科创板/创业板 → real tradeable; use these in priority order
- HK stocks have `MarketType="2"` and `SecurityTypeName` like "港股"; not on `qt.gtimg.cn` `sh/sz` endpoints
- "行云科技" → 300209, but **this name was adopted only recently** (formerly 天泽信息). Searching the old name returns nothing. If the user gives a name and it returns no match, try a substring (first 2 chars) and verify `Name` matches what the user said — recent rename is the #1 reason for "no match".
- Token `D43BF722C8E33BDC906FB84D85E326E8` is a hard-coded public token from Eastmoney's web search; not user-specific.

**Batch lookup pattern** for building a watchlist from a name list: loop 5-10 names per second, no extra throttle needed.

## qt.gtimg.cn field map (A 股, position-fixed)

Beyond the basic fields (name/code/price/prev_close/open/pct), positions 47 and 48 are the limit-up / limit-down flags:

| Pos | Meaning                                            |
|-----|----------------------------------------------------|
| 1   | 名称 (name)                                        |
| 2   | 代码 (6-digit, no prefix)                          |
| 3   | 当前价 (current)                                   |
| 4   | 昨收 (prev close)                                  |
| 5   | 今开 (open)                                        |
| 6   | 成交量 (lots = 100 shares)                         |
| 30  | 时间戳 `YYYYMMDDHHMMSS`                            |
| 33  | 今日最高                                           |
| 34  | 今日最低                                           |
| 38  | 涨跌额                                             |
| 39  | 涨跌幅 (%，already in %)                           |
| 47  | **涨停标记** = `"1"` if at limit-up, else `"0"` or empty |
| 48  | **跌停标记** = `"1"` if at limit-down              |

Always read limit-up/down from fields 47/48 — don't infer from `pct >= 9.9` (新股 first-day limits differ, and 你也不想在非涨跌停票上误判).

## Pitfalls

- **GBK encoding on Chinese sources.** The raw bytes are GBK. A naked `curl` to stdout shows garbled CJK in the terminal but the data is correct. Pipe through `iconv -f gbk -t utf-8` for human-readable output, or `iconv -f gbk -t utf-8 // IGNORE` if some bytes are corrupt.
- **Use `iconv`, not `python3 -c` round-trips.** The fastest clean read of a Tencent or Sina quote is `curl -sL 'https://qt.gtimg.cn/q=hk00700' -H 'User-Agent: Mozilla/5.0' | iconv -f gbk -t utf-8`. Trying to decode via Python (`data.encode('latin-1').decode('gbk')`) works but is 10× slower and breaks if any byte is invalid. `iconv` is on every Linux box.
- **When parsing the raw string in scripts, don't double-decode.** If you do `curl ... | iconv -f gbk -t utf-8 | python3 -c "..."` and the Python script then tries `.encode('gbk').decode('utf-8')`, you've already corrupted the bytes. Pick one: either pipe through `iconv` and treat output as UTF-8 throughout, OR keep raw GBK and decode once in Python.
- **Tencent endpoint is HTTP, but use HTTPS** (`https://qt.gtimg.cn`). It works either way; HTTPS avoids MITM on untrusted networks.
- **`smartbox.gtimg.cn` is 404** as of mid-2026. Do not use it for stock-name lookup. Use Eastmoney Suggest above.
- **Yahoo Finance is often blocked** from cloud IPs / data center egress. Don't rely on it; default to Tencent or Stooq.
- **No API key, but rate-limited.** Tens of requests/sec is fine; hundreds will get throttled. For bulk, batch into one request (comma-separated symbols) instead of looping.
- **Trading-hours caveat.** Quotes return the *last* price. Outside market hours, that's the previous close — say so explicitly when reporting to the user.
- **HK `volume` field is in shares, A股 `volume` is in 手 (lots = 100 shares).** Turnover (成交额) is always in the local currency.
- **Sina requires `Referer`.** Without `Referer: https://finance.sina.com.cn`, requests return 403.
- **52-week high/low may be `0.000` for newly-listed or suspended stocks.** Don't present zeros as real data.
- **Same name, multiple symbols.** Many Chinese stock names (科翔股份、东方电气、北方铜业...) have SH and SZ or HK variants. Eastmoney's `SecurityTypeName` + `MarketType` picks the right one. For watchlists, pin both `Code` and `MarketType` — never trust name-only matching.
- **ETF naming collisions.** 创业板ETF / 芯片ETF / 通信ETF / 煤炭ETF / 矿业ETF each have multiple issuers (华夏/易方达/国泰/华泰柏瑞/东财) and 3-5 codes per concept. Pick the largest by 规模 / 成交额 for liquid trading; user may have a specific one in mind, ask if ambiguous.

## When to defer to a skill

- For A股 *analysis* (分时量能、主力资金、持仓盈亏) use the `a-stock-analysis` skill (installed via skillhub).
- For HK/US analysis beyond a quote, no installed skill covers it; do the analysis inline with the data above.
