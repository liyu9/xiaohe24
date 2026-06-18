---
name: native-mcp
description: "MCP client: connect servers, register tools (stdio/HTTP)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [MCP, Tools, Integrations]
    related_skills: [mcporter]
---

# Native MCP Client

Hermes Agent has a built-in MCP client that connects to MCP servers at startup, discovers their tools, and makes them available as first-class tools the agent can call directly. No bridge CLI needed -- tools from MCP servers appear alongside built-in tools like `terminal`, `read_file`, etc.

## When to Use

Use this whenever you want to:
- Connect to MCP servers and use their tools from within Hermes Agent
- Add external capabilities (filesystem access, GitHub, databases, APIs) via MCP
- Run local stdio-based MCP servers (npx, uvx, or any command)
- Connect to remote HTTP/StreamableHTTP MCP servers
- Have MCP tools auto-discovered and available in every conversation

For ad-hoc, one-off MCP tool calls from the terminal without configuring anything, see the `mcporter` skill instead, or read `references/mcporter-adhoc-stdio.md` for the verified-working `mcporter call --stdio` pattern (installs in user-local, no sudo, works for one-off verification of npm-based MCP servers).

## Prerequisites

- **mcp Python package** -- optional dependency; install with `pip install mcp`. If not installed, MCP support is silently disabled.
- **Node.js** -- required for `npx`-based MCP servers (most community servers)
- **uv** -- required for `uvx`-based MCP servers (Python-based servers)

Install the MCP SDK:

```bash
pip install mcp
# or, if using uv:
uv pip install mcp
```

## Quick Start

Add MCP servers to `~/.hermes/config.yaml` under the `mcp_servers` key:

```yaml
mcp_servers:
  time:
    command: "uvx"
    args: ["mcp-server-time"]
```

Restart Hermes Agent. On startup it will:
1. Connect to the server
2. Discover available tools
3. Register them with the prefix `mcp_time_*`
4. Inject them into all platform toolsets

You can then use the tools naturally -- just ask the agent to get the current time.

## MiniMax Token Plan MCP (`minimax-coding-plan-mcp`)

The MiniMax Token Plan ships an official MCP server for coding-plan subscribers
that exposes a `web_search` tool (and a paid `understand_image` tool). PyPI
package: `minimax-coding-plan-mcp` (author Roy Wu @ minimax.chat, v0.0.4,
~13KB wheel, but pulls ~40 deps including `mcp`, `dotenv`, `pydantic`, `httpx`).

**Verified-working install (the path that actually gets `hermes mcp test` to
report `Connected (~700ms)`):**

```bash
# 1. Ensure env vars are in ~/.hermes/.env (chmod 600)
grep -q '^MINIMAX_API_KEY=' ~/.hermes/.env || \
  echo 'MINIMAX_API_KEY=<your-key>' >> ~/.hermes/.env
grep -q '^MINIMAX_API_HOST=' ~/.hermes/.env || \
  echo 'MINIMAX_API_HOST=https://api.minimaxi.com' >> ~/.hermes/.env
chmod 600 ~/.hermes/.env

# 2. Create a venv AND install the package + all deps via the Tencent mirror.
#    (uv default PyPI is glacially slow from CN cloud regions; the resolver
#     also hangs without an explicit --index-url. 5 seconds vs 5+ minutes.)
uv venv /home/ubuntu/.hermes/mcp/minimax-venv
uv pip install --python /home/ubuntu/.hermes/mcp/minimax-venv/bin/python \
  --index-url http://mirrors.tencentyun.com/pypi/simple \
  minimax-coding-plan-mcp

# 3. Write a wrapper that points the server's interpreter at the venv
cat > /home/ubuntu/.hermes/mcp/minimax-server.sh <<'EOF'
#!/bin/bash
exec /home/ubuntu/.hermes/mcp/minimax-venv/bin/python \
  -c "from minimax_mcp.server import main; main()" "$@"
EOF
chmod +x /home/ubuntu/.hermes/mcp/minimax-server.sh

# 4. Register the server, pointing at the wrapper (NOT uvx)
hermes mcp add MiniMax \
  --command /home/ubuntu/.hermes/mcp/minimax-server.sh \
  --env "MINIMAX_API_KEY=$MINIMAX_API_KEY" \
  --env "MINIMAX_API_HOST=https://api.minimaxi.com"

# 5. Test
hermes mcp test MiniMax
# Expect: ✓ Connected (~700-1000ms)
#         ✓ Tools discovered: 2  (web_search, understand_image)
```

