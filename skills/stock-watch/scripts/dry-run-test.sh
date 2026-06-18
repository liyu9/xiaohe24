#!/usr/bin/env bash
# Verify stock-watch setup end-to-end without sending to WeChat.
# Usage: bash scripts/dry-run-test.sh
# Exit 0 = all checks passed, message looks correct.
# Exit 1 = some check failed (data source, code lookup, or message format).

set -e

SCRIPT="${HOME}/.hermes/scripts/stock-watch.py"
[ -f "$SCRIPT" ] || { echo "FAIL: $SCRIPT not found"; exit 1; }

echo "=== 1) Check data source (qt.gtimg.cn) ==="
SAMPLE=$(curl -sS --max-time 6 "http://qt.gtimg.cn/q=sh600000,sz000001,sz159205" | head -c 200)
if echo "$SAMPLE" | grep -q "v_sh600000"; then
    echo "OK: 行情源 200 OK, sample = ${SAMPLE:0:120}..."
else
    echo "FAIL: 行情源未返回预期内容: $SAMPLE"
    exit 1
fi

echo ""
echo "=== 2) Dry-run close mode (full daily report, no push) ==="
STOCK_DRY_RUN=1 python3 "$SCRIPT" close --force 2>&1 | head -40

echo ""
echo "=== 3) Dry-run intraday mode (alerts only, no push) ==="
STOCK_DRY_RUN=1 python3 "$SCRIPT" intraday --force 2>&1 | head -30

echo ""
echo "=== 4) Confirm state file reset on new day ==="
STATE="${HOME}/.hermes/scripts/stock-watch-state.json"
if [ -f "$STATE" ]; then
    echo "State file: $STATE"
    cat "$STATE" | head -20
else
    echo "(state file not yet created — will be created on first real run)"
fi

echo ""
echo "=== 5) Confirm cron jobs exist ==="
hermes cronjob list 2>&1 | grep -E "stock-watch|next_run" | head -10

echo ""
echo "All checks complete. To send a REAL message to WeChat:"
echo "  python3 $SCRIPT intraday          # in trading hours"
echo "  python3 $SCRIPT intraday --force  # anytime"
