# Hallucination Catalog — Verified Wrong vs. Correct

A running list of specific claims that have appeared in user-supplied setup guides and been verified **wrong** against the live Hermes 0.15.x system. Use this to short-circuit audits: if the doc says X, check the catalog first.

## Path / directory

| Doc claim | Reality |
|---|---|
| `~/.hermes/personas/soul.md` | `~/.hermes/SOUL.md` (single file, not in `personas/`) |
| `~/.hermes/personas/product-manager.md` | Doesn't exist; the system has 14 built-in personalities in `agent.personalities` (`helpful`/`concise`/`technical`/`creative`/`teacher`/`kawaii`/`catgirl`/`pirate`/`shakespeare`/`surfer`/`noir`/`uwu`/`philosopher`/`hype`); you select via `display.personality` |
| `~/.hermes/teams/` | Doesn't exist; no multi-agent team config |
| `~/.hermes/knowledge/` | Doesn't exist; knowledge lives in `~/.hermes/skills/<name>/SKILL.md` |

## Config keys (yaml)

| Doc claim | Reality |
|---|---|
| `persona: default: "soul"` | No such field; `display.personality: <one of 14 enum values>` |
| `auto_improve: true` | Doesn't exist; the closest real fields are `skills.guard_agent_created`, `curator.enabled`, `agent.disabled_toolsets` |
| `lazy_load: true` / `max_loaded_skills: 8` | Doesn't exist; skills are loaded by trigger matching, not lazy thresholds |
| `memory.embedding_model: bge-micro-zh` | Doesn't exist; Hermes memory is **FTS5 full-text over session DB**, not a vector store. `memory.memory_enabled` / `memory.user_profile_enabled` are the real switches |
| `memory.long_term` / `memory.episodic` / `memory.semantic` | None of these exist |
| `compression.enabled: false` | Real, but default is `true` (not "off as doc suggests for safety") |
| `tool_call_timeout: 30` | Real field is `agent.gateway_timeout` (default 1800s) — affects everything, not just tool calls |
| `parallel_tool_calls: false` | Doesn't exist; the LLM controls parallelism, not the config |
| `smart_approval: true` | Doesn't exist; the real switch is `approvals.mode` (`manual`/`smart`/`off`) |
| `auto_retry: 1` | Real field is `agent.api_max_retries` (default 3) |
| `execution.max_turns: 5` | Real field is `agent.max_turns` (default 60, NOT 5); `goals.max_turns: 20` is the goal-task limit, different field |
| `api_key` under `security:` | Real: `api_key` lives under `model:` and `providers.<name>`, not `security:`. The security section has `tirith_*`, `allow_private_urls`, `redact_secrets`, `website_blocklist` |
| `allowed_ips: [...]` under `security:` | Doesn't exist; IP filtering is a platform feature, not a config field |
| `provider: "anthropic"` | Real provider id format is `custom:<name>` (e.g. `custom:minimax_coding`) |

## CLI commands

| Doc claim | Reality |
|---|---|
| `hermes profile create product-manager` | Doesn't exist; `hermes profile` exists but has no `create` subcommand in 0.15.x |
| `hermes config validate` | Doesn't exist; use `hermes config check` |
| `hermes doctor` | **Does** exist (verify with `hermes --help` first; some older guides are wrong) |
| `hermes memory import <file>` | Doesn't exist |
| `hermes memory list` | Doesn't exist as CLI; the `memory` tool is a function call, not a CLI subcommand |
| `hermes skills publish` | **Does** exist as of 0.15.x; verify before claiming wrong |

## Network / endpoints

| Doc claim | Reality |
|---|---|
| "Use `mirror.ghproxy.com` for GitHub proxy" | Mirror itself is **blocked from Tencent Cloud egress** (HTTP 000) as of 2026-06. Use `gh-proxy.com` or `gh.idayer.com` for GET; **neither proxies push**; for push, switch to SSH |
| "Configure proxy in `~/.hermes/config.yaml` under `proxy:`" | No `proxy:` section in config; proxy is set via env vars (`HTTPS_PROXY`, `HTTP_PROXY`) or by `terminal.backend: docker` with `docker_extra_args` |
| "Add cloud provider integration in config" | No cloud-provider integration in Hermes core; you'd need a plugin |