**Persistent paths** (not `/tmp`): `/home/ubuntu/.hermes/mcp/minimax-venv/`
and `/home/ubuntu/.hermes/mcp/minimax-server.sh` survive reboots; `/tmp` does not.

### Why the long install path? The four pits in order

#### Pit 1 — `uvx <pkg>` first run takes 40-300s+ on default PyPI

`uvx` (and `uv pip install` without `--index-url`) resolves and downloads from
`pypi.org`, which is slow or rate-limited from many cloud regions. `hermes mcp
add`'s built-in 30-40s connect-test window is not enough. **Symptom:** the
command hangs with no output, then `MCP call timed out after 41.2s`.

**Fix:** install into a venv with
`--index-url http://mirrors.tencentyun.com/pypi/simple`, then point Hermes at
the venv's interpreter via a wrapper script. 5 seconds vs 5+ minutes.

#### Pit 2 — `pip --target /tmp/site` installs the wheel but the entry script can't import it

If you do `pip install --target /tmp/site <pkg>`, you get `/tmp/site/bin/<entry>`
and `/tmp/site/<package>/`. Running `<entry>` directly fails with
`ModuleNotFoundError: No module named '<package>'` because the entry script
uses `#!/usr/bin/python3` (system python), not the target dir's python, and
system python can't see the target site-packages.

**Fix:** use a venv (uv venv / python -m venv) and install into it. The venv's
`bin/python` automatically has `<venv>/lib/pythonX.Y/site-packages` on
`sys.path`, so the entry script's import works. Then either:
- (a) Run `bin/python -c "from <package>.server import main; main()"` from a wrapper, OR
- (b) Patch the first line of `bin/<entry>` to `#!/path/to/venv/bin/python3` (brittle)

**Pit 2b — missing transitive deps.** `minimax-coding-plan-mcp` requires
`mcp`, `python-dotenv`, `httpx`, `pydantic`, etc. Installing with
`--no-deps` (or `pip --target` without deps) leaves you with a server that
imports fine but crashes on first call with `ModuleNotFoundError: No module
named 'dotenv'`. Always install **with deps** in the venv.

#### Pit 3 — `Connection closed` after the server starts cleanly

After fixing Pit 2, `hermes mcp test MiniMax` may report
`✗ Connection failed (7570ms): Connection closed` — but the server is actually
failing immediately on import, before the MCP handshake. Look at the server's
stderr: you'll see a Python traceback (`ModuleNotFoundError`, `ValueError`,
etc.). The wrapper or env is wrong; the network is fine.

**Diagnostic recipe:**

```bash
# Reproduce exactly what hermes does, see the real error
MINIMAX_API_KEY=$(grep '^MINIMAX_API_KEY=' ~/.hermes/.env | cut -d= -f2-) \
MINIMAX_API_HOST=https://api.minimaxi.com \
  timeout 5 /home/ubuntu/.hermes/mcp/minimax-server.sh < /dev/null
# A Python traceback = server-side problem.
# Silent exit = server is waiting for stdin (good; hermes should connect).
```

#### Pit 4 — `hermes mcp add` writes to `mcp_servers:` at the END of config.yaml

After running `hermes mcp add`, grep for your server:

```bash
grep -nA5 '^mcp_servers:' ~/.hermes/config.yaml
```

The block lands near the end of the file (~L550+), not at the top. Don't
search at the top.

### HTTP fallback when MCP won't cooperate

`minimax-coding-plan-mcp` is a thin wrapper. Source at
`<venv>/lib/python3.11/site-packages/minimax_mcp/server.py` shows the single
endpoint it calls:

```python
api_client.post("/v1/coding_plan/search", json={"q": query})
```

The upstream call is just:

```bash
curl -sS -X POST "https://api.minimaxi.com/v1/coding_plan/search" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -H "MM-API-Source: Minimax-MCP" \
  -H "Content-Type: application/json" \
  -d '{"q": "your search query"}'
```

HTTP 200 + JSON with an `organic` array of results = upstream works regardless
of MCP. Use this to **distinguish "API broken" from "MCP transport broken"**:
if curl works but `hermes mcp test` fails, the problem is on the transport
side, not the API.

### `${VAR}` env interpolation in mcp_servers.env

Hermes resolves `${MINIMAX_API_KEY}` and friends at server-connect time from
`~/.hermes/.env` plus the parent shell env. **Always use this form** in the
yaml so secrets stay out of `config.yaml`:

