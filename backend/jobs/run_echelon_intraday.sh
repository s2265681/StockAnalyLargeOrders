#!/bin/bash
# 涨停梯队盘中高频刷新（只跑梯队，不跑情绪周期/买卖指导）

set -euo pipefail
JOB_NAME=echelon_intraday
# shellcheck source=job_lib.sh
source "$(dirname "$0")/job_lib.sh"
job_setup
job_skip_if_not_trading_day
job_acquire_lock echelon_intraday
job_run "$PYTHON" jobs/echelon_intraday.py
