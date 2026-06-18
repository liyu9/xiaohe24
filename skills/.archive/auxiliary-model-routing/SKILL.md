---
name: auxiliary-model-routing
description: "Configure Hermes' `auxiliary.*` task blocks (vision, web_extract, compression, skills_hub, approval, mcp, title_generation, triage_specifier, kanban_decomposer, profile_describer, curator, session_search) to use a specific custom provider/model. Use when the user says 'vision tool not working', 'auxiliary title generation failed', 'route vision through my own provider', 'point compression at Claude', 'use a custom OpenAI-compatible endpoint for OCR / image analysis / session search / skill curation', or any 'configure the auxiliary model' / 'auxiliary.<task>.provider' request. Covers the auxiliary schema, the OpenRouter default, image_input_mode, end-to-end MCP server install (venv, wrapper, mcp_servers yaml, 4-step verification), and the verification recipe (HTTP probe + config show)."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, config, auxiliary, vision, providers, custom-endpoint, multimodal, model-routing]
---

# Auxiliary Model Routing

Hermes delegates a dozen "background" tasks to small/fast LLMs instead of the main model: image analysis (`vision_analyze`), web page extraction (`web_extract`), context compression, title generation, session search expansion, skill curation, kanban decomposition, etc. Each of these has its own provider/model override in `auxiliary.*`. This skill covers **how to configure those blocks correctly** — and how to verify the configuration actually works (not just that the yaml parses).

## The `auxiliary.*` schema (as of v0.15.x)

Each auxiliary block has the same fields:

```yaml
auxiliary:
  <task_name>:
    provider: auto          # provider key (see below)
    model: ''               # model name (empty = inherit)
    base_url: ''            # empty = inherit from provider
    api_key: ''             # empty = inherit from provider
    timeout: 30             # seconds
    extra_body: {}          # merged into request body (provider-specific)
    download_timeout: 30    # for tasks that fetch URLs (vision, web_extract)
```

**All known task names** (block order in `config.yaml` may vary, but these are the canonical ones):

| Task | What it does | Default tool that calls it |
|------|--------------|----------------------------|
| `vision` | Image analysis | `vision_analyze` |
| `web_extract` | URL → markdown | `web_extract` |
| `compression` | Context-window compression | automatic on token threshold |
| `skills_hub` | Skill search/curation | `/skills` browse |
| `approval` | `approvals.mode: smart` judge | command approval flow |
| `mcp` | MCP tool dispatch helper | MCP server wrappers |
| `title_generation` | Auto-title session from first message | session creation |
| `triage_specifier` | Decide which agent handles inbound message | gateway routing |
| `kanban_decomposer` | Break a task into Kanban cards | `kanban` tool |
| `profile_describer` | Summarize user profile from session | memory writer |
| `curator` | Curate skills/commands | skill/command discovery |
| `session_search` | Expand a query for session FTS | `session_search` |

**Pitfall — there is no `native` field.** A common LLM hallucination when reading old docs is suggesting `provider: native` or `vision_mode: native`. These fields don't exist. The valid value is a **provider key** (see below) or `auto`.

## Provider resolution

`provider` can be:

1. **`auto`** — Hermes walks a built-in fallback chain (OpenRouter → Google → others) based on which env vars are set. **Falls back to first available key.** If you have `OPENROUTER_API_KEY` set, `auto` resolves to OpenRouter; if you have only `GOOGLE_API_KEY`, it resolves to Google. If neither, you get `No LLM provider configured`.

2. **A built-in name** — `openrouter`, `anthropic`, `openai`, `google`, etc. Direct, no walking.

3. **A `custom:` prefix** — `custom:minimax_coding`, `custom:my_azure`, etc. References a key under the top-level `providers:` block in `config.yaml`.

4. **A bare custom name** — `minimax_coding` (no prefix). Same as `custom:minimax_coding`; both work in `auxiliary.*` blocks. The existing `auxiliary.title_generation.provider: minimax_coding` pattern in the default config proves the bare form is valid.

**Empty `base_url` and `api_key` are inherited** from the named provider. This is the cleanest way to point a task at an existing custom provider:

```bash
# Add a new auxiliary task backed by the existing minimax_coding provider
hermes config set auxiliary.vision.provider minimax_coding
hermes config set auxiliary.vision.model MiniMax-M3
# base_url + api_key left empty → inherited from providers.minimax_coding
```

This avoids registering a new provider, avoids duplicating secrets, and survives provider updates.

