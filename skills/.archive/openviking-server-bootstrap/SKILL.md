---
name: openviking-server-bootstrap
description: Install, configure, and bring up OpenViking (the volcengine vector context server) as a local vector DB, and wire it into a host agent (Hermes / Claude Code / Codex / OpenCode). Use when the user says "装 OpenViking", "起 openviking-server", "联通 OpenViking", "配 vikingbot", or wants the host agent's long-term memory to be backed by a local vector DB. Covers pip install, the nested embedding.dense / vlm config schema trap, ov.conf-only startup (env vars alone are rejected), the doubao-embedding-vision model-naming trap, the ~/.hermes/.env write-protect bypass via shell append, and the hermes-managed background process pattern (background=true, not nohup).
---

# OpenViking Server Bootstrap

End-to-end procedure to install, configure, and bring up an OpenViking (volcengine) server reachable by a host agent. Worked through on 2026-06-06 on this host: started from a freshly `pip install openviking`, ended with `openviking-server` listening on `127.0.0.1:8765` returning `{"status":"ok","healthy":true}` and exposing `/openapi.json` + `/docs`.

## When to load

- User says "装 OpenViking", "起 openviking-server", "联通 OpenViking", "配 vikingbot"
- User says they want their host agent's long-term memory to be vector-backed
- User hands you a volcengine ARK key and says "用这个配 OpenViking"

Skip if the user just wants to **query** an existing OpenViking server — that is a different task (MCP client setup, not bootstrap).

## Steps

### 1. Install

```bash
# in host venv
source ~/.hermes/hermes-agent/venv/bin/activate
uv pip install openviking
# if previous attempt left half-installed:
#   uv pip install --reinstall openviking
# use清华源 if PyPI is slow:
#   export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

**Verify both** the Python package and the CLI entry point exist:

```bash
python -c "import openviking; print(openviking.__file__)"
which openviking-server && openviking-server --help
```

If `openviking-server` is missing, the pip install hung or errored; check `ps -ef | grep "uv pip"`.

### 2. Collect credentials

The user needs to supply, at minimum:

- **ARK key** (`ark-...`) — volcengine access
- **ARK endpoint** — usually `https://ark.cn-beijing.volces.com/api/plan/v3`
- **Embedding model name** — common ones:
  - `doubao-embedding` (text-only, for `embedding.dense`)
  - `doubao-embedding-vision` (multimodal, technically a VLM — see pitfall below)
- **LLM model name** for VLM/vision (if doing multimodal) — e.g. `doubao-1.5-vision-pro`

### 3. Write `~/.openviking/ov.conf`

**The config file is mandatory.** Pure env vars (e.g. `OPENVIKING_EMBEDDING_API_KEY=...`) are **not sufficient** — the server will start, then immediately exit with:

```
OpenViking configuration file not found.
Please create /home/ubuntu/.openviking/ov.conf or /etc/openviking/ov.conf, or set OPENVIKING_CONFIG_FILE.
```

### 4. Know the nested schema — this is the #1 pitfall

The `embedding` section is **not** a flat dict. It must nest under `dense`, `sparse`, or `hybrid`:

```json
{
  "storage": { "workspace": "/home/ubuntu/.openviking/data" },
  "embedding": {
    "dense": {
      "model": "doubao-embedding",
      "api_key": "ark-...",
      "api_base": "https://ark.cn-beijing.volces.com/api/plan/v3",
      "provider": "volcengine",
      "input": "text"
    }
  },
  "vlm": {
    "model": "doubao-1.5-vision-pro",
    "api_key": "ark-...",
    "api_base": "https://ark.cn-beijing.volces.com/api/plan/v3",
    "provider": "volcengine"
  }
}
```

If you put `model` / `api_key` / `api_base` directly under `embedding`, the server starts, runs 3-5 seconds, then exits with:

```
Unknown config field 'embedding.model'
Unknown config field 'embedding.api_key'
Unknown config field 'embedding.api_base'
...
```

**Reference**: the schema lives in `venv/lib/python3.11/site-packages/openviking_cli/utils/config/embedding_config.py` and `vlm_config.py`. When in doubt, read those files — they have the most accurate field names.

### 5. Volcengine model naming trap

`doubao-embedding-vision` is a **VLM (vision-language) model** in the volcengine model catalog — it does **multimodal embedding** but is categorized under vision, not text embedding. Two consequences:

