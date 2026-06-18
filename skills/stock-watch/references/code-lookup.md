# Stock-name → code lookup (Eastmoney Suggest)

When a watchlist is given as Chinese names (e.g. "行云科技", "科顺股份", "国瓷材料"),
you need 6-digit codes + market prefix (`sh`/`sz`) before `qt.gtimg.cn` will respond.

## Endpoint

```
GET https://searchapi.eastmoney.com/api/suggest/get
  ?input=<URL-encoded Chinese name>
  &type=14
  &token=D43BF722C8E33BDC906FB84D85E326E8
Headers: User-Agent: Mozilla/5.0
         Referer: https://www.eastmoney.com/
```

Returns JSON:
```json
{
  "QuotationCodeTable": {
    "Data": [
      {
        "Code": "300209",
        "Name": "行云科技",
        "SecurityTypeName": "深证A股",
        "MarketType": "0",
        ...
      }
    ]
  }
}
```

- `MarketType="1"` → 上交所 → prefix `sh`
- `MarketType="0"` → 深交所 → prefix `sz`
- `MarketType="2"` → 港股 → use `hk` endpoint instead

## Disambiguation logic (used in stock-watch.py)

```python
items = d["QuotationCodeTable"]["Data"]
# prefer real tradeable A-share over ETF/fund/HK
priority = ("沪深A股","上证A股","深证A股","北证A股","科创板","创业板")
pick = None
for want in priority:
    for it in items:
        if it.get("SecurityTypeName") == want:
            pick = it; break
    if pick: break
if not pick and items: pick = items[0]
prefix = "sh" if pick["MarketType"]=="1" else "sz"
code = f"{prefix}{pick['Code']}"
```

## Top 5 gotchas (June 2026)

1. **`行云科技 → 300209` is a recent rename.** Was 天泽信息 until ~2025. If you
   search "天泽信息" the suggest returns nothing useful. The reverse (search
   new name) works because Eastmoney's data is current. Lesson: always search
   the **current** name the user gave you; don't second-guess.

2. **Same name, multiple symbols** — many Chinese names (科翔股份, 北方铜业,
   卓胜微, 紫金矿业) exist on both SH and SZ historically, or have HK
   parallels. Use `SecurityTypeName` priority above, never just `Code`.

3. **ETF naming collisions** — `创业板ETF` has 5+ issuers: 159915 (易方达),
   159205 (东财), 159951 (嘉实), etc. They have different 规模/费率/跟踪误差.
   For watch/push purposes pick the highest-成交量 one and confirm with the
   user. Don't auto-pick the first result.

4. **`smartbox.gtimg.cn` is 404** — do not use it for name lookup. This is
   the old Tencent Finance suggest endpoint. Eastmoney is the only free
   public no-key option that works in 2026.

5. **Rate limit** — 5-10 requests/sec is fine. If you batch all 50 names
   in a tight loop with no sleep, you may get 429s after ~100. For typical
   watchlist size (50 names, build once) this never matters.

## Cross-reference

- `finance-data` skill → "Stock-name → code lookup" section (this file is
  the long-form version)
- The actual lookup helper lives inline in `~/.hermes/scripts/stock-watch.py`
  setup section
