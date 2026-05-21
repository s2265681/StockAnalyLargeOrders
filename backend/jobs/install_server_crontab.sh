#!/bin/bash
# 在服务器安装 NiuNIuNiu 定时任务 + logrotate
set -euo pipefail

ROOT="${NIU_ROOT:-/www/StockAnalyLargeOrders}"
if [ -d "$(cd "$(dirname "$0")/../.." && pwd)" ]; then
  ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fi

TEMPLATE="$ROOT/backend/jobs/crontab.server.txt"
MARKER="# NiuNIuNiu server jobs"
LOGROTATE_SRC="$ROOT/deploy/logrotate-niuniuniu.conf"
TMP="$(mktemp)"

chmod +x "$ROOT/backend/jobs/run_"*.sh "$ROOT/backend/jobs/install_"*.sh 2>/dev/null || true
mkdir -p "$ROOT/logs"

NIU_LOG="$ROOT/logs"
sed "s|\${NIU_ROOT}|$ROOT|g; s|\${NIU_LOG}|$NIU_LOG|g" "$TEMPLATE" > "$TMP.block"

KEEP=""
if crontab -l >/dev/null 2>&1; then
  KEEP="$(crontab -l \
    | grep -v '/backend/jobs/run_' \
    | grep -vF '# NiuNIuNiu local jobs' \
    | grep -vF "$MARKER" \
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

if [ -f "$LOGROTATE_SRC" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    cp "$LOGROTATE_SRC" /etc/logrotate.d/niuniuniu
    echo "已安装 logrotate -> /etc/logrotate.d/niuniuniu"
  else
    sudo cp "$LOGROTATE_SRC" /etc/logrotate.d/niuniuniu 2>/dev/null \
      && echo "已安装 logrotate -> /etc/logrotate.d/niuniuniu" \
      || echo "请手动: sudo cp $LOGROTATE_SRC /etc/logrotate.d/niuniuniu"
  fi
fi

echo "已安装服务器 crontab [$MARKER]"
crontab -l | grep -F "$MARKER" -A20
