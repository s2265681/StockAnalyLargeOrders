#!/bin/bash
# 龙虎榜离线任务：补全当日 AI + 删除 7 天前数据
# crontab（工作日 18:00）:
#   0 18 * * 1-5 /Users/mac/Github/NiuNIuNiu/backend/jobs/run_dragon_tiger.sh \
#     >> /Users/mac/Github/NiuNIuNiu/dragon_tiger_job.log 2>&1
# 用法:
#   run_dragon_tiger.sh              # 最新交易日补全 + 清理（crontab 推荐）
#   run_dragon_tiger.sh force        # 最新交易日强制重跑 + 清理
#   run_dragon_tiger.sh recent       # 近 5 日缺失补全 + 清理（手动）
#   run_dragon_tiger.sh sync 20260513 20260514  # 仅同步榜单，不跑 AI
#   run_dragon_tiger.sh 20260515 force

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

MODE="${1:-latest}"
LOG_DIR="$ROOT"
mkdir -p "$LOG_DIR"

case "$MODE" in
  sync)
    shift
    exec ./venv/bin/python jobs/dragon_tiger_sync_daily.py "$@"
    ;;
  recent)
    FORCE="${2:-}"
    if [ "$FORCE" = "force" ]; then
      exec ./venv/bin/python jobs/dragon_tiger_ai_recent.py force
    fi
    exec ./venv/bin/python jobs/dragon_tiger_ai_recent.py
    ;;
  force)
    exec ./venv/bin/python jobs/dragon_tiger_ai_daily.py force
    ;;
  latest|"")
    exec ./venv/bin/python jobs/dragon_tiger_ai_daily.py
    ;;
  *)
    if [[ "$MODE" =~ ^[0-9]{8}$ ]]; then
      FORCE="${2:-force}"
      exec ./venv/bin/python jobs/dragon_tiger_ai_daily.py "$MODE" "$FORCE"
    fi
    echo "未知参数: $MODE (可用: latest | force | recent | YYYYMMDD [force])" >&2
    exit 1
    ;;
esac
