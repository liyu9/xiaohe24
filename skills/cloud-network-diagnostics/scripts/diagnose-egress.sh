#!/usr/bin/env bash
# diagnose-egress.sh — Re-runnable 7-layer network diagnostic
# Usage: ./diagnose-egress.sh [target_host] [target_port]
# Default: github.com:443
# Exit codes: 0 = all layers OK, 1+ = failing layer (see output)

set -u
TARGET="${1:-github.com}"
PORT="${2:-443}"
HUMAN_UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

bar() { printf '\n=== %s ===\n' "$1"; }
note() { printf '  %s\n' "$1"; }

bar "1/7 DNS"
if RESOLVED=$(getent hosts "$TARGET" 2>/dev/null | awk '{print $1}' | head -1); then
  note "resolved: $TARGET -> $RESOLVED"
else
  note "FAIL: DNS resolution failed for $TARGET"
  exit 1
fi

bar "2/7 Local firewall (OUTPUT chain)"
if command -v sudo >/dev/null 2>&1 && sudo -n iptables -L OUTPUT -n >/dev/null 2>&1; then
  RULES=$(sudo -n iptables -L OUTPUT -n 2>/dev/null)
  if echo "$RULES" | grep -qE 'REJECT|DROP'; then
    note "WARNING: OUTPUT chain has REJECT/DROP rules"
    echo "$RULES" | head -10 | sed 's/^/    /'
  else
    note "OUTPUT chain: ACCEPT (no block rules)"
  fi
else
  note "sudo unavailable or no nopasswd — skipping local firewall check"
fi

bar "3/7 Routing"
ip route show default 2>/dev/null | sed 's/^/  /'

bar "4/7 Egress IP (who does the public internet see?)"
for svc in api.ipify.org ifconfig.me; do
  IP=$(curl -sf --connect-timeout 5 "https://$svc" 2>/dev/null | tr -d '\n')
  [ -n "$IP" ] && note "$svc: $IP" && break
done
[ -z "${IP:-}" ] && note "could not determine egress IP"

bar "5/7 TCP handshake to $TARGET:$PORT"
(
  (echo > /dev/tcp/"$TARGET"/"$PORT") 2>/dev/null
  echo "TCP_PORT_OPEN"
) &
TCP_PID=$!
sleep 5
kill -0 $TCP_PID 2>/dev/null && { note "FAIL: TCP did not open within 5s"; kill $TCP_PID 2>/dev/null; } || note "TCP port reachable"

bar "6/7 TLS + HTTP (GET with real User-Agent)"
TMPBODY=$(mktemp)
HTTP_CODE=$(timeout 10 curl -s -o "$TMPBODY" -w '%{http_code}' -H "User-Agent: $HUMAN_UA" --connect-timeout 5 "https://$TARGET:$PORT/" 2>/dev/null || echo "000")
BODY_BYTES=$(stat -c%s "$TMPBODY" 2>/dev/null || echo 0)
note "HTTP status: $HTTP_CODE"
note "body bytes:  $BODY_BYTES"
if [ "$HTTP_CODE" = "000" ] || [ "$BODY_BYTES" -lt 100 ]; then
  note "WARNING: GET did not return a real response — try with -v to see TLS detail"
fi
rm -f "$TMPBODY"

bar "7/7 mtr path (5 ICMP probes, no root required)"
if command -v mtr >/dev/null 2>&1; then
  timeout 12 mtr -n -r -c 3 "$TARGET" 2>&1 | head -15 | sed 's/^/  /'
else
  note "mtr not installed — skipping path trace"
fi

bar "Diagnostic complete"
note "For deep-dive TLS, use:  curl -v -H 'User-Agent: $HUMAN_UA' https://$TARGET:$PORT/ 2>&1 | head -40"
note "For TCP-mode mtr (needs root):  sudo mtr -T -P $PORT -n -r -c 5 $TARGET"
