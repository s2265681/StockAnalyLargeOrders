#!/bin/bash
# 板块抢筹快照同步
cd "$(dirname "$0")/.." || exit 1
exec python3 jobs/sector_grab_sync.py "$@"
