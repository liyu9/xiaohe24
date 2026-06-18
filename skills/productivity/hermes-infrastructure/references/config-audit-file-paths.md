# Hermes + OpenClaw config file paths

The 6 source-of-truth files and how each is located.

## Primary paths

| File | Canonical path | Override env var |
|---|---|---|
| `~/.hermes/.env` | `/home/ubuntu/.hermes/.env` | `HERMES_HOME` (parent dir) |
| `~/.hermes/config.yaml` | `/home/ubuntu/.hermes/config.yaml` | `HERMES_HOME` (parent dir) |
| `~/.hermes/SOUL.md` | `/home/ubuntu/.hermes/SOUL.md` | n/a — fixed |
| `~/.hermes/memories/MEMORY.md` | `/home/ubuntu/.hermes/memories/MEMORY.md` | `HERMES_HOME/memories/` |
| `~/.hermes/memories/USER.md` | `/home/ubuntu/.hermes/memories/USER.md` | `HERMES_HOME/memories/` |
| `~/.openclaw/openclaw.json` | `/home/ubuntu/.openclaw/openclaw.json` | `OPENCLAW_STATE_DIR` (parent) |

## Profile-aware paths

`HERMES_HOME` is profile-aware. With the default profile:

```
HERMES_HOME = /home/ubuntu/.hermes
```

With a named profile (e.g. `~/.hermes/profiles/agent-coder/`):

```
HERMES_HOME = /home/ubuntu/.hermes/profiles/agent-coder
```

The same 6-file structure is mirrored under each profile. **Audit
must respect the active profile** — running `cat /home/ubuntu/.hermes/config.yaml`
on a non-default-profile session returns the wrong file.

To detect the active profile:

```python
import os
home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
print("active HERMES_HOME:", home)
```

## OpenClaw path resolution

`OPENCLAW_STATE_DIR` defaults to `~/.openclaw`. The `openclaw.json` lives
at `$OPENCLAW_STATE_DIR/openclaw.json`. With named profiles:

```
$OPENCLAW_STATE_DIR/openclaw.json
$OPENCLAW_STATE_DIR/openclaw-<profile>/openclaw.json
```

## Plugin tree

User-local plugins (the only durable tree):

```
~/.hermes/plugins/<plugin-name>/
├── __init__.py
└── plugin.yaml
```

In-repo plugins (clobbered on `hermes update`):

```
~/.hermes/hermes-agent/plugins/<name>/
```

## Memory provider configs

External memory providers (OpenViking, Honcho, Mem0, etc.) have
their own config files, profile-scoped:

- OpenViking: `~/.openviking/ov.conf` (env: `OPENVIKING_CONFIG_FILE`)
- Honcho: `~/.hermes/honcho.json` (env: `HOME`-relative)
- Mem0 / others: provider-specific, see each provider's README

The provider config is **separate from the main hermes config** —
to enable a provider you set `memory.provider: openviking` in
`~/.hermes/config.yaml`, but the provider's own auth + endpoint config
lives in its own file.
