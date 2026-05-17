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
  LOCKDIR="$LOG_DIR/.${lock_name}.lock"
  if ! mkdir "$LOCKDIR" 2>/dev/null; then
    echo "$(date '+%F %T') [$JOB_NAME] 仍在运行，跳过本次"
    exit 0
  fi
  trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT
}

job_on_failure() {
  local rc="${1:-1}"
  local detail="${2:-}"
  set +e
  if [ -n "$detail" ]; then
    "$PYTHON" -c "
from utils.job_notify import send_job_alert
send_job_alert('${JOB_NAME}', exit_code=${rc}, detail='''${detail}''')
"
  else
    "$PYTHON" jobs/job_notify_failure.py "$JOB_NAME" "$rc" "$JOB_LOG_FILE"
  fi
  set -e
}

job_run() {
  set +e
  "$@"
  local rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "$(date '+%F %T') [$JOB_NAME] 失败 exit=$rc" >&2
    job_on_failure "$rc"
    exit "$rc"
  fi
}
