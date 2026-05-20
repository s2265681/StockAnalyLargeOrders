#!/usr/bin/env bash
# 部署用：先关闭 9001 上所有进程，再只启动一个 PM2 后端
set -euo pipefail

PORT="${PORT:-9001}"
APP_NAME="${PM2_APP_NAME:-StockAnalysisLargeOrders}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/www/StockAnalyLargeOrders}"
REQUIRED_OK="${REQUIRED_OK:-5}"
MAX_WAIT_SEC="${MAX_WAIT_SEC:-90}"

cd "$DEPLOY_ROOT"

free_port() {
  echo "===> [free_port] release :${PORT}"

  echo "    stop & delete PM2 app: ${APP_NAME}"
  pm2 stop "$APP_NAME" 2>/dev/null || true
  pm2 delete "$APP_NAME" 2>/dev/null || true

  # 避免 start.sh / nohup 残留
  if pgrep -f "${DEPLOY_ROOT}/backend/.*app\.py" >/dev/null 2>&1; then
    echo "    kill stray app.py under ${DEPLOY_ROOT}/backend"
    pkill -f "${DEPLOY_ROOT}/backend/.*app\.py" 2>/dev/null || true
    sleep 1
  fi

  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids=$(lsof -ti:"${PORT}" 2>/dev/null || true)
    if [ -n "${pids}" ]; then
      echo "    SIGTERM PIDs on :${PORT}: ${pids}"
      # shellcheck disable=SC2086
      kill ${pids} 2>/dev/null || true
      sleep 2
    fi
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
    sleep 1
  fi

  if command -v lsof >/dev/null 2>&1; then
    local left
    left=$(lsof -ti:"${PORT}" 2>/dev/null || true)
    if [ -n "${left}" ]; then
      echo "    SIGKILL remaining on :${PORT}: ${left}"
      # shellcheck disable=SC2086
      kill -9 ${left} 2>/dev/null || true
      sleep 1
    fi
  fi

  if command -v lsof >/dev/null 2>&1 && lsof -i:"${PORT}" >/dev/null 2>&1; then
    echo "ERROR: port ${PORT} still in use:"
    lsof -i:"${PORT}" || true
    return 1
  fi

  echo "    port ${PORT} is free"
}

start_backend() {
  echo "===> [start_backend] pm2 start ${APP_NAME}"
  pm2 start ecosystem.config.js --only "$APP_NAME"
  pm2 save 2>/dev/null || true
}

wait_healthy() {
  local health_url="http://127.0.0.1:${PORT}/health"
  echo "===> [wait_healthy] ${REQUIRED_OK}x consecutive OK: ${health_url}"
  local consecutive=0
  local deadline=$((SECONDS + MAX_WAIT_SEC))
  while [ "$SECONDS" -lt "$deadline" ]; do
    local body
    body=$(curl -fsS "$health_url" 2>/dev/null || true)
    if echo "$body" | grep -q '"alert_rules"[[:space:]]*:[[:space:]]*true'; then
      consecutive=$((consecutive + 1))
      echo "  health OK (${consecutive}/${REQUIRED_OK})"
      if [ "$consecutive" -ge "$REQUIRED_OK" ]; then
        echo "===> [ensure_single_backend] done"
        lsof -i:"${PORT}" 2>/dev/null || true
        return 0
      fi
    else
      if [ -n "$body" ]; then
        echo "  not ready: ${body}"
      else
        echo "  unreachable, retry..."
      fi
      consecutive=0
    fi
    sleep 2
  done
  return 1
}

free_port
start_backend
wait_healthy || {
  echo "===> [ensure_single_backend] FAILED"
  pm2 status "$APP_NAME" || true
  pm2 logs "$APP_NAME" --lines 50 --nostream || true
  lsof -i:"${PORT}" 2>/dev/null || true
  exit 1
}