## Behavioral claims

| Doc claim | Reality |
|---|---|
| "切换人格用 `/personality X` 命令" | Real slash command is `/personality <name>` (single arg, one of the 14 enum) — works, but only switches between the built-ins, not user-defined yaml |
| "Hermes will auto-create skills based on usage" | `skills.guard_agent_created` defaults `false`; auto-creation needs the agent to *propose* a skill, which only happens after a complex task completes |
| "Memory is shared across all Hermes profiles" | **No.** Each profile has its own `~/.hermes/profiles/<name>/` and own memory. Sharing requires explicit export/import |
| "Set `max_turns: 5` to save tokens" | At 5, almost any multi-step task (search → read → fix → verify) gets cut off. Use 20-40 for typical work, 60+ for code refactors |

## PyPI packages (added 2026-06-05 session)

AI-generated setup guides are **particularly prone to fabricating PyPI package names and version numbers**. Hallucination patterns observed:

- **Adding a product suffix to a real package name** — e.g. `sibyl-memory-hermes` (real: `sibyl-memory`), `openviking-hermes` (real: `openviking`). The guide author knows the host product and tacks on a suffix; the package author rarely ships a separate `-<host>` distribution.
- **Inflating version numbers** to make a 0.3.x alpha look "production-ready" — e.g. `openviking 0.8.2` (real: `0.3.23`, alpha stage). Guides love round numbers and don't bother checking PyPI.
- **Claiming a package ships its own CLI** when it has no `console_scripts` entry point — `openviking` has no `openviking --version` after `pip install`; the CLI requires `cargo install` from source.
- **Claiming 0-config / 0-API-key install** for packages that clearly need model credentials — `openviking` requires VLM + Embedding model API keys at runtime.

**Audit recipe for any `pip install <pkg>` claim in a guide:**

```bash
# 1. Does the package exist?
pip show <pkg> 2>&1 | head -3
# 2. Actual version + author + project URLs
curl -s "https://pypi.org/pypi/<pkg>/json" | python3 -c "import json,sys; d=json.load(sys.stdin); print('version:', d['info']['version']); print('author:', d['info']['author']); print('project_urls:', json.dumps(d['info'].get('project_urls', {})))"
# 3. Does the package ship a CLI? (check entry_points)
curl -s "https://pypi.org/pypi/<pkg>/json" | python3 -c "import json,sys; d=json.load(sys.stdin); print('entry_points:', d['info'].get('entry_points') or 'NONE')"
# 4. Does the upstream README confirm the install path the guide claims?
curl -sL "https://raw.githubusercontent.com/<author>/<repo>/main/README.md" | head -100
```

**Verified-wrong claims (2026-06-05 session):**

| Doc claim | Reality |
|---|---|
| `pip install sibyl-memory-hermes` | Real: `pip install sibyl-memory` (PyPI author: "SIBYL, Sibyl Labs LLC", NOT a Hermes-branded package) |
| `pip install openviking-hermes` | Real: `pip install openviking` (no `-hermes` suffix exists). Author: ByteDance / volcengine |
| `openviking 0.8.2` | Real: `0.3.23` (alpha, classifiers say `Development Status :: 3 - Alpha`). Round-number version is a tell. |
| `openviking --version` after pip install | Does NOT exist. CLI requires `cargo install --git https://github.com/volcengine/OpenViking ov_cli` from source. |
| `~/.hermes/openviking.db` (SQLite file) | Doesn't exist. OpenViking is a **filesystem-paradigm context database** (viking:// URIs, tiered L0/L1/L2 loading, 5-category directory layout), not a SQLite file. Guides describing SQL tables `memories/documents/chunks/entities` are entirely invented. |
| "0 API key, 0 network, fully offline" (for openviking) | False. Requires VLM + Embedding model API keys (volcengine / OpenAI / kimi / GLM). |

**Cross-check pattern:** any guide naming a "Hermes integration" package with `-hermes` or `-for-hermes` in the name is suspect — check PyPI first. Real integration packages are usually named `<product>` (not `<product>-hermes`); the integration happens via the host's plugin loader (e.g. `plugins/memory/<product>/__init__.py`).