## Default-provider diagnostic

`hermes config check` prints which env vars feed which tools:

```
○ OPENROUTER_API_KEY → vision_analyze, mixture_of_agents
○ GOOGLE_API_KEY
○ GEMINI_API_KEY
```

**This is informational, not mandatory.** It tells you what `auto` *would* fall back to. If you set `auxiliary.vision.provider` explicitly, the listed env var is irrelevant — your explicit provider wins. Don't be fooled into thinking you need to set `OPENROUTER_API_KEY` when you've already pointed `vision` at a custom provider.

## `image_input_mode` (vision-specific)

Controls how the main agent (not `vision_analyze` itself) hands images to the LLM:

```yaml
agent:
  image_input_mode: url-only    # default in v0.15.1; refuses local paths
  # image_input_mode: base64    # local files only, no remote
  # image_input_mode: both      # accept both (v0.15.2+)
```

**The default `url-only` will silently reject local paths** in `vision_analyze(image_url='/home/.../foo.jpg')`. Symptoms: the tool errors with "unsupported scheme" or "cannot fetch local file". Fix:

```bash
hermes config set agent.image_input_mode both
```

`both` is the safe default for a local agent that may receive both file paths and HTTP URLs.

## Multimodal vision with a custom provider (the M3 use case)

Many custom providers expose vision through their main chat endpoint. Example: MiniMax-M3 is natively multimodal, served via the Anthropic-compatible endpoint at `https://api.minimaxi.com/anthropic` with `api_mode: anthropic_messages`.

**Recipe:**

```bash
# 1. Confirm the existing custom provider has the right base_url + api_mode
grep -A8 'minimax_coding:' ~/.hermes/config.yaml | head -10
# Expect: base_url: https://api.minimaxi.com/anthropic
#         api_mode: anthropic_messages
#         model: MiniMax-M3

# 2. Point vision at it
hermes config set auxiliary.vision.provider minimax_coding
hermes config set auxiliary.vision.model MiniMax-M3

# 3. Allow local image paths
hermes config set agent.image_input_mode both

# 4. Verify Hermes recognized the config
hermes config show | grep -A1 Vision
# Expect: Vision provider=minimax_coding, model=MiniMax-M3

hermes config check    # config version still valid, no schema errors
```

**Important:** the `auxiliary.*` task blocks do **not** currently expose an `api_mode` override. They inherit `api_mode` from the named provider. So when you point `vision` at a provider whose `api_mode: anthropic_messages`, the vision task will use Anthropic message format. This works if your custom endpoint accepts that format and the model is multimodal.

## `Connection closed` is almost always a server-startup crash, not a network problem

When `hermes mcp test <server>` reports `✗ Connection failed (NNNN ms):
Connection closed`, the default reaction is "the network is bad" or "wrong
auth". Often wrong. Reproduce the server invocation directly:

```bash
MINIMAX_API_KEY=$(grep '^MINIMAX_API_KEY=' ~/.hermes/.env | cut -d= -f2-) \
MINIMAX_API_HOST=https://api.minimaxi.com \
  timeout 5 /path/to/server-wrapper.sh < /dev/null
```

- **Python traceback visible** → server is crashing on import. The most
  common causes:
  - `ModuleNotFoundError: No module named '<pkg>'` → the server's interpreter
    can't see the package; you installed with `pip --target` instead of a
    venv, or the wrapper's shebang points at the wrong python.
  - `ModuleNotFoundError: No module named 'dotenv'` (or any transitive dep)
    → you installed `--no-deps`. Reinstall with deps in the venv.
  - `ValueError: <env var> required` → env block missing a key the server
    actually reads.
- **Silent exit (timeout 124)** → server is waiting for stdin JSON-RPC,
  that's good; hermes should connect on the next `hermes mcp test`.
- **No output but exit code != 124** → server is exiting on its own for a
  reason that's not an import error. Read the server's docs / source.

See the `native-mcp` skill for the full MiniMax-coding-plan-mcp walkthrough
and a `scripts/mcp_diagnose.sh` that walks this checklist automatically.

## When the `hermes config set` env-block path is rejected

`hermes config set mcp_servers.<X>.env.<Y>` with an all-uppercase `<Y>` raises:

```
ValueError: Invalid environment variable name:
'MCP_SERVERS.MINIMAX.ENV.MINIMAX_API_KEY'
```

The config-set path treats any all-uppercase key as an OS env var and
rejects dotted paths. **Workarounds:**

