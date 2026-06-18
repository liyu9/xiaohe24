# Feishu Bitable REST API — one-shot setup cheatsheet

The **runtime** path is always OpenClaw's `feishu_bitable_*` tools. This
file documents the **one-time setup** path: direct Feishu REST calls to
create the app, the table, and the columns before the runtime plugin can
write anything.

`templates/setup-bitable.sh` wraps everything below into a single script.
This file is the manual version for when the user wants to do it
interactively in a notebook.

## Endpoints

All under `https://open.feishu.cn/open-apis/`. All require a
`tenant_access_token` from `/auth/v3/tenant_access_token/internal`.

| Operation | Method | Path |
|---|---|---|
| Get tenant token | POST | `/auth/v3/tenant_access_token/internal` |
| Create Bitable app | POST | `/bitable/v1/apps` |
| Add column to table | POST | `/bitable/v1/apps/{app_token}/tables/{table_id}/fields` |
| Insert row | POST | `/bitable/v1/apps/{app_token}/tables/{table_id}/records` |
| List rows | GET | `/bitable/v1/apps/{app_token}/tables/{table_id}/records` |
| Update row | PUT | `/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}` |
| Delete rows (batch) | POST | `/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete` |

## Field types

| Type | code | Properties |
|---|---|---|
| Text | 1 | (no properties for free text) |
| Single-select | 1 | `options: [{name, color}]` |
| Date / DateTime | 5 | `date_formatter: "yyyy-MM-dd HH:mm"` or `"yyyy-MM-dd"` |
| Number | 2 | (formatter options) |
| Multi-select | 1 | `options: [...]`, multi-value field |
| Attachment | 17 | (no properties) |

## Error codes you'll hit

- `code: 99991661` — missing Authorization header. Your `tenant_access_token` expired (90 min TTL) or the `Authorization: Bearer <token>` line is missing.
- `code: 999914001` — invalid app_token. The app does not exist or the app_id used to fetch the token does not own the app.
- `code: 1254045` — table not found. The default `table_id` from app creation is stable; do not regenerate.
- `code: 1254042` — field not found. The field name has a typo or the field was not actually created.
- `code: 9499` — invalid request body. Usually a missing required field. The message includes which field.

## Token caching (for batch operations)

`tenant_access_token` is valid for 90 minutes. If you are making 5+
sequential setup calls (create app + add 5 fields + write test row +
list + delete), cache the token:

```python
import time, json, urllib.request

_token_cache = {"value": "", "expires_at": 0.0}

def get_token(app_id, app_secret):
    now = time.time()
    if _token_cache["value"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["value"]
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=body, headers={"Content-Type": "application/json"})
    data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    if data.get("code") != 0:
        raise RuntimeError(f"token fetch failed: {data}")
    _token_cache["value"] = data["tenant_access_token"]
    _token_cache["expires_at"] = now + int(data.get("expire", 5400))
    return _token_cache["value"]
```

## batch_delete body shape (the easy-to-get-wrong one)

`batch_delete` takes a **list of record_id strings**, NOT a list of
`{record_id: "..."}` objects:

```json
{"records": ["recvlK1fdztpxM", "recvlK2ts48fXH"]}
```

NOT:

```json
{"records": [{"record_id": "recvlK1fdztpxM"}]}  // ← returns code: 9499
```

The 2026-06-06 debugging found this after one wasted call.

## The setup-to-runtime handoff

After the setup script writes APP_TOKEN + TABLE_ID to `~/.hermes/.env`,
delete the test row and verify clean state:

```bash
curl -sS "https://open.feishu.cn/open-apis/bitable/v1/apps/$APP_TOKEN/tables/$TABLE_ID/records" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
items = json.load(sys.stdin).get('data', {}).get('items') or []
print(f'records in table: {len(items)} (expect 0 for clean setup)')
"
```

If non-zero, the test row was not deleted. Re-run the batch_delete
with the right body shape.

## Permission requirements

The Feishu app must have the `bitable:app:readonly` and
`bitable:app` scopes enabled in the developer console. Without these,
the token will succeed but the bitable endpoints will return 403.

If you are doing this on behalf of the user, ask them to verify the
app's scope settings in the Feishu developer console (app → 权限管理 →
Scopes) before debugging the API call.
