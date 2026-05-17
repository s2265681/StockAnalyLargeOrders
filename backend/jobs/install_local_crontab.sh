#!/bin/bash
# 合并安装 NiuNIuNiu 本地 crontab（保留其它条目，替换本项目旧行）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$ROOT/backend/jobs/crontab.local.txt"
MARKER="# NiuNIuNiu local jobs"
# 本地开发用；生产请用 install_server_crontab.sh
TMP="$(mktemp)"

chmod +x "$ROOT/backend/jobs/run_intraday.sh" \
  "$ROOT/backend/jobs/run_auction_grab.sh" \
  "$ROOT/backend/jobs/run_dragon_tiger.sh" \
  "$ROOT/backend/jobs/run_echelon.sh" \
  "$ROOT/backend/jobs/run_emotion_cycle.sh" 2>/dev/null || true

mkdir -p "$ROOT/logs"

NIU_LOG="$ROOT/logs"
sed "s|\${NIU_ROOT}|$ROOT|g; s|\${NIU_LOG}|$NIU_LOG|g" "$TEMPLATE" > "$TMP.block"

KEEP=""
if crontab -l >/dev/null 2>&1; then
  KEEP="$(crontab -l \
    | grep -v 'NiuNIuNiu/backend/jobs/run_' \
    | grep -vF '# NiuNIuNiu server jobs' \
    | grep -vF "$MARKER" \
    | grep -v '^NIU_ROOT=' \
    | grep -v '^NIU_LOG=' \
    | sed '/^[[:space:]]*$/d' \
    || true)"
fi

{
  [ -n "$KEEP" ] && printf '%s\n\n' "$KEEP"
  echo "$MARKER"
  grep -v '^#' "$TMP.block" | grep -v '^[[:space:]]*$'
} > "$TMP"

crontab "$TMP"
rm -f "$TMP" "$TMP.block"

echo "已安装本地 crontab [$MARKER]"
crontab -l | grep -F "$MARKER" -A20