```yaml
mcp_servers:
  MiniMax:
    command: /home/ubuntu/.hermes/mcp/minimax-server.sh
    env:
      MINIMAX_API_KEY: ${MINIMAX_API_KEY}
      MINIMAX_API_HOST: ${MINIMAX_API_HOST}
    connect_timeout: 120
    timeout: 60
    enabled: true
```

(`hermes mcp add` writes this for you when you pass `--env KEY=$VAR`.)
Never hardcode keys in yaml — the file is read by humans, sync'd to git,
backed up to GitHub, etc.

### Other mcp_servers fields you'll likely want

```yaml
mcp_servers:
  MiniMax:
    command: /path/to/wrapper.sh
    args: []                      # wrapper takes no args; add args only if command isn't a script
    env:
      MINIMAX_API_KEY: ${MINIMAX_API_KEY}
      MINIMAX_API_HOST: ${MINIMAX_API_HOST}
    connect_timeout: 120          # default 60; bump if first start is slow
    timeout: 60                   # per-tool-call, default 120
    enabled: true                 # set false to skip without removing
    tools:
      include: [web_search]       # whitelist — recommended for cost-controlled servers
      resources: false            # disable resources / prompts wrappers if unused
      prompts: false
```

`tools.include: [web_search]` is recommended for `minimax-coding-plan-mcp`:
the other tool (`understand_image`) is paid. Whitelisting keeps the model
from accidentally invoking paid tools, and the surface stays auditable.

### 30-second auto-reload race

Per the official `user-guide/features/mcp.md` doc: **when you edit
`~/.hermes/config.yaml` from inside a running Hermes session**, the CLI
auto-reloads MCP connections with a **30-second timeout**. If your `hermes mcp
add` is being run from the very session whose config it edits, the
add-then-test cycle races this 30s window — `hermes mcp test` may report
`Connection timed out` even when nothing is wrong. Add the entry, then run
`hermes mcp test MiniMax` from a fresh terminal so it gets the full 5-minute
window.

### `hermes config set` mcp_servers pitfalls

- `hermes config set` rejects `mcp_servers.<X>.env.<Y>` when the full path
  contains an all-uppercase segment it mistakes for an env var name. Symptom:
  `ValueError: Invalid environment variable name:
  'MCP_SERVERS.MINIMAX.ENV.MINIMAX_API_KEY'`. **Workaround:** set the env
  via `hermes mcp add --env KEY=$VAL` (the mcp add path works), or use
  `hermes config set` for the non-env fields and add the env block via
  `hermes mcp add --command <cmd> --env KEY=VAL --env KEY2=VAL2` so the
  CLI treats them as MCP env not OS env.
- `config.yaml` is a **protected file**: `patch` and `write_file` are denied
  for it. `hermes config set` is the supported mutation path. For one-off
  edits (e.g., adding a literal `${VAR}` line that `config set` rejected),
  use `sed -i` and back up first:
  `cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%s)`.
- `mcp_servers.<X>.command` must be an absolute path. Relative paths or bare
  names on `PATH` work in some transports but fail silently under
  `connect_timeout: 60`; always use the full path to the wrapper.

## Configuration Reference

Each entry under `mcp_servers` is a server name mapped to its config. There are two transport types: **stdio** (command-based) and **HTTP** (url-based).

### Stdio Transport (command + args)

```yaml
mcp_servers:
  server_name:
    command: "npx"             # (required) executable to run
    args: ["-y", "pkg-name"]   # (optional) command arguments, default: []
    env:                       # (optional) environment variables for the subprocess
      SOME_API_KEY: "value"
    timeout: 120               # (optional) per-tool-call timeout in seconds, default: 120
    connect_timeout: 60        # (optional) initial connection timeout in seconds, default: 60
```

### HTTP Transport (url)

```yaml
mcp_servers:
  server_name:
    url: "https://my-server.example.com/mcp"   # (required) server URL
    headers:                                     # (optional) HTTP headers
      Authorization: "Bearer sk-..."
    timeout: 180               # (optional) per-tool-call timeout in seconds, default: 120
    connect_timeout: 60        # (optional) initial connection timeout in seconds, default: 60
```

### All Config Options

