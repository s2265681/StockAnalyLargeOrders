#!/bin/bash
# 本地开发：SSH 隧道连接服务器 MySQL
# 用法: ./scripts/db-tunnel.sh [start|stop|status]
# 默认: 本机 3307 -> 服务器 127.0.0.1:3306（与 backend/.env 一致）

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/logs/.db-tunnel.pid"

# 可覆盖：scripts/local.deploy.env 或环境变量
if [ -f "$ROOT/scripts/local.deploy.env" ]; then
  # shellcheck source=/dev/null
  . "$ROOT/scripts/local.deploy.env"
fi

SERVER_HOST="${SERVER_HOST:-47.99.130.21}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_PORT="${SERVER_PORT:-22}"
LOCAL_PORT="${LOCAL_DB_PORT:-3307}"
REMOTE_HOST="${REMOTE_DB_HOST:-127.0.0.1}"
REMOTE_PORT="${REMOTE_DB_PORT:-3306}"
SSH_KEY="${SSH_KEY:-}"
SSH_PASSWORD="${SSH_PASSWORD:-}"

_ssh_args=(-p "$SERVER_PORT" -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new)
if [ -n "$SSH_KEY" ]; then
  _ssh_args+=(-i "$SSH_KEY")
fi

_run_ssh() {
  if [ -n "$SSH_PASSWORD" ] && [ -z "$SSH_KEY" ]; then
    if ! command -v sshpass >/dev/null 2>&1; then
      echo "❌ 需要 sshpass 才能使用密码登录: brew install sshpass 或 brew install hudochenkov/sshpass/sshpass" >&2
      exit 1
    fi
    SSHPASS="$SSH_PASSWORD" sshpass -e ssh "$@"
  else
    ssh "$@"
  fi
}

_tunnel_running() {
  nc -z 127.0.0.1 "$LOCAL_PORT" 2>/dev/null
}

_start() {
  if _tunnel_running; then
    echo "✅ 数据库隧道已在运行: 127.0.0.1:${LOCAL_PORT} -> ${SERVER_USER}@${SERVER_HOST}:${REMOTE_PORT}"
    return 0
  fi

  mkdir -p "$ROOT/logs"
  echo "🔗 建立 SSH 隧道: 127.0.0.1:${LOCAL_PORT} -> ${SERVER_USER}@${SERVER_HOST}:${REMOTE_HOST}:${REMOTE_PORT}"

  _run_ssh "${_ssh_args[@]}" -f -N \
    -L "${LOCAL_PORT}:${REMOTE_HOST}:${REMOTE_PORT}" \
    "${SERVER_USER}@${SERVER_HOST}"

  sleep 1
  if _tunnel_running; then
    echo "✅ 隧道已就绪，backend/.env 使用 MYSQL_HOST=127.0.0.1 MYSQL_PORT=${LOCAL_PORT}"
  else
    echo "❌ 隧道启动失败，请检查 ${SERVER_USER}@${SERVER_HOST} 的 SSH 凭据" >&2
    echo "   可在 scripts/local.deploy.env 中设置 SSH_PASSWORD 或 SSH_KEY" >&2
    exit 1
  fi
}

_stop() {
  if [ -f "$PID_FILE" ]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi

  # 按端口查找 ssh -L 进程
  pids="$(lsof -t -iTCP:"$LOCAL_PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "${pids:-}" ]; then
    echo "$pids" | xargs kill 2>/dev/null || true
    echo "🛑 已关闭 127.0.0.1:${LOCAL_PORT} 隧道"
  else
    echo "ℹ️  未发现运行中的隧道 (port ${LOCAL_PORT})"
  fi
}

_status() {
  if _tunnel_running; then
    echo "✅ 隧道运行中: 127.0.0.1:${LOCAL_PORT} -> ${SERVER_USER}@${SERVER_HOST}:${REMOTE_PORT}"
  else
    echo "❌ 隧道未运行。执行: ./scripts/db-tunnel.sh start"
    exit 1
  fi
}

case "${1:-start}" in
  start) _start ;;
  stop) _stop ;;
  status) _status ;;
  *)
    echo "用法: $0 [start|stop|status]" >&2
    exit 1
    ;;
esac
