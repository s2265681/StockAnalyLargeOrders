#!/bin/bash
# 竞价抢筹快照同步
# 用法: run_auction_grab.sh [all|morning|tail]

set -euo pipefail
JOB_NAME=auction_grab
# shellcheck source=job_lib.sh
source "$(dirname "$0")/job_lib.sh"
job_setup
job_skip_if_not_trading_day
job_acquire_lock auction_grab

MODE="${1:-all}"
job_run "$PYTHON" jobs/auction_grab_sync.py "$MODE"
