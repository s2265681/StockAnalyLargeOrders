#!/bin/bash
# 盘中刷新：梯队 + 情绪周期 + 买卖指导（强制覆盖当日）

set -euo pipefail
JOB_NAME=intraday
# shellcheck source=job_lib.sh
source "$(dirname "$0")/job_lib.sh"
job_setup
job_skip_if_not_trading_day
job_acquire_lock intraday
# 情绪周期/买卖指导改由 run_emotion_intraday.sh 每小时刷新，这里只刷梯队
export INTRADAY_EMOTION_REFRESH=0
job_run "$PYTHON" jobs/intraday_refresh.py
