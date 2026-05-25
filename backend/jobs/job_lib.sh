# shellcheck shell=bash
# 定时任务公共逻辑（由 run_*.sh source）

job_setup() {
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  BACKEND="$ROOT/backend"
  LOG_DIR="$ROOT/logs"
  mkdir -p "$LOG_DIR"
  cd "$BACKEND"

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

  PYTHON="./venv/bin/python"
  export JOB_NAME="${JOB_NAME:-unknown}"
  export JOB_LOG_FILE="${JOB_LOG_FILE:-$LOG_DIR/${JOB_NAME}_job.log}"
}

# 休市日退出 0；返回 2 表示跳过
job_skip_if_not_trading_day() {
  set +e
  "$PYTHON" jobs/job_guard.py
  local rc=$?
  set -e
  if [ "$rc" -eq 2 ]; then
    echo "$(date '+%F %T') [$JOB_NAME] 今日休市，跳过"
    exit 0
  fi
  if [ "$rc" -ne 0 ]; then
    echo "$(date '+%F %T') [$JOB_NAME] 交易日检查失败 rc=$rc" >&2
    job_on_failure "$rc" "交易日检查异常"
    exit "$rc"
  fi
}

job_acquire_lock() {
  local lock_name="${1:-$JOB_NAME}"
  local lock_file="$LOG_DIR/.${lock_name}.lock"
  exec 9>"$lock_file"
  if ! flock -n 9; then
    echo "$(date '+%F %T') [$JOB_NAME] 仍在运行，跳过本次"
    exit 0
  fi
}

job_on_failure() {
  local rc="${1:-1}"
  local detail="${2:-}"
  export JOB_DURATION_SECS="${JOB_DURATION_SECS:-0}"
  set +e
  if [ -n "$detail" ]; then
    JOB_DURATION_SECS="$JOB_DURATION_SECS" "$PYTHON" -c "
from utils.job_notify import send_job_alert
send_job_alert('${JOB_NAME}', exit_code=${rc}, detail='''${detail}''')
"
  else
    JOB_DURATION_SECS="$JOB_DURATION_SECS" "$PYTHON" jobs/job_notify_failure.py "$JOB_NAME" "$rc" "$JOB_LOG_FILE"
  fi
  set -e
}

job_on_success() {
  local detail="${1:-}"
  if [ "${JOB_NOTIFY_ON_SUCCESS:-1}" = "0" ]; then
    return 0
  fi
  export JOB_DURATION_SECS="${JOB_DURATION_SECS:-0}"
  set +e
  JOB_DURATION_SECS="$JOB_DURATION_SECS" "$PYTHON" jobs/job_notify_success.py "$JOB_NAME" "$detail" "$JOB_LOG_FILE"
  set -e
}

job_run() {
  local timeout_sec="${JOB_TIMEOUT_SEC:-1800}"
  local start_ts
  start_ts=$(date +%s)
  set +e
  timeout --signal=TERM --kill-after=15s "$timeout_sec" "$@"
  local rc=$?
  set -e
  export JOB_DURATION_SECS=$(( $(date +%s) - start_ts ))
  if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
    echo "$(date '+%F %T') [$JOB_NAME] 超时强杀 timeout=${timeout_sec}s rc=$rc" >&2
    job_on_failure "$rc" "执行超过 ${timeout_sec}s 被强制终止"
    exit "$rc"
  fi
  if [ "$rc" -ne 0 ]; then
    echo "$(date '+%F %T') [$JOB_NAME] 失败 exit=$rc 耗时=${JOB_DURATION_SECS}s" >&2
    job_on_failure "$rc"
    exit "$rc"
  fi
  job_on_success ""
}
