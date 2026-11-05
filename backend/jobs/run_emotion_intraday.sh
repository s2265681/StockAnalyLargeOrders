#!/bin/bash
# 开盘后先刷当日情绪周期（周期研判 + 当天买卖指导）
# 09:38 触发：保证当日数据在开盘后尽早可见；后续 intraday 各时段继续更新

set -euo pipefail
JOB_NAME=emotion_intraday
# shellcheck source=job_lib.sh
source "$(dirname "$0")/job_lib.sh"
job_setup
job_skip_if_not_trading_day
job_acquire_lock emotion_intraday
# 盘初快刷：单次较短超时；成功不单独发信，避免和 intraday 重复打扰
export JOB_TIMEOUT_SEC=900
export JOB_NOTIFY_ON_SUCCESS=0
job_run "$PYTHON" jobs/emotion_intraday.py
