#!/bin/bash
# Wrapper for minimax-coding-plan-mcp
# Use venv python (has all deps: minimax_mcp, dotenv, mcp, etc.)
# Path: ~/.hermes/mcp/feishu-card/venv/bin/python
# Managed by Hermes setup; do not delete
exec /home/ubuntu/.hermes/mcp/feishu-card/venv/bin/python -c "from minimax_mcp.server import main; main()" "$@"