## Hermes `memory` subcommand set (verified 0.15.1, 2026-06-05)

| Doc claim | Reality |
|---|---|
| `hermes memory enable sibyl` | Doesn't exist. Real subcommands: `setup / status / off / reset` only. `enable` is a hallucination. |
| `hermes memory status` | **Real.** Output format: `Built-in: always active / Provider: <name or none> / Installed plugins: <list>`. The "Installed plugins" list is the authoritative source of supported providers. |
| `hermes memory setup` | **Real.** Interactive wizard; the truthful ground truth of the provider's config schema is what `setup` actually generates — not what the guide says. |
| Available providers (0.15.1) | `honcho / openviking / mem0 / hindsight / holographic / retaindb / byterover / supermemory`. **A real PyPI package is not enough to be a Hermes provider** — e.g. `sibyl` is a real package on PyPI but NOT in the Hermes provider list. Always check `hermes memory status` output. |
| `hermes docs add/list/delete/search` | Doesn't exist. Hermes has no `docs` subcommand. Document indexing/RAG is delegated to the memory provider's own API (e.g. openviking has resource ingestion), not a top-level `hermes docs` command. |
| `/sql "SELECT..."` slash command | Doesn't exist. There is no SQL-execution slash command. Providers expose their data through provider-specific APIs, not via Hermes' slash command layer. |

## How to extend this catalog

When a new doc audit turns up a wrong claim that isn't here:

1. Add a row in the right section with `Doc claim` and `Reality`
2. Include the Hermes version you verified against (e.g. "verified Hermes 0.15.1")
3. If the doc was a Xmind/Markdown/PDF, keep the file path in a comment so you can re-check on version bumps
4. For PyPI claims, also record the **probed URL** (`https://pypi.org/pypi/<pkg>/json`) and the **upstream repo** the package points to — version and author drift between sessions

The catalog only stays useful if it tracks the **specific** (doc string → real config) pairs, not the general "docs lie" principle.

## npm global install layout (verified Hermes host, 2026-06-05)

When the host has `npm config get prefix` set to `~/.local` (Hermes install path), `npm i -g <pkg>` does NOT install to `/usr/local/`. It installs to:

| Path | Content |
|---|---|
| `~/.local/lib/npm-global/lib/node_modules/<pkg>/` | Package source |
| `~/.local/lib/npm-global/bin/<cmd>` | **Only if** the package's `package.json` declares `bin` correctly |

Common audit pitfall: AI guides assume `npm i -g` puts binaries on `$PATH` immediately. Two failure modes observed:

1. **No `bin` field or wrong path** — e.g. `@openviking/cli@0.3.24` ships a linux-x64 nested binary at `node_modules/@openviking/cli/node_modules/@openviking/cli-linux-x64/bin/ov` but the wrapper `bin/ov` symlink is missing. After `npm i -g`, `which ov` returns nothing.
2. **Linux package has `claude.exe` suffix** — e.g. `@anthropic-ai/claude-code@2.1.165` ships a 244MB binary at `bin/claude.exe` (literal filename, even on Linux). A symlink to `bin/claude` (no suffix) breaks silently. Always `ls -la <pkg>/bin/` to find the real binary name.

