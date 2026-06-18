# OpenViking Startup Error Catalog

Quick reference for errors seen during `openviking-server` startup. Read the session's `process(action='log', session_id=...)` output and match against this table.

## Errors that block startup

| Error message | Root cause | Fix |
|---|---|---|
| `OpenViking configuration file not found. Please create /home/ubuntu/.openviking/ov.conf or /etc/openviking/ov.conf, or set OPENVIKING_CONFIG_FILE.` | No `ov.conf` written | Write `~/.openviking/ov.conf` with at minimum `storage.workspace` and one of `embedding.dense` / `embedding.sparse` / `embedding.hybrid` |
| `Unknown config field 'embedding.model'`, `'embedding.api_key'`, `'embedding.api_base'`, `'embedding.provider'`, `'embedding.input'` | Flat schema — `model` / `api_key` / etc. placed directly under `embedding` instead of under `embedding.dense` / `embedding.sparse` / `embedding.hybrid` | Move all model config under `embedding.dense.X` (or `sparse` / `hybrid`) |
| `Unknown config field 'embedding.sparse'`, `'embedding.sparse.model'`, etc. (when you have only `embedding.sparse` set) | `embedding.sparse` requires an explicit `algorithm`; also the schema may require a `dense` to be present for fallback | Set `embedding.dense` instead of `embedding.sparse`, or add a `dense` fallback |
| `ValueError: At least one embedding configuration (dense, sparse, or hybrid) is required` | None of the three embedding sub-keys are present | Add `embedding.dense` block |
| `ValueError: embedding.text_source must be one of: summary_first, summary_only, content_only` | Bad `text_source` value | Use one of the three allowed values (default `content_only` is fine; just delete the field) |
| `Address already in use` on port bind | A previous `openviking-server` instance is still alive, or another process is on that port | `lsof -i :<port>` → kill the leftover; or pick `--port 8766` |
| `ValidationError: 1 validation error for EmbeddingModelConfig\nprovider\n  Input should be 'openai','volcengine','vikingdb','jina','ollama','gemini','voyage','dashscope','minimax','cohere','litellm','local'` | Bad `provider` value | Use one of the listed strings; for ARK it is `volcengine` |

## Errors that don't block startup (server runs, but operations fail)

| Symptom | Likely cause | Fix |
|---|---|---|
| `/health` 200 but `add-resource` 4xx with volcengine body mentioning `model not found` | Wrong `embedding.dense.model` name (e.g. `doubao-embedding-vision` on a text endpoint, or a typo) | Cross-check volcengine console for the exact model name; or use `doubao-embedding` for text |
| `/api/v1/resources` POST returns 401 from upstream | API key wrong region / expired | Verify the `api_base` matches the key's region (`cn-beijing` is the most common) |
| Server runs ~30s then exits with no log message | The `embedding` init call to the model API failed and the server gave up | Set `OPENVIKING_LOG_LEVEL=DEBUG` (env var, passed via `export` before `terminal(background=true)`) to see the upstream call trace |
| `/api/v1/skills` returns 200 but `add-skill` 500s with `storage.workspace not writable` | The `storage.workspace` directory doesn't exist and the server can't create it | `mkdir -p /home/ubuntu/.openviking/data` before starting |

## What "healthy" looks like

When the server is fully up and all configs are valid, the `/health` endpoint returns:

```json
{"status":"ok","healthy":true,"version":"0.3.24","auth_mode":"dev"}
```

`auth_mode: "dev"` is the default for local dev; production deployments flip this to `api_key` or `oauth`.

`/openapi.json` returns 200 with a `paths` object listing 26+ endpoints. If `paths` is empty or `/api/v1/resources` is missing, the server is up but a router failed to register — restart it.

## When in doubt

Read the schema directly:

```bash
# in venv
python -c "import openviking_cli.utils.config.embedding_config as m; help(m.EmbeddingConfig)"
python -c "import openviking_cli.utils.config.vlm_config as m; help(m.VLMConfig)"
```

These are the source of truth — the README, the npm CLI docs, and even the `--help` output are summaries of these classes.