- `hermes mcp add --env KEY=$VAL` knows the difference (the mcp-add path
  correctly emits `mcp_servers.<X>.env.KEY`), so use that.
- Or set the non-env fields with `hermes config set`, and add the env
  block with `hermes mcp add --command <cmd> --env K1=$V1 --env K2=$V2`.
- Or `sed -i` the literal `${VAR}` line into `~/.hermes/config.yaml`
  (back up first).

`config.yaml` is also a **protected file**: `patch` and `write_file` are
denied for it. `hermes config set` is the supported mutation path; raw
file edits are for one-off `sed` cases.

When you run `hermes config show` after setting `auxiliary.vision.provider=minimax_coding`, the output will look like:

```
Vision        provider=minimax_coding, model=MiniMax-M3
```

## Pitfall — `config show` displaying your block ≠ the block works

This is the same status it had with `provider: auto` (which errored "No LLM provider configured"). `config show` only proves **the YAML was parsed and the block exists in the schema** — it does **not** mean Hermes successfully resolved the provider or that an upstream call would succeed. Many agents stop here and report "vision works" based on this line alone. It does not. Always do the HTTP probe (next section) before claiming success.

## Verification recipe — **always** do this before declaring success

The biggest failure mode is **declaring "vision works now" based on `config show` output alone**, without ever calling the tool. `config show` only proves Hermes parsed the YAML — not that the upstream call returns 200.

Two verification steps, in order:

### Step 1: HTTP probe (no Hermes required)

Reproduce the exact request Hermes will make, with curl/Python. For an Anthropic-mode provider:

```python
# /tmp/vision_probe.py
import json, base64, urllib.request

img = open("/home/ubuntu/.hermes/image_cache/img_XXXX.jpg", "rb").read()
b64 = base64.b64encode(img).decode()

req = urllib.request.Request(
    "https://api.minimaxi.com/anthropic/v1/messages",
    data=json.dumps({
        "model": "MiniMax-M3",
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                  "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": "Describe this image in detail."}
            ]
        }]
    }).encode(),
    headers={
        "Content-Type": "application/json",
        "x-api-key": "sk-cp-...",
        "anthropic-version": "2023-06-01",
    },
    method="POST",
)
with urllib.request.urlopen(req, timeout=60) as r:
    print(r.status, r.read()[:2000].decode())
```

- HTTP 200 + non-empty assistant content → the **upstream pipeline works** (auth, image format, model name, multimodal support).
- 401/403 → wrong key or scope.
- 400 "model not found" → wrong model name for that endpoint.
- 400/422 image content errors → model not multimodal, or wrong `type` field for that provider's protocol.

### Step 2: Tool-level probe (inside a Hermes session)

```bash
# In any interactive chat, paste a local image and ask the agent to describe it
# Or in CLI:
hermes chat -q "Use vision_analyze to describe /home/ubuntu/.hermes/image_cache/img_XXXX.jpg"
```

If `vision_analyze` returns a description, end-to-end works. If it returns the same `No LLM provider configured` or an HTTP error, the `auxiliary.vision` block isn't being picked up — usually a `provider` typo or missing restart on legacy config schemas.

**Only after both steps pass is it safe to tell the user "vision works."** See `references/discipline-lesson.md` for the session where this lesson was learned the hard way.

## MiniMax-specific footgun: the `auto` 404 trap

When the main provider is MiniMax with `base_url: https://api.minimaxi.com/anthropic`, **`auto` resolves auxiliary tasks to `https://api.minimaxi.com/v1` — which doesn't exist**, returning HTTP 404. This is the source of:

```
⚠ Auxiliary title generation failed: HTTP 404: 404 page not found
```

**Fix:** pin the affected tasks to the main provider explicitly:

```bash
hermes config set auxiliary.title_generation.provider minimax_coding
# Repeat for any other auxiliary task showing 404
```

Then restart. The `auxiliary.title_generation.provider: minimax_coding` line in the default config is exactly this fix pre-applied.

## Install a new MCP server end-to-end

