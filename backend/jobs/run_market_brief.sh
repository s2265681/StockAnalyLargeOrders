#!/bin/bash
# 盘前资讯定时任务：每日 8:30 生成海外指数 + AI 摘要
set -euo pipefail
JOB_NAME=market_brief
# shellcheck source=job_lib.sh
source "$(dirname "$0")/job_lib.sh"
job_setup
job_skip_if_not_trading_day
job_acquire_lock market_brief
job_run "$PYTHON" jobs/market_brief_daily.py