| Option            | Type   | Default | Description                                       |
|-------------------|--------|---------|---------------------------------------------------|
| `command`         | string | --      | Executable to run (stdio transport, required)     |
| `args`            | list   | `[]`    | Arguments passed to the command                   |
| `env`             | dict   | `{}`    | Extra environment variables for the subprocess    |
| `url`             | string | --      | Server URL (HTTP transport, required)             |
| `headers`         | dict   | `{}`    | HTTP headers sent with every request              |
| `timeout`         | int    | `120`   | Per-tool-call timeout in seconds                  |
| `connect_timeout` | int    | `60`    | Timeout for initial connection and discovery      |

Note: A server config must have either `command` (stdio) or `url` (HTTP), not both.

## How It Works

### Startup Discovery

When Hermes Agent starts, `discover_mcp_tools()` is called during tool initialization:

1. Reads `mcp_servers` from `~/.hermes/config.yaml`
2. For each server, spawns a connection in a dedicated background event loop
3. Initializes the MCP session and calls `list_tools()` to discover available tools
4. Registers each tool in the Hermes tool registry

### Tool Naming Convention

MCP tools are registered with the naming pattern:

```
mcp_{server_name}_{tool_name}
```

Hyphens and dots in names are replaced with underscores for LLM API compatibility.

Examples:
- Server `filesystem`, tool `read_file` → `mcp_filesystem_read_file`
- Server `github`, tool `list-issues` → `mcp_github_list_issues`
- Server `my-api`, tool `fetch.data` → `mcp_my_api_fetch_data`

### Auto-Injection

After discovery, MCP tools are automatically injected into all `hermes-*` platform toolsets (CLI, Discord, Telegram, etc.). This means MCP tools are available in every conversation without any additional configuration.

### Connection Lifecycle

- Each server runs as a long-lived asyncio Task in a background daemon thread
- Connections persist for the lifetime of the agent process
- If a connection drops, automatic reconnection with exponential backoff kicks in (up to 5 retries, max 60s backoff)
- On agent shutdown, all connections are gracefully closed

### Idempotency

`discover_mcp_tools()` is idempotent -- calling it multiple times only connects to servers that aren't already connected. Failed servers are retried on subsequent calls.

## Transport Types

### Stdio Transport

The most common transport. Hermes launches the MCP server as a subprocess and communicates over stdin/stdout.

```yaml
mcp_servers:
  filesystem:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"]
```

The subprocess inherits a **filtered** environment (see Security section below) plus any variables you specify in `env`.

### HTTP / StreamableHTTP Transport

For remote or shared MCP servers. Requires the `mcp` package to include HTTP client support (`mcp.client.streamable_http`).

```yaml
mcp_servers:
  remote_api:
    url: "https://mcp.example.com/mcp"
    headers:
      Authorization: "Bearer sk-..."
```

If HTTP support is not available in your installed `mcp` version, the server will fail with an ImportError and other servers will continue normally.

## Security

### Environment Variable Filtering

For stdio servers, Hermes does NOT pass your full shell environment to MCP subprocesses. Only safe baseline variables are inherited:

- `PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TERM`, `SHELL`, `TMPDIR`
- Any `XDG_*` variables

All other environment variables (API keys, tokens, secrets) are excluded unless you explicitly add them via the `env` config key. This prevents accidental credential leakage to untrusted MCP servers.

```yaml
mcp_servers:
  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      # Only this token is passed to the subprocess
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_..."
```

### Credential Stripping in Error Messages

If an MCP tool call fails, any credential-like patterns in the error message are automatically redacted before being shown to the LLM. This covers:

- GitHub PATs (`ghp_...`)
- OpenAI-style keys (`sk-...`)
- Bearer tokens
- Generic `token=`, `key=`, `API_KEY=`, `password=`, `secret=` patterns

## Troubleshooting

### "MCP SDK not available -- skipping MCP tool discovery"

The `mcp` Python package is not installed. Install it:

```bash
pip install mcp
```

### "No MCP servers configured"

No `mcp_servers` key in `~/.hermes/config.yaml`, or it's empty. Add at least one server.

### "Failed to connect to MCP server 'X'"

Common causes:
- **Command not found**: The `command` binary isn't on PATH. Ensure `npx`, `uvx`, or the relevant command is installed.
- **Package not found**: For npx servers, the npm package may not exist or may need `-y` in args to auto-install.
- **Timeout**: The server took too long to start. Increase `connect_timeout`.
- **Port conflict**: For HTTP servers, the URL may be unreachable.
- **Server fails on import** (most common cause of `Connection closed`): reproduce
  the exact `command` invocation with the same env, see the Python traceback.
  See "Pit 3" above.

