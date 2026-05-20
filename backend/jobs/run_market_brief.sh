#!/bin/bash
# 盘前资讯定时任务：每日 8:30 生成海外指数 + AI 摘要
set -euo pipefail
JOB_NAME=market_brief
# shellcheck source=job_lib.sh
source "$(dirname "$0")/job_lib.sh"
job_setup
job_skip_if_not_trading_day
job_acquire_lock market_brief
# 盘前邮件由 market_brief_daily.py 发送完整正文，避免与通用成功邮件重复
export JOB_NOTIFY_ON_SUCCESS=0
job_run "$PYTHON" jobs/market_brief_daily.py
