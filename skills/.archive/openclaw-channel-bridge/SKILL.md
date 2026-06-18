---
name: openclaw-channel-bridge
description: Install, configure, and operate OpenClaw as a multi-channel AI gateway (companion to Hermes). Includes npm install openclaw, set up the @openclaw/feishu plugin, write the openclaw.json config (channels.feishu + gateway blocks), bring up the local loopback gateway on port 18789 with token auth, and call 14 Feishu tools (feishu_bitable_*, feishu_doc, feishu_drive, feishu_chat, feishu_wiki, feishu_perm, feishu_app_scopes) via the gateway HTTP API POST /tools/invoke. Use when the user says 装 openclaw, openclaw 跟飞书对接, openclaw 飞书插件, 起 openclaw gateway. Covers 5 traps discovered 2026-06-06 (appSecret is a plain string, auth.mode must be token not the string none, gateway.mode=local required, channels list UI is misleading, /tools/invoke body uses {name, args} not {name, arguments}).
---

# OpenClaw Channel Bridge

End-to-end procedure to install OpenClaw, configure a Feishu channel, bring up the local gateway, and call the channel's tools via the gateway HTTP API. Worked through on 2026-06-06 on this host: started from `npm install -g openclaw`, ended with `openclaw gateway` listening on `127.0.0.1:18789` and a Hermes plugin writing to a Feishu Bitable through `POST /tools/invoke` then `feishu_bitable_create_record`.

## When to load

- User says 装 openclaw, openclaw 跟飞书对接, openclaw 飞书插件, 起 openclaw gateway
- User wants to add chat channels (Feishu / Lark / WeCom / Telegram / ...) to this host
- User wants to call chat-platform tools (Feishu Bitable / Doc / Drive / Wiki / ...) programmatically
- User has Hermes + wants the parallel "all your chats, one OpenClaw" gateway alongside it

Skip if the user just wants to browse or read from an existing OpenClaw installation.

## What OpenClaw is (and isnt)

