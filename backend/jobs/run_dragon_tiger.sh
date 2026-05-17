#!/bin/bash
# 龙虎榜离线任务：补全当日 AI
# 用法:
#   run_dragon_tiger.sh              # 最新交易日（cron）
#   run_dragon_tiger.sh force
#   run_dragon_tiger.sh recent [force]
#   run_dragon_tiger.sh sync DATE...
#   run_dragon_tiger.sh YYYYMMDD [force]

set -euo pipefail
JOB_NAME=dragon_tiger
# shellcheck source=job_lib.sh
source "$(dirname "$0")/job_lib.sh"
job_setup

MODE="${1:-latest}"

if [ "$MODE" = "latest" ] || [ -z "$MODE" ]; then
  job_skip_if_not_trading_day
  job_acquire_lock dragon_tiger
  if "$PYTHON" -c "
import sys
sys.path.insert(0, '.')
from routes.dragon_tiger import is_dragon_tiger_ai_complete
from utils.date_utils import get_valid_trading_date
dt = get_valid_trading_date().replace('-', '')
sys.exit(0 if is_dragon_tiger_ai_complete(dt) else 1)
" 2>/dev/null; then
    echo "$(date '+%F %T') 龙虎榜 AI 已齐全，跳过"
    exit 0
  fi
  job_run "$PYTHON" jobs/dragon_tiger_ai_daily.py
fi

job_acquire_lock dragon_tiger

case "$MODE" in
  sync)
    shift
    job_run "$PYTHON" jobs/dragon_tiger_sync_daily.py "$@"
    ;;
  recent)
    FORCE="${2:-}"
    if [ "$FORCE" = "force" ]; then
      job_run "$PYTHON" jobs/dragon_tiger_ai_recent.py force
    fi
    job_run "$PYTHON" jobs/dragon_tiger_ai_recent.py
    ;;
  force)
    job_run "$PYTHON" jobs/dragon_tiger_ai_daily.py force
    ;;
  *)
    if [[ "$MODE" =~ ^[0-9]{8}$ ]]; then
      FORCE="${2:-force}"
      job_run "$PYTHON" jobs/dragon_tiger_ai_daily.py "$MODE" "$FORCE"
    fi
    echo "未知参数: $MODE (可用: latest | force | recent | YYYYMMDD [force])" >&2
    exit 1
    ;;
esac
