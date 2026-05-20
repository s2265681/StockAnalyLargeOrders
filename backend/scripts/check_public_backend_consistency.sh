#!/usr/bin/env bash
# 从本机探测公网入口是否混有新旧后端（用于排查 SLB 多机未同步）
set -euo pipefail

BASE_URL="${1:-http://47.99.130.21}"
TRIES="${TRIES:-20}"

ok=0
old=0
codes_404=0
codes_401=0

echo "Probing ${BASE_URL} (${TRIES} requests)..."

for i in $(seq 1 "$TRIES"); do
  body=$(curl -s --connect-timeout 3 "${BASE_URL}/health" 2>/dev/null || echo "")
  if echo "$body" | grep -q '"alert_rules"[[:space:]]*:[[:space:]]*true'; then
    ok=$((ok + 1))
  else
    old=$((old + 1))
  fi
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "${BASE_URL}/api/alert-rules" 2>/dev/null || echo "000")
  if [ "$code" = "404" ]; then codes_404=$((codes_404 + 1)); fi
  if [ "$code" = "401" ]; then codes_401=$((codes_401 + 1)); fi
done

echo "health: new=${ok} old=${old}"
echo "GET /api/alert-rules (no auth): 401=${codes_401} 404=${codes_404}"

if [ "$old" -gt 0 ] || [ "$codes_404" -gt 0 ]; then
  echo "FAIL: mixed backends or missing alert-rules route."
  echo "On server: bash backend/scripts/ensure_single_backend.sh"
  echo "If SLB has multiple ECS, deploy/restart every node."
  exit 1
fi

echo "OK: all samples hit new backend."