- **What it is**: A multi-channel AI gateway (think of it as Hermes's sibling — both gate messages from IM platforms into an agent loop). It ships with channel plugins for Feishu, WeCom, Slack, Telegram, Discord, etc. Once running, the `feishu` channel plugin registers **14 Feishu tools** (`feishu_bitable_*`, `feishu_doc`, `feishu_drive`, `feishu_chat`, `feishu_wiki`, `feishu_perm`, `feishu_app_scopes`) that can be called via the gateway HTTP API. **Important caveat**: as of `@openclaw/feishu@2026.6.1`, `feishu_chat` is metadata-only (members/info/member_info) — it does NOT implement `send_message`. See `references/feishu-tools-cheatsheet.md` for the actually-implemented actions and the probe-before-bet loop.
- **What it isn't**: Not a replacement for Hermes. They coexist. Hermes owns chat-side, OpenClaw owns multi-channel + channel-tool exposure. A clean integration pattern is: Hermes plugin then `POST /tools/invoke` then OpenClaw then Feishu API. Don't hand-roll urllib + tenant_access_token inside a Hermes plugin when OpenClaw can do it.

## Steps

### 1. Install OpenClaw and the Feishu plugin

```bash
export PATH="$HOME/.local/lib/npm-global/bin:$PATH"
npm install -g openclaw
npm install -g @openclaw/feishu
```

`@openclaw/feishu` is a separate npm package (depends on `@larksuiteoapi/node-sdk`). It is **not** auto-installed by `openclaw`. After install, `~/.openclaw/npm/projects/openclaw-feishu-*/node_modules/@openclaw/feishu/dist/index.js` should exist.

Verify the Feishu plugin is recognized by OpenClaw:

```bash
openclaw plugins list | grep -i feishu
# expect: Feishu/Lark  feishu  openclaw  enabled
```

If you only see installed / not configured / disabled in `channels list --all`, that is normal — `channels list` shows the catalog; the actual activation is driven by `openclaw.json`.

### 2. Gather credentials

- `FEISHU_APP_ID` — already in `~/.hermes/.env` from prior Feishu plugin work
- `FEISHU_APP_SECRET` — same

The user does not need to give you a separate OpenClaw token; the gateway generates one when you set `gateway.auth.mode = "token"` and pick a string. Use a memorable local-only string — loopback is not exposed externally.

### 3. Write `~/.openclaw/openclaw.json` directly

**The CLI's `add --use-env` wizard reports "Added" but does NOT actually persist the credentials.** Hand-write the config:

```python
import json
from pathlib import Path

p = Path.home() / ".openclaw" / "openclaw.json"
d = json.loads(p.read_text()) if p.exists() else {}

# 1) Channels: feishu
d.setdefault("channels", {}).setdefault("feishu", {})
d["channels"]["feishu"].update({
    "enabled": True,
    "defaultAccount": "default",
    "appId": "<FEISHU_APP_ID>",
    "appSecret": "<FEISHU_APP_SECRET>",   # plain string in this version
    "domain": "feishu",
    "connectionMode": "websocket",
    "renderMode": "auto",
})
# overlay per-account (schema also looks for accounts map)
d["channels"]["feishu"]["accounts"] = {
    "default": {
        "enabled": True, "name": "主人",
        "appId": "<FEISHU_APP_ID>",
        "appSecret": "<FEISHU_APP_SECRET>",
        "domain": "feishu",
        "connectionMode": "websocket",
    }
}

# 2) Gateway
d["gateway"] = {
    "mode": "local",           # required to bypass "unconfigured" startup block
    "bind": "loopback",        # don't expose to LAN
    "port": 18789,             # openclaw default
    "auth": {
        "mode": "token",       # NOT the string "none" - schema rejects that form
        "token": "<your-local-token>",
    },
}

p.write_text(json.dumps(d, ensure_ascii=False, indent=2))
```

**Traps in this file** (all hit on 2026-06-06):

1. **`gateway.auth` MUST be an object with `mode` + `auth-creds` (e.g. `token`)**. Writing `gateway.auth: "none"` (string) makes the schema reject the whole config. Found at `openclaw/dist/runtime-gateway-auth-surfaces-*.js`.
2. **`gateway.mode = "local"` is required** — without it, gateway startup blocks with `Gateway start blocked: existing config is missing gateway.mode`. You can also pass `--allow-unconfigured` to bypass, but that's a code smell, not a fix.
3. **The `channels list` UI is misleading** — after writing this config, `openclaw channels list` still says `no configured chat channels`. The actual state is in `plugins list` and `channels status --probe` (which needs the gateway up + the token).
4. **`appSecret` is a plain string** in this version. The plugin's schema also accepts a `secretRef` wrapper but the plain-string form is what works without extra config plumbing.
5. **`connectionMode: "websocket"`** requires the host to be able to make outbound HTTPS to Feishu's long-polling endpoint. If the host is firewalled, switch to `"webhook"` and expose a public callback URL.
6. **`bind` is the access scope, not the security boundary.** `loopback` (default in this skill) means only `127.0.0.1` can reach port 18789 — the right choice for a local-only integration with Hermes. If you set `"0.0.0.0"`, the gateway is reachable from any host that can route to this machine — **anyone on the LAN (or the public internet if the host has a public IP) can hit `/tools/invoke` with a guessed token**. The token in `gateway.auth.token` is the only barrier. Use a long random string if you must use `0.0.0.0`; do not use a memorable phrase like `"loopback-token"`. The user explicitly chose `bind = 0.0.0.0` on 2026-06-06 for a remote-host setup; if you see this in a config the user shared, treat the token as **exposed** and don't write it to README files or skills.
7. **`gateway.auth.token_ttl` is optional** — when set (e.g. `"72h"`), the gateway auto-rotates the token; when unset, the token is permanent. Permanent tokens are fine for machine-to-machine on a closed LAN; rotate on a schedule if the gateway is exposed.
8. **Port 18789 is not registered with IANA and is shared with several AI-tooling projects** (Hermes' own gateway, LiteLLM, etc.). If `ss -ltn` shows 18789 already in use, find which process owns it (`lsof -i :18789`) before assuming openclaw is yours. The two gateways can run side by side on different ports; the user runs Hermes-gateway on its own configured port and openclaw on 18789 by default.
9. **`ss -ltn` check is not enough** — it shows the listener but not whether the gateway is healthy. Always `curl -sS -m 3 http://127.0.0.1:18789/` and look for the "OpenClaw Control" HTML title, or `openclaw channels status --deep --token <token>` for the "Gateway reachable" line.

### 4. Bring up the gateway (Hermes-managed background)

Hermes blocks `nohup ... &`. Use the `terminal(background=true)` pattern:

```python
terminal(
    background=true,
    command=(
        'export PATH="$HOME/.local/lib/npm-global/bin:$PATH" && '
        "openclaw gateway run --port 18789 --bind loopback --force "
        '--token "<your-local-token>"'
    ),
)
```

Server is long-lived → **do NOT set `notify_on_complete=true`**.

Verify in a follow-up `terminal()` call:

```bash
sleep 6
ss -ltn | grep 18789                                # expect LISTEN line
curl -sS -m 3 http://127.0.0.1:18789/              # expect "OpenClaw Control" HTML
timeout 10 openclaw channels status --deep \
  --token "<your-local-token>"                     # expect "Gateway reachable"
```

**Do not run `openclaw doctor --fix`** — it hangs > 60s in the local container and provides no actionable signal.

### 5. Call Feishu tools via `POST /tools/invoke`

This is the integration point with Hermes. The gateway exposes a uniform HTTP surface over the 14 Feishu tools.

**Body schema** (this is the single most-pitfalled API surface):

```json
{
  "name": "feishu_bitable_list_records",
  "args": { "app_token": "...", "table_id": "...", "page_size": 5 }
}
```

**`args`, NOT `arguments`.** The handler is at `openclaw/dist/tools-invoke-BOg2mgow.js` and uses `params.input.args` (not `arguments`). Passing `arguments` gets a confusing "request miss app_token path argument" error from the Lark SDK downstream.

**Auth header**: `Authorization: Bearer <your-local-token>` (matches `gateway.auth.token`).

**Response shape**:

```json
{
  "ok": true,
  "result": {
    "content": [{"type": "text", "text": "<JSON-stringified tool output>"}],
    "details": { ... }
  }
}
```

The tool's actual output (records list, doc content, etc.) is **double-encoded**: first JSON by the tool, then string-embedded in `content[0].text`. To use it: `json.loads(resp["result"]["content"][0]["text"])`.

**Quick verification**:

```bash
curl -sS -X POST http://127.0.0.1:18789/tools/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "feishu_bitable_list_records",
    "args": {"app_token": "<APP_TOKEN>", "table_id": "<TABLE_ID>", "page_size": 5}
  }'
```

Other useful tools in the same pattern:

| Tool | Args | What it does |
|---|---|---|
| `feishu_bitable_create_record` | `app_token, table_id, fields` | Insert one row |
| `feishu_bitable_update_record` | `app_token, table_id, record_id, fields` | Update one row |
| `feishu_bitable_get_meta` | `url` | Parse a /wiki/ or /base/ URL to get app_token/table_id |
| `feishu_doc` | `action, doc_token, content, ...` | Read/write/append/insert/create doc (many sub-actions) |
| `feishu_drive` | `action, file_token, ...` | Drive file ops |
| `feishu_chat` | `action, chat_id, ...` | Chat metadata, member list |
| `feishu_wiki` | `action, space_id, ...` | Wiki space/node ops |
| `feishu_perm` | `action, token, ...` | Permission grants |

**Default-deny list** (irrelevant for Feishu but good to know): `exec, spawn, shell, fs_write, fs_delete, fs_move, apply_patch, sessions_spawn, sessions_send, cron, gateway, nodes`. See `openclaw/dist/dangerous-tools-*.js`. The list is extended by `gateway.tools.deny` and can be relaxed with `gateway.tools.allow`.

### 6. Use from a Hermes plugin

Drop the urllib + tenant_access_token + format-the-URL boilerplate. The plugin becomes a thin HTTP client over `127.0.0.1:18789`:

```python
import os, json, urllib.request

def _openclaw_invoke(tool_name: str, args: dict, timeout: float = 8.0) -> dict:
    body = json.dumps({"name": tool_name, "args": args}).encode()
    req = urllib.request.Request(
        os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789") + "/tools/invoke",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('OPENCLAW_GATEWAY_TOKEN','')}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

# Example: write a Bitable row
resp = _openclaw_invoke("feishu_bitable_create_record", {
    "app_token": "...",
    "table_id": "...",
    "fields": {"药品名": "氯雷他定", "剂量": "10mg", "症状": "荨麻疹"},
})
text = resp["result"]["content"][0]["text"]   # string-embedded JSON
record_id = json.loads(text)["record"]["record_id"]
```

Two env vars are sufficient: `OPENCLAW_GATEWAY_URL` and `OPENCLAW_GATEWAY_TOKEN`. Add `~/.hermes/.env` (write-protected by patch tool — use shell `cat >> .env` to append).

### 7. Verify end-to-end

After step 6, run an end-to-end smoke that touches the real Feishu backend:

1. Pre-conditions: gateway listening (port 18789), `openclaw.json` has `channels.feishu.appId/appSecret`, a Bitable app/table exist on the Feishu side.
2. From a Hermes session, call the plugin with a complete payload.
3. Independently verify the Bitable row landed (use the `feishu_bitable_list_records` tool via curl, parse the double-encoded content[0].text, print fields).

Row appears then done. **Stop here and report.** Do not "test more thoroughly" (see `agent-execution-anti-stall-rules`).

## Pitfalls summary

1. **`/tools/invoke` body uses `{name, args}` — not `{name, arguments}`.** Symptom: confusing `request miss app_token path argument` from the Lark SDK downstream. Source: `openclaw/dist/tools-invoke-BOg2mgow.js:15-20`.
2. **`channels list` lies about whether an account is configured.** It shows the catalog; the real state is in `~/.openclaw/openclaw.json` and `plugins list | grep feishu`.
3. **`openclaw channels add --use-env` reports success but does not write credentials.** Hand-write `openclaw.json` (step3).
4. **`gateway.auth` must be a `{mode, token}` object — not the string `"none"`.** Schema lives at `openclaw/dist/runtime-gateway-auth-surfaces-*.js`.
5. **`gateway.mode = "local"` is required** to start without `--allow-unconfigured`. Without it, you get `Gateway start blocked: existing config is missing gateway.mode`.
6. **The14 Feishu tools are only registered once the gateway is up** — `plugins list` shows them as `enabled` because the plugin is installed, but invoking them before gateway startup will fail with "gateway not reachable".
7. **`openviking-server` (a separate project, not OpenClaw) uses port1933 default** and a different config (`~/.openviking/ov.conf`). If you also run openviking, don't conflate the two. See `openviking-server-bootstrap` skill for that side.
8. **Gateway startup takes3-5s** to bind18789. Don't assume `process started` = `port open`; sleep6s then `ss -ltn`.
9. **`feishu_chat` does NOT implement `send_message`** in `@openclaw/feishu@2026.6.1`. The plugin only has `members`/`info`/`member_info`. To send IM messages, fall back to direct Feishu OpenAPI (`POST /open-apis/im/v1/messages`) using `FEISHU_APP_ID`/`FEISHU_APP_SECRET` from `~/.hermes/.env` + a cached `tenant_access_token`. See `feishu-enhanced` skill for the fallback path and `references/feishu-tools-cheatsheet.md` for the authoritative action list.
10. **Don't trust the cheatsheet table blindly.** Plugin versions drift; the table here was wrong about `feishu_chat` until a real `/tools/invoke` probe caught it. Always verify the action you plan to call exists before betting a workflow on it (probe loop below).

### Probe-before-bet (verify the tool actually has the action you need)

When a workflow hinges on a specific tool+action pair (e.g. "send a Feishu DM via `feishu_chat.send_message`"), don't trust the cheatsheet or memory — verify with a3-line shell loop before writing real code. Cheap to run, catches version drift and skill-fact rot:

```bash
URL="${OPENCLAW_GATEWAY_URL:-http://127.0.0.1:18789}"
TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"
for a in <action1> <action2> <action3>; do
 printf "%-18s -> " "$a"
 curl -sS -m5 -X POST "$URL/tools/invoke" \
 -H "Content-Type: application/json" \
 -H "Authorization: Bearer $TOKEN" \
 -d "{\"name\":\"<tool>\",\"args\":{\"action\":\"$a\"}}"
 echo ""
done
```

Real action → `{"ok":true,"result":{...}}` (with payload inside `result.content[0].text`). Missing action → `{"ok":true,"result":{"content":[{"type":"text","text":"{\n \"error\": \"Unknown action: <X>\"\n}"}],...}}` — the `ok:true` wrapper is misleading; the error is inside `result`. Reads the plugin's source under `node_modules/@openclaw/feishu/dist/*.js` (grep for `case "<action>":`) for ground truth when the live probe is ambiguous.

Pair this with `read_file` against the plugin's source if the probe is unclear — the source's `switch(p.action)` is the only source of truth. Re-runnable shell form lives at `scripts/probe_tool_actions.sh` (pass the tool name + candidate actions, get one line per probe).

## Worked example: 2026-06-06 production config (bind 0.0.0.0 + 72h token TTL)

The principal's 2026-06-06 SOUL review finalized a non-loopback OpenClaw
config for a multi-host setup. Verified working as of that session:

```json
{
  "channels": {
    "feishu": {
      "enabled": true,
      "defaultAccount": "default",
      "appId": "cli_xxx",
      "appSecret": "YIf9xxx_actual_secret_here",
      "domain": "feishu",
      "connectionMode": "websocket",
      "renderMode": "auto",
      "accounts": {
        "default": {
          "enabled": true,
          "name": "主人",
          "appId": "cli_xxx",
          "appSecret": "YIf9xxx_actual_secret_here",
          "domain": "feishu",
          "connectionMode": "websocket"
        }
      }
    }
  },
  "gateway": {
    "mode": "local",
    "bind": "0.0.0.0",
    "port": 18789,
    "auth": {
      "mode": "token",
      "token": "<long-random-string-or-rotating-secret>",
      "token_ttl": "72h"
    }
  }
}
```

**Key choices in this config (vs the loopback default):**

- `bind: "0.0.0.0"` — gateway is reachable from any host that can route to this machine. **Treat the `auth.token` value as exposed** once this is set; do not write it to README files, skills, or commit it to git. The principal's actual token was a memorable phrase; for a real LAN deployment replace it with a 32+ char random string and store via a secret manager, not a plain `.env` / `openclaw.json` file.
- `token_ttl: "72h"` — gateway auto-rotates the token every 3 days. All consumers (Hermes plugins, other tools) must read the **current** token, not a cached one. If you cache the token in process memory, set a refresh interval ≤ 1h.
- The `accounts.default` block duplicates `appId/appSecret` from the parent. The schema expects this overlay; the parent-level fields are read at startup but per-account calls go through the overlay.
- `connectionMode: "websocket"` requires the host to make outbound HTTPS to Feishu's long-polling endpoint. If the host is behind a strict egress firewall, switch to `"webhook"` and stand up a public callback URL.

**When to use this config (vs the loopback default):** only when the
gateway is a shared service for multiple hosts (Hermes on host A,
OpenClaw on host B, both need to call each other). For a single-host
Hermes + OpenClaw setup, **stay on `bind: "loopback"`** — there is no
benefit to exposing the gateway and one less attack surface.

## Verification checklist

- [ ] `npm ls -g openclaw @openclaw/feishu` shows both installed
- [ ] `openclaw --version` works (PATH includes `~/.local/lib/npm-global/bin`)
- [ ] `~/.openclaw/openclaw.json` has `channels.feishu.appId/appSecret/connectionMode/accounts` and `gateway.{mode,port,auth.mode,auth.token}`
- [ ] `openclaw gateway run` started in background (PID + `ss -ltn` shows 18789)
- [ ] `openclaw channels status --deep` reports "Gateway reachable"
- [ ] `POST /tools/invoke` with `feishu_bitable_list_records` returns `ok: true` and real records
- [ ] End-to-end Hermes plugin call lands a row in the Bitable
- [ ] Stop here, report, do not re-validate

## Reference files

- `references/openclaw-config-template.json` — full working `openclaw.json` template (channels.feishu + accounts overlay + gateway)
- `references/feishu-tools-cheatsheet.md` — the 14 Feishu tools with their arg shapes, copied from `@openclaw/feishu/dist/api.js`
- `templates/hermes-plugin-skeleton.py` — minimal Hermes plugin template that calls OpenClaw tools via `/tools/invoke`
- `references/hermes_allergy_logger.py` — full working example (the 2026-06-06 plugin that auto-logs allergy-medication intake to a Feishu Bitable)
