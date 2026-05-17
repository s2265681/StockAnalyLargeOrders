#!/bin/bash
# 涨停梯队离线任务（收盘后 16:00 强制重跑写库）
# crontab（工作日 16:00）:
#   0 16 * * 1-5 /Users/mac/Github/NiuNIuNiu/backend/jobs/run_echelon.sh force \
#     >> /Users/mac/Github/NiuNIuNiu/echelon_job.log 2>&1
# 用法:
#   run_echelon.sh           # 最新交易日，有缓存则跳过
#   run_echelon.sh force     # 最新交易日强制重跑（crontab 推荐）

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"

if [ ! -d "venv" ]; then
  echo "venv 不存在，请先在 backend 目录创建虚拟环境" >&2
  exit 1
fi

if [ -f .env ]; then
  set -a
  # shellcheck source=/dev/null
  . ./.env
  set +a
fi

MODE="${1:-force}"
LOG_DIR="$ROOT"
mkdir -p "$LOG_DIR"

case "$MODE" in
  force)
    exec ./venv/bin/python jobs/echelon_daily.py force
    ;;
  latest|"")
    exec ./venv/bin/python jobs/echelon_daily.py
    ;;
  *)
    if [[ "$MODE" =~ ^[0-9]{8}$ ]]; then
      exec ./venv/bin/python jobs/echelon_daily.py "$MODE" force
    fi
    echo "未知参数: $MODE (可用: force | YYYYMMDD)" >&2
    exit 1
    ;;
esac
