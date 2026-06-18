# Install a new MCP server end-to-end

> **Note:** This is the full step-by-step recipe originally published as the
> standalone `install-mcp-server` skill (Hermes v0.15.1, `mcp_servers` schema).
> It has been absorbed into the `auxiliary-model-routing` umbrella under
> § "Install a new MCP server end-to-end" in `SKILL.md`. Load `SKILL.md` for
> the surrounding config and verification recipe; load this file when you are
> specifically installing a new server and need the 8-pitfall checklist.

## Overview

The full workflow for installing and configuring a stdio or HTTP MCP server
in Hermes, including all 8 known pitfalls. Verified against
`minimax-coding-plan-mcp` on 2026-06-04.

## 1. Pull the official docs first

**Always** start with the source of truth:
- The MCP server's own README / official docs (GitHub / npm / PyPI / vendor site)
- Look for `mcpServers` config example, `env` variable names, `command` + `args` template

**Required reading for Hermes specifically** (canonical references):
- `mcp-config-reference.md` (the schema)
- `use-mcp-with-hermes.md` (stdio mode example)
- `user-guide/features/mcp.md` L145 `${VAR}` substitution + L232 30s auto-reload window

## 2. Install the package into a venv (not `/tmp`, not uv's default mirror)

### Pitfall 1: uv install times out from China-region servers
`uv pip install` walks `https://pypi.org/simple`, which frequently 60s+ timeouts
from Chinese cloud servers. **Fix**: use `pip` against `mirrors.tencentyun.com`:

```bash
# Check pip mirror config
grep index-url /etc/pip.conf   # usually already mirrors.tencentyun.com

# Install into a venv
uv venv ~/.hermes/mcp/<server-name>/venv
# Note: uv venv doesn't ship with pip, use uv pip install
uv pip install --python ~/.hermes/mcp/<server-name>/venv/bin/python \
  --index-url http://mirrors.tencentyun.com/pypi/simple \
  <server-package>

# Or use pip
~/.hermes/mcp/<server-name>/venv/bin/python -m ensurepip
~/.hermes/mcp/<server-name>/venv/bin/python -m pip install <server-package>
```

### Pitfall 2: `/tmp` installs vanish on restart
**Always** install into `~/.hermes/mcp/<server-name>/`. Never `/tmp`.

### Pitfall 3: `pip install --target /some/path` makes the package invisible to the server
`pip install --target /some/path` followed by a server with `#!/usr/bin/python3`
in its shebang means the **system** Python (which the shebang points at) does
not include `/some/path` in `sys.path`. **Fix**: install into a venv, and use
the venv's python in a wrapper:

```bash
#!/bin/bash
exec /home/ubuntu/.hermes/mcp/<name>/venv/bin/python -c \
  "from <package>.server import main; main()" "$@"
```

## 3. Write a wrapper script

```bash
#!/bin/bash
# Use absolute paths only
exec /home/ubuntu/.hermes/mcp/<name>/venv/bin/python -c \
  "from <package>.server import main; main()" "$@"
```
`chmod +x` it, then **test it once** (no output = server is correctly waiting
on stdin for JSON-RPC).

## 4. Configure the `mcp_servers` block

### Pitfall 4: `hermes mcp add` triggers a 30s auto-reload window
**user-guide/features/mcp.md L232** is explicit: in a running Hermes session,
running `hermes mcp add` starts a 30s connection window — first-time package
install + server start often exceeds it. **Fix**: use
`hermes config set mcp_servers.<name>.<key> <value>` to set individual fields
manually, **not** `mcp add`. Or do `hermes mcp add` (saves disabled) + then
`hermes config set` to tune.

### Pitfall 4a: `hermes mcp add` CLI has its own limits
- `--preset` **only** supports `codex` in v0.15.1, not MiniMax or third-party.
- `--args` **does not** support leading flags like `-y` (npx style); reports
  `unrecognized arguments: -y`. `uvx` invoking `minimax-coding-plan-mcp` does
  **not** need `-y` — drop it.
- `--env KEY=VALUE` is expanded literally — it does **not** go through `${VAR}`
  substitution. To keep yaml clean, use
  `hermes config set mcp_servers.<name>.env.KEY ${KEY}` (the innermost
  all-uppercase env key is broken in `config set`; see pitfall 6).
- Connection-test timeouts do not auto-retry. If the test fails, the server is
  `disabled`. After fixing wrapper / venv, manually `hermes mcp test <name>`.
- Verified: `hermes mcp add MiniMax --command uvx --args minimax-coding-plan-mcp --env ...`
  triggers a 41s timeout (install + server-start exceeds the 30s window).
  Switching to `hermes config set` + manual yaml edits does **not** time out.

### Pitfall 5: stdio does not inherit shell env
`mcp_servers.<name>.env` is the **only** env passed to a stdio server. The
parent shell's env is **not** inherited. **Use `${VAR}` references** —
`~/.hermes/.env`'s `MINIMAX_API_KEY` is auto-resolved
(see `user-guide/features/mcp.md` L145).

### Pitfall 6: all-uppercase dotted keys fail `hermes config set`
`hermes config set mcp_servers.<name>.env.MINIMAX_API_KEY 'value'` raises:
```
ValueError: Invalid environment variable name: 'MCP_SERVERS.MINIMAX.ENV.MINIMAX_API_KEY'
```
**Workarounds**:
- For the outer key path, `hermes config set mcp_servers.<name>.command ...` works
- For the innermost env key value, `sed` the yaml directly (don't go through
  Hermes CLI for that field)