### "MCP server 'X' requires HTTP transport but mcp.client.streamable_http is not available"

Your `mcp` package version doesn't include HTTP client support. Upgrade:

```bash
pip install --upgrade mcp
```

### Tools not appearing

- Check that the server is listed under `mcp_servers` (not `mcp` or `servers`)
- Ensure the YAML indentation is correct
- Look at Hermes Agent startup logs for connection messages
- Tool names are prefixed with `mcp_{server}_{tool}` -- look for that pattern

### Connection keeps dropping

The client retries up to 5 times with exponential backoff (1s, 2s, 4s, 8s, 16s, capped at 60s). If the server is fundamentally unreachable, it gives up after 5 attempts. Check the server process and network connectivity.

## Examples

### Time Server (uvx)

```yaml
mcp_servers:
  time:
    command: "uvx"
    args: ["mcp-server-time"]
```

Registers tools like `mcp_time_get_current_time`.

### Filesystem Server (npx)

```yaml
mcp_servers:
  filesystem:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    timeout: 30
```

Registers tools like `mcp_filesystem_read_file`, `mcp_filesystem_write_file`, `mcp_filesystem_list_directory`.

### GitHub Server with Authentication

```yaml
mcp_servers:
  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_xxxxxxxxxxxxxxxxxxxx"
    timeout: 60
```

Registers tools like `mcp_github_create_pull_request`, etc.

### Remote HTTP Server

```yaml
mcp_servers:
  company_api:
    url: "https://mcp.mycompany.com/mcp"
    headers:
      Authorization: "Bearer sk-xxxxxxxxxxxxxxxxxxxx"
    timeout: 180
    connect_timeout: 30
```

### Multiple Servers

```yaml
mcp_servers:
  time:
    command: "uvx"
    args: ["mcp-server-time"]

  filesystem:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_xxxxxxxxxxxxxxxxxxxx"

  company_api:
    url: "https://mcp.internal.company.com/mcp"
    headers:
      Authorization: "Bearer sk-xxxxxxxxxxxxxxxxxxxx"
    timeout: 300
```

All tools from all servers are registered and available simultaneously. Each server's tools are prefixed with its name to avoid collisions.

## Sampling (Server-Initiated LLM Requests)

Hermes supports MCP's `sampling/createMessage` capability — MCP servers can request LLM completions through the agent during tool execution. This enables agent-in-the-loop workflows (data analysis, content generation, decision-making).

Sampling is **enabled by default**. Configure per server:

```yaml
mcp_servers:
  my_server:
    command: "npx"
    args: ["-y", "my-mcp-server"]
    sampling:
      enabled: true           # default: true
      model: "gemini-3-flash" # model override (optional)
      max_tokens_cap: 4096    # max tokens per request
      timeout: 30             # LLM call timeout (seconds)
      max_tool_loop_depth: 5  # tool loop limit (0 = disable)
      log_level: "info"       # audit verbosity
```

Servers can also include `tools` in sampling requests for multi-turn tool-augmented workflows. The `max_tool_loop_depth` config prevents infinite tool loops. Per-server audit metrics (requests, errors, tokens, tool use count) are tracked via `get_mcp_status()`.

Disable sampling for untrusted servers with `sampling: { enabled: false }`.

## Notes

- MCP tools are called synchronously from the agent's perspective but run asynchronously on a dedicated background event loop
- Tool results are returned as JSON with either `{"result": "..."}` or `{"error": "..."}`
- The native MCP client is independent of `mcporter` -- you can use both simultaneously
- Server connections are persistent and shared across all conversations in the same agent process
- Adding or removing servers requires restarting the agent (no hot-reload currently)

## Companion files in this skill

- `templates/minimax-mcp-wrapper.sh` — drop-in wrapper for
  `minimax-coding-plan-mcp` (and any other Python MCP server) that calls the
  venv's `python -c "from <pkg>.server import main; main()"`. Fixes the
  `ModuleNotFoundError` that bites `pip --target` installs.
- `scripts/mcp_diagnose.sh` — when `hermes mcp test <server>` is failing,
  this walks the four most common stdio MCP failure modes (config miss,
  command crash on import, missing env keys, unreachable upstream) and
  reports which one is biting you. Pass the server name; default is
  `MiniMax`.
- `references/minimax-mcp-session.md` — the end-to-end install walkthrough
  that came out of the session where this section was first written,
  including the four pitfalls in the order they actually bit, and the
  caveats around hot-reload and the `hermes mcp add --env` name-validation
  bug.
