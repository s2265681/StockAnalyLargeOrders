#!/bin/bash
# 情绪周期研判定时任务入口
# 用法:
#   run_emotion_cycle.sh              # cron：最新交易日周期研判（job_lib 交易日+锁）
#   run_emotion_cycle.sh recent         # 强制重跑最近 3 天周期研判
#   run_emotion_cycle.sh daily-recent   # 强制重跑最近 3 天当天分析
#   run_emotion_cycle.sh daily-backfill # 正序补全全部缺失的当天分析
#   run_emotion_cycle.sh backfill       # 强制全量批量补全周期研判

set -euo pipefail
MODE="${1:-latest}"

if [ "$MODE" = "latest" ] || [ "$MODE" = "" ]; then
  JOB_NAME=emotion_cycle
  # shellcheck source=job_lib.sh
  source "$(dirname "$0")/job_lib.sh"
  job_setup
  job_skip_if_not_trading_day
  job_acquire_lock emotion_cycle
  job_run "$PYTHON" jobs/emotion_cycle_daily.py
  exit 0
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"

if [ ! -d "venv" ]; then
  echo "venv 不存在，请先在 backend 目录创建虚拟环境" >&2
  exit 1
fi

case "$MODE" in
  recent)
    exec ./venv/bin/python jobs/emotion_cycle_recent.py
    ;;
  daily-recent)
    exec ./venv/bin/python jobs/emotion_daily_analysis_recent.py
    ;;
  daily-backfill)
    exec ./venv/bin/python jobs/backfill_emotion_daily_analysis.py
    ;;
  backfill)
    exec ./venv/bin/python jobs/backfill_emotion_cycle_batch.py force
    ;;
  *)
    echo "未知模式: $MODE (可用: latest | recent | daily-recent | daily-backfill | backfill)" >&2
    exit 1
    ;;
esac