### Full yaml template
```yaml
mcp_servers:
  <name>:
    command: /home/ubuntu/.hermes/mcp/<name>/run-server.sh
    connect_timeout: 120    # default 60s; first-time install+start often needs more
    timeout: 60
    enabled: true
    env:
      API_KEY: ${API_KEY}        # ← resolves from ~/.hermes/.env
      API_HOST: ${API_HOST}
    tools:                       # optional whitelist
      include: [tool_a, tool_b]  # rate-limit + prevent surprise billable calls
      resources: false
      prompts: false
```

## 5. Verification (all 4 steps must pass)

```bash
# ① config parses
hermes config check       # must pass; config version 24+

# ② server appears in the list
hermes mcp list            # should show ✓ enabled

# ③ connection test
hermes mcp test <name>     # "Connected (<ms>ms)" + "Tools discovered: N"

# ④ end-to-end real call (CRITICAL — bypass the hermes CLI, hit JSON-RPC stdio directly)
```
```python
# scripts/test_mcp_stdio.py — copy + adapt the path; works for any stdio server
import json, subprocess, os, time, fcntl, sys

# 1) Build env (MUST be explicit — stdio does not inherit parent env)
env = os.environ.copy()
env['API_KEY'] = 'your-key-here'
env['API_HOST'] = 'https://api.example.com'

# 2) JSON-RPC: initialize → notifications/initialized → tools/list → tools/call
msgs = [
    {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2024-11-05","capabilities":{},
        "clientInfo":{"name":"test","version":"1.0"}
    }},
    {"jsonrpc":"2.0","method":"notifications/initialized"},
    {"jsonrpc":"2.0","id":2,"method":"tools/list"},
    {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{
        "name":"main_tool","arguments":{...}
    }}
]
input_bytes = '\n'.join(json.dumps(m) for m in msgs).encode() + b'\n'

# 3) Spawn the server subprocess
proc = subprocess.Popen(
    ['/home/ubuntu/.hermes/mcp/<name>/run-server.sh'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env=env, bufsize=0
)

# 4) Non-blocking fd read (fastmcp is async; subprocess.communicate() loses slow responses)
fd = proc.stdout.fileno()
flags = fcntl.fcntl(fd, fcntl.F_GETFL)
fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
proc.stdin.write(input_bytes); proc.stdin.close()

# 5) Poll: collect 3 responses (id 1+2+3), or break after 3-5s of no new data
all_out = b''
deadline = time.time() + 30
last_data = time.time()
while time.time() < deadline:
    time.sleep(0.2)
    try:
        c = proc.stdout.read(65536)
        if c: all_out += c; last_data = time.time()
    except (BlockingIOError, IOError):
        pass
    if all_out.decode('utf-8', errors='replace').count('"jsonrpc"') >= 3:
        time.sleep(1.5)  # let web_search finish
    if time.time() - last_data > 4 and all_out: break

proc.kill()
try: proc.wait(timeout=2)
except: pass

# 6) Parse
for line in all_out.decode('utf-8', errors='replace').strip().split('\n'):
    try:
        d = json.loads(line)
        if d.get('id') == 3:
            text = d.get('result', {}).get('content', [{}])[0].get('text', '')
            inner = json.loads(text)  # inner JSON payload
            print(json.dumps(inner, ensure_ascii=False, indent=2))
    except: pass
```

**Key pitfalls** (verified 2026-06-04 on `minimax-coding-plan-mcp`):
- `subprocess.communicate()` **drops** slow responses like `web_search` —
  the server is async and the process exit flush is incomplete. **Must** use
  non-blocking fd polling.
- Seeing `"jsonrpc"` 3 times = 3 responses (initialize / tools/list / tools/call),
  **not** 1 response.
- Add `time.sleep(1.5)` after the 3rd response so `web_search` has time to
  actually return (fastmcp is async; the response may arrive in batches).

## 6. Known MCP servers (verified)

| Server | Endpoint / transport | Status |
|---|---|---|
| `MiniMax` (`minimax-coding-plan-mcp`) | stdio + `POST https://api.minimaxi.com/v1/coding_plan/search` | ✅ configured, real-call verified |

## 7. Security / persistence

- venv + wrapper live in `~/.hermes/mcp/<name>/` (never `/tmp`)
- Credentials in `~/.hermes/.env` (chmod 600), not inlined into yaml
- yaml uses `${VAR}` references; auto-resolved at load
- `tools.include` whitelist limits exposed tools (prevents surprise billable
  tools from being called by the LLM)

## 8. Debugging quick-reference

| Symptom | Root cause | Fix |
|---|---|---|
| `Connection closed` < 10s | Server crashed on startup (pkg missing / env var missing) | Read stderr; run venv python directly to see the traceback |
| `Connection timed out` 30s+ | Install slow (uv default mirror timeout) | Switch pip to a Tencent mirror |
| `hermes mcp test` lists no tools | Server started but didn't expose schema | Check source for `@mcp.tool()` decorator; `hermes mcp test`'s stdout should list tool names |
| `tools/call` arrives but content empty | Server is async; `subprocess.communicate()` doesn't flush | Use non-blocking fd read + polling |
| Server receives `None` for env | stdio does not inherit parent env | Set `mcp_servers.<name>.env` explicitly + use `${VAR}` references |

## Cross-references
- `references/mcp-failure-modes.md` (in this umbrella) — full diagnosis
  catalog for `Connection closed`, the 30s auto-reload race, and the
  `hermes config set mcp_servers.<X>.env.<Y>` bug
- `references/discipline-lesson.md` (in this umbrella) — the
  "don't declare 'it works' until you've seen real tool output" rule, which
  the verification step here enforces
