#!/bin/bash
# 情绪周期研判定时任务入口
# 用法:
#   run_emotion_cycle.sh           # 仅生成最新交易日（analyze_one_date）
#   run_emotion_cycle.sh recent        # 强制重跑最近 3 天周期研判
#   run_emotion_cycle.sh daily-recent   # 强制重跑最近 3 天当天分析
#   run_emotion_cycle.sh daily-backfill # 正序补全全部缺失的当天分析
#   run_emotion_cycle.sh backfill       # 强制全量批量补全周期研判

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"

if [ ! -d "venv" ]; then
  echo "venv 不存在，请先在 backend 目录创建虚拟环境" >&2
  exit 1
fi

MODE="${1:-latest}"
LOG_DIR="$ROOT"
mkdir -p "$LOG_DIR"

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
  latest|"")
    exec ./venv/bin/python jobs/emotion_cycle_daily.py
    ;;
  *)
    echo "未知模式: $MODE (可用: latest | recent | daily-recent | daily-backfill | backfill)" >&2
    exit 1
    ;;
esac
