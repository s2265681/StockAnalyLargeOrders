#!/bin/bash
# 移除本机 NiuNIuNiu 定时任务（改用服务器时执行）
set -euo pipefail
MARKER="# NiuNIuNiu local jobs"
TMP="$(mktemp)"
if ! crontab -l >/dev/null 2>&1; then
  echo "无 crontab"
  exit 0
fi
crontab -l \
  | grep -v 'NiuNIuNiu/backend/jobs/run_' \
  | grep -vF "$MARKER" \
  | sed '/^[[:space:]]*$/d' > "$TMP" || true
crontab "$TMP"
rm -f "$TMP"
echo "已移除本机 NiuNIuNiu 定时任务"
