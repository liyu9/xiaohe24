#!/bin/bash
# Diagnose why `hermes mcp test <name>` is failing.
#
# Usage:  bash scripts/mcp_diagnose.sh [server-name]
#         (default server-name: MiniMax)
#
# Walks through the four most common failure modes for stdio MCP servers
# in this environment and reports which one is biting you.

set -u

SERVER="${1:-MiniMax}"
CONFIG="$HOME/.hermes/config.yaml"
ENV_FILE="$HOME/.hermes/.env"

echo "== Diagnose: $SERVER =="
echo

# 1. Does the server even exist in config?
echo "[1/4] Looking up mcp_servers.$SERVER in $CONFIG ..."
if ! grep -q "  $SERVER:" "$CONFIG"; then
  echo "  ✗ NOT FOUND. Run: hermes mcp add $SERVER --command <cmd> --env KEY=VAL"
  exit 1
fi
echo "  ✓ Found"
echo

# 2. Pull the configured command + env keys
COMMAND=$(awk "/^  $SERVER:/{flag=1; next} flag && /command:/{print \$2; exit}" "$CONFIG")
ENV_KEYS=$(awk "/^  $SERVER:/{flag=1} flag && /^      [A-Z_]+: /{print \$1}" "$CONFIG" | tr -d ':' | head)
echo "[2/4] command = $COMMAND"
echo "     env vars = $ENV_KEYS"
echo

# 3. Reproduce the server invocation outside hermes, see the real stderr
echo "[3/4] Reproducing command outside hermes (5s timeout) ..."
ENV_PREFIX=""
for key in $ENV_KEYS; do
  val=$(grep "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)
  if [ -n "$val" ]; then
    ENV_PREFIX="$ENV_PREFIX $key=$val"
  else
    echo "  ⚠ $key is referenced in $SERVER.env but NOT in $ENV_FILE"
  fi
done
echo "  running: $COMMAND"
echo "  with env: $ENV_PREFIX"
echo "  ---- server stderr/stdout below ----"
env $ENV_PREFIX timeout 5 "$COMMAND" </dev/null 2>&1 | head -20
RC=$?
echo "  ---- (exit code: $RC) ----"
echo
if [ $RC -eq 124 ]; then
  echo "  ⇒ server waited for stdin = good; hermes should connect on the next test"
elif [ $RC -ne 0 ]; then
  echo "  ⇒ server crashed. Look at the traceback above."
  echo "    Common fixes:"
  echo "      - ModuleNotFoundError → venv missing the package; reinstall into the venv"
  echo "      - dotenv not found     → venv missing deps; reinstall WITHOUT --no-deps"
  echo "      - KeyError on env var  → check the env block keys match what the server reads"
fi
echo

# 4. Validate upstream API is reachable (best-effort; MiniMax-specific)
echo "[4/4] Probing upstream API directly ..."
API_KEY=$(grep '^MINIMAX_API_KEY=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | head -1)
if [ -n "$API_KEY" ]; then
  HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
    "https://api.minimaxi.com/v1/coding_plan/search" \
    -H "Authorization: Bearer $API_KEY" \
    -H "MM-API-Source: Minimax-MCP" \
    -H "Content-Type: application/json" \
    -d '{"q": "ping"}')
  if [ "$HTTP_CODE" = "200" ]; then
    echo "  ✓ Upstream API returns 200 (upstream is fine; problem is on the MCP transport)"
  else
    echo "  ✗ Upstream returned $HTTP_CODE (problem is on the API side: bad key, scope, or quota)"
  fi
else
  echo "  ⚠ No MINIMAX_API_KEY in $ENV_FILE; skipping upstream probe"
fi
echo

echo "Next steps:"
echo "  - If step 3 showed a traceback, fix that first."
echo "  - If step 3 was silent and step 4 was 200, run:"
echo "      hermes mcp test $SERVER"
echo "    from a fresh terminal (avoid the 30s auto-reload race)."
