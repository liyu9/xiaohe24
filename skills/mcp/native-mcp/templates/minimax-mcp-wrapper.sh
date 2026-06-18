#!/bin/bash
# Wrapper for minimax-coding-plan-mcp.
#
# Why this exists: the package's bin/<entry> uses #!/usr/bin/python3
# (system python) which can't see the venv's site-packages. Calling
# the entry directly fails with "ModuleNotFoundError: No module named
# 'minimax_mcp'" the moment the server tries to import its own package.
#
# Use: register this wrapper as the `command` in mcp_servers.MiniMax,
# point the venv path at wherever `uv venv` created the env.
#
# Set MINIMAX_VENV_PATH before registering, e.g.:
#   export MINIMAX_VENV_PATH=/home/ubuntu/.hermes/mcp/minimax-venv
#   cp templates/minimax-mcp-wrapper.sh /home/ubuntu/.hermes/mcp/minimax-server.sh
#   chmod +x /home/ubuntu/.hermes/mcp/minimax-server.sh

set -e
VENV_PATH="${MINIMAX_VENV_PATH:-/home/ubuntu/.hermes/mcp/minimax-venv}"
PY="${VENV_PATH}/bin/python"

if [ ! -x "$PY" ]; then
  echo "minimax-mcp-wrapper: venv python not found at $PY" >&2
  echo "Did you run:  uv venv $VENV_PATH && uv pip install --python $PY minimax-coding-plan-mcp" >&2
  exit 1
fi

exec "$PY" -c "from minimax_mcp.server import main; main()" "$@"
