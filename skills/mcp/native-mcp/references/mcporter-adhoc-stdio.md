# mcporter 0.9.0 — Ad-Hoc Stdio MCP Calls

This is a condensed reference for invoking an MCP server **without registering it** in the `native-mcp` config. Use this when:

- You want to call an MCP tool **once** for a verification (e.g., "does this npm-based MCP server work at all?")
- The skill you're working with has a SKILL.md that says to call `mcporter call --stdio "..."` (legacy pattern that still works in 0.9.0)
- The native-mcp config-based registration is overkill for a single test

## The pattern (verified working 2026-06-04)

```bash
# 1. Install mcporter (one-time, user-local)
mkdir -p ~/.local/lib/npm-global
npm config set prefix ~/.local/lib/npm-global
npm install -g mcporter         # ~7s, 119 packages
export PATH=$HOME/.local/lib/npm-global/bin:$PATH
echo 'export PATH=$HOME/.local/lib/npm-global/bin:$PATH' >> ~/.bashrc

# 2. Call any stdio MCP server ad-hoc (no config, no daemon)
mcporter call \
  --stdio "npx -y <package-name>@<version>" \
  <tool-name> \
  --args '<json-payload>'
```

Example (xmind-skill verification):

```bash
mcporter call \
  --stdio "npx -y xmind-generator-mcp@0.1.2" \
  generate-mind-map \
  --args '{"title":"Test","filename":"test","topics":[{"title":"A"}]}'
# → "Mind map successfully generated and saved to: /tmp/xmind-generator-mcp/test.xmind"
```

## How the args get there

The full flow is: `mcporter call` → spawns `npx -y <pkg>@<ver>` as a subprocess → JSON-RPC `initialize` → `tools/list` → `tools/call` with the args. `mcporter` translates the `--args '<json>'` flag into the JSON-RPC payload.

For more complex args (named flags instead of a single JSON blob), use key=value syntax:

```bash
mcporter call --stdio "npx -y xmind-generator-mcp@0.1.2" \
  read-mind-map \
  inputPath=/tmp/test.xmind \
  style=A
```

The schema is discovered from `tools/list` on first call.

## Differences from native-mcp config-based registration

| | `native-mcp` (in `config.yaml`) | `mcporter call --stdio` (ad-hoc) |
|---|---|---|
| **Where tools appear** | Auto-injected, prefixed `mcp_<server>_<tool>` | None — called via shell, no registration |
| **Persistent** | Yes — survives restarts | No — single call per invocation |
| **Discovery cost** | Paid once at Hermes startup | Paid every call (npx re-resolves each time) |
| **Output format** | JSON in the tool result | Human-readable text on stdout |
| **Use case** | Production workflows calling MCP tools repeatedly | One-off verification, smoke test, debugging |
| **Token cost** | Same | Same |
| **Time cost (first call)** | 1-3s (npx cold) | 5-15s (npx cold; reuses ~/.npm cache after) |

## Common pitfalls

- **`mcporter` not on PATH** — if you install via `npm install -g` but npm's global prefix isn't `~/.local/lib/npm-global`, you'll get `EACCES` on `/usr/lib/node_modules/...`. Always check `npm config get prefix` before installing and set it to a user-writable dir.
- **Old SKILL.md syntax** — many skills' docs were written for `mcporter <0.9` and use `mcporter call --stdio "<full command with args as one string>"`. The pattern still works in 0.9.0 (verified), but the new docs recommend `mcporter config add` first. Either works; ad-hoc is faster for one-off calls.
- **`npx` first-call latency** — first invocation pays the package install cost (10-15s for medium npm packages). Subsequent calls reuse `~/.npm/_npx` cache (2-5s). Don't be alarmed by the first slow call.
- **Ad-hoc server output paths are fixed by the server** — e.g., `xmind-generator-mcp@0.1.2` writes all XMind files to `/tmp/xmind-generator-mcp/<name>.xmind` regardless of the `filename` field. The `filename` is only the XMind-internal title, not the disk path. If you need it elsewhere, `mv` after the call.
- **Schema discovery is silent** — `mcporter` does NOT print the discovered tool schema unless you add `--output json` (or `--schema` to `mcporter list`). If a tool call fails with "Unknown tool", add `--output json` to see what was actually discovered.

## When to use which

- **One-off verification** (does the MCP server work? does the auth work? is the output format right?) → `mcporter call --stdio`
- **Production workflow** (calling the same MCP tool every X minutes) → register in `~/.hermes/config.yaml` under `mcp_servers:` and use `native-mcp`

If you're unsure, start with ad-hoc. Upgrading to native-mcp is a 5-line config change once you know the server works.

## Verified-working smoke test (copy-paste runnable)

```bash
set -e
export PATH=$HOME/.local/lib/npm-global/bin:$PATH

# Install mcporter
mkdir -p ~/.local/lib/npm-global
npm config set prefix ~/.local/lib/npm-global
npm install -g mcporter

# Make sure npx is available
which npx || (apt-get update -qq && apt-get install -y nodejs npm)

# Call the xmind MCP
mcporter call \
  --stdio "npx -y xmind-generator-mcp@0.1.2" \
  generate-mind-map \
  --args '{"title":"smoke","filename":"smoke","topics":[{"title":"hi"}]}'

# Read what was just written
ls -la /tmp/xmind-generator-mcp/smoke.xmind
```

Expected: `Mind map successfully generated and saved to: /tmp/xmind-generator-mcp/smoke.xmind` + a ~1.5KB zip file at that path.