**Fix recipe (long-term stable, doesn't pollute `~/.bashrc`):**

```bash
# 1. Find the real binary
ls -la ~/.local/lib/npm-global/lib/node_modules/<pkg>/bin/
ls -la ~/.local/lib/npm-global/lib/node_modules/<pkg>/node_modules/ 2>/dev/null   # nested layouts

# 2. Symlink into the user bin dir (already on PATH for this host)
ln -s <absolute-real-binary-path> ~/.local/bin/<cmd-name>

# 3. Verify
which <cmd-name> && <cmd-name> --version
```

This is preferable to `export PATH=~/.local/lib/npm-global/bin:$PATH` because:
- Doesn't depend on shell startup order (login vs non-login, tmux, systemd)
- Doesn't pollute `~/.bashrc` / `~/.zshrc` (which the user has explicitly flagged as off-limits)
- Matches the host's existing convention: `~/.local/bin/` already hosts `uv`, `uvx`, `gh`, `hermes`, `hermes-agent`, `oc-skills`, `skillhub` — all user-installed CLIs land there

## OpenViking real config (verified Hermes 0.15.1, 2026-06-05)

The official openviking PyPI package (0.3.23, alpha, volcengine/ByteDance) is the **filesystem-paradigm context database** — not a SQL store, not a "SQL + RAG" hybrid, not a SQLite file. Real architecture:

| Doc claim | Reality |
|---|---|
| `~/.hermes/openviking.db` (SQLite) | Doesn't exist. Data lives in `~/.openviking/` as a `viking://` virtual filesystem with tiered L0/L1/L2 layers (L0 ≈100 tokens summary, L1 ≈2k overview, L2 full content). |
| `openviking 0.8.2` | Real: `0.3.23`, alpha stage (`Development Status :: 3 - Alpha`). |
| Storage: SQL tables `memories / documents / chunks / entities` | Entirely invented. The 5 categories are filesystem subdirs under `viking://` (preference / entity / event / case / pattern), addressed by URI. |
| "0 API key, fully offline" | False. Requires **both** a VLM model (image/content understanding) and an Embedding model (vectorization) at runtime. |

**Real Hermes integration path** (verified at `~/.hermes/hermes-agent/plugins/memory/openviking/__init__.py`):

- Plugin is HTTP-based, calls `openviking-server` at `http://127.0.0.1:1933` (default)
- Required env vars (profile-scoped, in `~/.hermes/.env`):
  - `OPENVIKING_ENDPOINT` (default `http://127.0.0.1:1933`)
  - `OPENVIKING_API_KEY` (optional, only for authenticated servers)
  - `OPENVIKING_ACCOUNT` (default `default`)
  - `OPENVIKING_USER` (default `default`)
  - `OPENVIKING_AGENT` (default `hermes`)
- Session lifecycle: on session end, plugin triggers `viking_remember` to extract memories into 5 viking:// subdirs (preferences / entities / events / cases / patterns)
- Retrieval: `viking://` URI directory positioning + semantic search (mixed, not pure vector)
- Full bidirectional `MemoryProvider` interface (rewritten 2026-06 from PR #3369, not read-only)

**VLM provider trick (the only stable way to use non-OpenAI providers):**

openviking's VLM config supports `provider: "openai"` with a custom `api_base` for **any OpenAI-compat endpoint**, including:

- `https://api.minimaxi.com/v1` (minimax M3, verified 200 OK with `MiniMax-M3` model id)
- `https://ark.cn-beijing.volces.com/api/plan/v3` (volcengine ARK plan endpoint, with `doubao-embedding-vision` for embeddings)

**NOT supported**: native Anthropic-protocol endpoints (`/v1/messages` style) — the VLM client assumes OpenAI-style `/v1/chat/completions`. If you have an Anthropic-only key, the only path is to wrap it behind an OpenAI-compat proxy or use a different provider for VLM.

**Embedding endpoint quirk**: volcengine's standard `doubao-embedding` does NOT work on the `/api/plan/v3` (agent-plan) endpoint — returns `UnsupportedModel`. The vision variant `doubao-embedding-vision` works (200 OK with real vectors). Always probe with a curl POST before committing to a model in `openviking-server init`.

**Audit recipe for any openviking-related doc claim:**

```bash
# 1. Verify package on PyPI
curl -s "https://pypi.org/pypi/openviking/json" | python3 -c "import json,sys; d=json.load(sys.stdin); print('version:', d['info']['version']); print('author:', d['info']['author']); print('project_urls:', d['info'].get('project_urls', {}))"

# 2. Verify Hermes plugin path and env var names
ls -la ~/.hermes/hermes-agent/plugins/memory/openviking/__init__.py
grep -E "OPENVIKING_|viking://|viking_remember" ~/.hermes/hermes-agent/plugins/memory/openviking/__init__.py

# 3. Verify Hermes recognises openviking as a provider
hermes memory status

# 4. Probe model endpoints
curl -s -X POST https://<api_base>/v1/embeddings -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"model":"<model-id>","input":["test"]}' | head -c 500
```