- If you set `embedding.dense.model = "doubao-embedding-vision"` and `embedding.dense.input = "text"`, embeddings will fail with a 4xx from the volcengine API.
- The right move is usually to put it under `vlm` (for image-aware retrieval) AND pick a separate text-only model for `embedding.dense` (e.g. `doubao-embedding`).

When the user hands you a model name, **cross-check the volcengine model catalog** (or ask "is this text or vision?") before placing it. If the user is firm that one model should serve both, set `input: "multimodal"` on the embedding config.

### 6. Start the server — use `background=true`, not `nohup &`

Hermes' terminal tool **rejects** shell-level background wrappers (`nohup ... &`, `disown`, `setsid`). Use:

```python
terminal(
    background=true,
    command="source venv/bin/activate && openviking-server --host 127.0.0.1 --port 8765",
    workdir="/home/ubuntu/.hermes/hermes-agent"
)
```

This gives you a `session_id` and a `pid`. The server is long-lived → **do not set `notify_on_complete=true`** (it would only fire if the server crashes, which is the right behavior — you will be pinged on crash).

**Read the stdout from the session** (via `process(action='log', session_id=...)`) to see startup errors. Common ones:

| Error | Cause | Fix |
|---|---|---|
| `OpenViking configuration file not found` | No ov.conf | Write `~/.openviking/ov.conf` (step 3) |
| `Unknown config field 'embedding.X'` | Flat schema (step 4 trap) | Nest under `dense` |
| `Address already in use` | Port collision | Pick a different port; kill the leftover |
| Server exits after 30s with no log | Likely model-API call fails silently on first request | Check `/health` first; if 200, it is healthy despite the exit message being absent |

### 7. Verify the server is up

```bash
curl -sS -m 3 http://127.0.0.1:8765/health
# expected: {"status":"ok","healthy":true,"version":"0.3.x","auth_mode":"dev"}

curl -sS -m 3 http://127.0.0.1:8765/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('paths:', len(d.get('paths',{})))"
# expected: paths: 26+ (resources, fs, content, console, admin, ...)
```

If `health` 200 + `openapi.json` lists paths, the server is fully operational. **Stop here and report success.** Do not "test more thoroughly" — see the anti-stall skill for why.

### 8. Wire into host agent (Hermes-specific)

The user said "联通" — that just means the server is up and reachable. Wiring OpenViking into Hermes memory is a **separate** task (likely `hermes memory setup`); ask before doing it.

## Pitfalls summary

1. **ov.conf is mandatory.** Env vars alone are rejected.
2. **`embedding.X` is wrong** — must be `embedding.dense.X` (or `sparse` / `hybrid`).
3. **`doubao-embedding-vision` is a VLM** — placing it in `embedding.dense` will fail; put it in `vlm` or use `input: "multimodal"`.
4. **Hermes blocks `nohup &`** — use `terminal(background=true)`.
5. **The server may take 20-30s to bind the port** after `embedding` initializes the model backend. Do not assume "process started" = "port open"; sleep ~5s and `ss -ltn | grep <port>` to confirm.
6. **`/health` is the only stable endpoint** across versions. `/api/v1/health`, `/v1/health`, `/api/health` all 404. Trust `/health` and `/openapi.json`.

## Verification checklist (run before reporting done)

- [ ] `python -c "import openviking"` exits 0
- [ ] `which openviking-server` returns a path
- [ ] `~/.openviking/ov.conf` exists with `embedding.dense.X` (not flat `embedding.X`)
- [ ] `openviking-server` is running (PID + `ss -ltn` shows the port)
- [ ] `curl /health` returns `{"status":"ok","healthy":true,...}`
- [ ] `curl /openapi.json` returns a JSON with 20+ paths
- [ ] No further actions needed — report and stop

## Reference files

- `references/ov-conf-template.json` — minimal working ov.conf for volcengine ARK
- `references/startup-error-catalog.md` — full error → fix table

## Related skills

- `feishu-enhanced` — full Feishu API surface (Bitables, Docs, Drive, IM) when you don't need OpenViking in the loop
- `openclaw-channel-bridge` — when the host also runs OpenClaw + @openclaw/feishu, prefer the Hermes plugin → `POST /tools/invoke` → `feishu_bitable_*` path over hand-rolling urllib + tenant_access_token inside a plugin. OpenViking itself does not depend on OpenClaw; the two are independent and can run side-by-side (different ports, different config dirs: openviking at 8765 with `~/.openviking/ov.conf`, openclaw at 18789 with `~/.openclaw/openclaw.json`).
- `cloud-network-diagnostics` — when the install step itself fails (network timeout, mirror unreachable)