The `auxiliary.mcp` task (or any user-installed MCP server) starts as nothing —
you have to install the package, write a wrapper, register it under
`mcp_servers:`, and **verify with a real call** (not just `hermes mcp test`,
which can pass while the server can't actually answer). The full 8-pitfall
recipe (uv mirror timeouts, `--target` install invisibility, `pip install`
versus venv, the 30s auto-reload race, the `env` upper-case-key bug, async
stdio read quirks, etc.) lives in **`references/install-mcp-server.md`** —
load it when you're about to add a new server. TL;DR:

1. **Read the server's own docs first** (README / `mcpServers` example / `env`
   variable names). Required reading on the Hermes side:
   `mcp-config-reference.md`, `use-mcp-with-hermes.md`,
   `user-guide/features/mcp.md` (L145 `${VAR}` substitution, L232 30s
   auto-reload window).
2. **Install into `~/.hermes/mcp/<name>/venv/`** with
   `pip` against a fast mirror (`mirrors.tencentyun.com` from Tencent Cloud
   egress). **Never** `/tmp` and **never** `pip install --target` — the
   shebang can't see target site-packages.
3. **Write a wrapper script** that `exec`s the venv's python with the entry
   point: `from <pkg>.server import main; main()`. `chmod +x`, smoke-test
   once (no output = server correctly waiting for JSON-RPC on stdin).
4. **Configure `mcp_servers:` with `${VAR}` references** for secrets. Use
   `hermes config set mcp_servers.<name>.<key> <val>` per field rather than
   `hermes mcp add` (which triggers the 30s auto-reload race on first install).
5. **Verify with all 4 steps** (in order): `hermes config check` →
   `hermes mcp list` → `hermes mcp test <name>` → **direct JSON-RPC stdio
   call** (`subprocess.Popen` + non-blocking fd read, NOT
   `subprocess.communicate()` which drops slow async responses). The 4th
   step is the only one that proves a real tool call returns real data.

If the install fails at any step, see **`references/mcp-failure-modes.md`**
for the `Connection closed` / 30s auto-reload / `config set` upper-case-key
catalog.

## When to use this skill

- User says "vision_analyze not working" / "image analysis fails" / "No LLM provider configured"
- User says "title generation failed" / "compression 404"
- User says "use my custom provider for X" / "route vision through Y"
- User wants to point `curator` / `session_search` / `kanban_decomposer` at a specific model
- You're about to add a new `auxiliary.*` block via `hermes config set`
- User says "install MCP server X" / "add a new MCP server" / "configure mcp_servers" / "Connection closed" — load `references/install-mcp-server.md` and `references/mcp-failure-modes.md`

## When NOT to use this

- The user wants to change the **main** chat model → `hermes model` or edit `model.default`
- The user wants OAuth login → `hermes login --provider X`
- The provider doesn't support the auxiliary task at all (e.g., a pure-completion model used for vision) → pick a different provider for that block
- The `extra_body` field is needed for provider-specific params → write a script, don't try to express it in chat

## Reference files

- `references/discipline-lesson.md` — the "don't fabricate tool output" session, and the 5 rules that came out of it (applies to **every** config or verification step in this skill — the verification recipe in SKILL.md was born from this lesson)
- `references/mcp-failure-modes.md` — when `hermes mcp test` reports `Connection closed` (or any other connection error), what the actual cause usually is (server crash on import, not network), how to reproduce the server invocation outside hermes to see the real traceback, the 30s auto-reload race, and the `hermes config set mcp_servers.<X>.env.<Y>` upper-case-key bug
- `references/install-mcp-server.md` — full 8-pitfall recipe for installing a new MCP server end-to-end: venv setup, wrapper script, `mcp_servers:` yaml with `${VAR}` references, the 4-step verification (config check → list → test → real JSON-RPC call), and a debugging quick-reference table
- `scripts/vision_probe.py` — drop-in end-to-end vision probe; pass `--image`, `--provider anthropic_messages|openai_chat`, `--base-url`, `--model`, `--api-key`. Exits 0 only if HTTP 200 + non-empty assistant content.
- `scripts/minimax_anthropic_vision_probe.py` — pre-wired for the MiniMax-M3 case (Anthropic protocol at `https://api.minimaxi.com/anthropic`); zero-config run that fails loud if the upstream is down.

## Verification checklist before responding to the user

- [ ] `hermes config check` passes (config version still valid)
- [ ] `hermes config show | grep -A1 Vision` shows the new provider/model
- [ ] **HTTP probe returned 200 with actual model output** (not a 404 / not a 401)
- [ ] If vision: `image_input_mode` matches the user's input format (path vs URL)
- [ ] Restart recommended in the response if `auxiliary.*` blocks were added (some Hermes versions hot-reload, some don't)
- [ ] No claim of "it works" without having seen the model return content
