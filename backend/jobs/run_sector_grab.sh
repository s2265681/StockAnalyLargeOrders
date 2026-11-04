#!/bin/bash
# 板块抢筹快照同步
cd "$(dirname "$0")/.." || exit 1
if [ -f .env ]; then
  set -a
  # shellcheck source=/dev/null
  . ./.env
  set +a
fi
if [ ! -x ./venv/bin/python ]; then
  echo "venv 不存在，请先在 backend 目录创建虚拟环境" >&2
  exit 1
fi
exec ./venv/bin/python jobs/sector_grab_sync.py "$@"
