#!/usr/bin/env bash
# probe_tool_actions.sh — verify which actions a gateway tool actually implements
#
# Usage: probe_tool_actions.sh <tool_name> [action1 action2 ...]
# e.g. probe_tool_actions.sh feishu_chat send_message list_members info member_info
#
# If no actions are given, prompts for them on stdin (one per line, blank line to end).
# Prints one line per action: "<action> -> <response>" with the full gateway reply inline.
# Exit code is0 regardless of whether the action exists — this is a probe, not a gate.
#
# Read the plugin's source (e.g. node_modules/@openclaw/feishu/dist/*.js) for ground
# truth when the probe is ambiguous. See "Probe-before-bet" in SKILL.md.

set -u

TOOL="${1:?usage: $0 <tool_name> [actions...]}"
shift

URL="${OPENCLAW_GATEWAY_URL:-http://127.0.0.1:18789}"
TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"

if [[ $# -eq0 ]]; then
 echo "Enter actions to probe (one per line, blank line to end):"
 while IFS= read -r line; do
 [[ -z "$line" ]] && break
 set -- "$@" "$line"
 done
fi

if [[ $# -eq0 ]]; then
 echo "no actions given" >&2
 exit2
fi

for a in "$@"; do
 printf "%-22s -> " "$a"
 curl -sS -m5 -X POST "$URL/tools/invoke" \
 -H "Content-Type: application/json" \
 -H "Authorization: Bearer $TOKEN" \
 -d "{\"name\":\"$TOOL\",\"args\":{\"action\":\"$a\"}}"
 echo ""
done
