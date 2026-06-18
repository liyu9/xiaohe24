#!/bin/bash
# setup-bitable.sh — one-shot Feishu Bitable setup for an auto-logger plugin.
# Run this once per event class. The result (APP_TOKEN + TABLE_ID) goes
# into ~/.hermes/.env. After this, the runtime path is OpenClaw-only.
#
# Usage: edit the SCHEMA + FIELDS block below, then:
#   bash setup-bitable.sh

set -euo pipefail

# --- Credentials ----------------------------------------------------------
source ~/.hermes/.env  # FEISHU_APP_ID, FEISHU_APP_SECRET

# --- User-editable: change APP_NAME and the FIELDS array per event class --
APP_NAME="过敏药记录"

# Field types: 1 = text/single-select, 5 = date/datetime
# date_formatter: "yyyy-MM-dd HH:mm" for date-time, "yyyy-MM-dd" for date
FIELDS=(
  '{"field_name":"服药时间","type":5,"property":{"date_formatter":"yyyy-MM-dd HH:mm"}}'
  '{"field_name":"药品名","type":1,"property":{"options":[{"name":"氯雷他定","color":0},{"name":"西替利嗪","color":1},{"name":"依巴斯汀","color":2},{"name":"其他","color":3}]}}'
  '{"field_name":"剂量","type":1,"property":{"options":[{"name":"5mg","color":0},{"name":"10mg","color":1},{"name":"20mg","color":2},{"name":"1片","color":3},{"name":"其他","color":4}]}}'
  '{"field_name":"症状","type":1,"property":{"options":[{"name":"荨麻疹","color":0},{"name":"鼻塞","color":1},{"name":"打喷嚏","color":2},{"name":"眼睛痒","color":3},{"name":"皮肤痒","color":4},{"name":"其他","color":5}]}}'
  '{"field_name":"备注","type":1}'
)

# --- 1. Get tenant token ---------------------------------------------------
TOKEN=$(curl -sS -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
  -H "Content-Type: application/json" \
  -d "{\"app_id\":\"$FEISHU_APP_ID\",\"app_secret\":\"$FEISHU_APP_SECRET\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['tenant_access_token'])")
echo "✅ token ok (len=${#TOKEN})"

# --- 2. Create the Bitable app -------------------------------------------
echo "=== creating app '$APP_NAME' ==="
APP_RESP=$(curl -sS -X POST "https://open.feishu.cn/open-apis/bitable/v1/apps" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$APP_NAME\"}")
APP_TOKEN=$(echo "$APP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['app']['app_token'])")
TABLE_ID=$(echo "$APP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['app']['default_table_id'])")
echo "APP_TOKEN=$APP_TOKEN"
echo "TABLE_ID=$TABLE_ID"
URL=$(echo "$APP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['app']['url'])")
echo "URL=$URL"

# --- 3. Add fields --------------------------------------------------------
echo "=== adding fields ==="
for col in "${FIELDS[@]}"; do
  name=$(echo "$col" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['field_name'])")
  code=$(curl -sS -o /tmp/field_resp -w "%{http_code}" -X POST \
    "https://open.feishu.cn/open-apis/bitable/v1/apps/$APP_TOKEN/tables/$TABLE_ID/fields" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$col")
  if [ "$code" = "200" ]; then
    echo "  ✅ $name"
  else
    echo "  ❌ $name ($code): $(cat /tmp/field_resp | head -c 200)"
  fi
done

# --- 4. Write a test row, list it back, then clean up --------------------
echo "=== smoke test (write + list + delete) ==="
NOW_MS=$(date +%s%3N)
TEST_RESP=$(curl -sS -X POST "https://open.feishu.cn/open-apis/bitable/v1/apps/$APP_TOKEN/tables/$TABLE_ID/records" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"fields\":{\"服药时间\":$NOW_MS,\"药品名\":\"氯雷他定\",\"剂量\":\"10mg\",\"症状\":\"荨麻疹\",\"备注\":\"系统初始化测试\"}}")
TEST_RECORD_ID=$(echo "$TEST_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('record',{}).get('record_id',''))")
echo "  wrote test record: $TEST_RECORD_ID"

# verify
sleep 1
curl -sS "https://open.feishu.cn/open-apis/bitable/v1/apps/$APP_TOKEN/tables/$TABLE_ID/records" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', {}).get('items') or []
print(f'  verified: {len(items)} record(s) in table')
"

# delete test
curl -sS -X POST "https://open.feishu.cn/open-apis/bitable/v1/apps/$APP_TOKEN/tables/$TABLE_ID/records/batch_delete" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"records\":[\"$TEST_RECORD_ID\"]}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  cleaned up: code={d.get(\"code\")}, deleted={len(d.get(\"data\",{}).get(\"records\",[]))}')"

# --- 5. Print env vars to add to ~/.hermes/.env ---------------------------
cat <<EOF

================================================================
✅ Setup done. Add these to ~/.hermes/.env:
================================================================

BITABLE_APP_TOKEN=$APP_TOKEN
BITABLE_TABLE_ID=$TABLE_ID

================================================================
Then verify the OpenClaw path:
  curl -sS -X POST http://127.0.0.1:18789/tools/invoke \\
    -H "Content-Type: application/json" \\
    -H "Authorization: Bearer \$OPENCLAW_GATEWAY_TOKEN" \\
    -d '{
      "name": "feishu_bitable_list_records",
      "args": {
        "app_token": "$APP_TOKEN",
        "table_id": "$TABLE_ID",
        "page_size": 5
      }
    }'
================================================================
EOF
