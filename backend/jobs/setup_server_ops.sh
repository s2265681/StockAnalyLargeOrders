#!/bin/bash
# 服务器运维一次性/部署后脚本：Swap + crontab + logrotate
# 用法（需 root）: sudo bash backend/jobs/setup_server_ops.sh
# 仅 Swap: SWAP_SIZE_GB=2 sudo bash backend/jobs/setup_server_ops.sh --swap-only
# 仅 crontab: bash backend/jobs/setup_server_ops.sh --cron-only

set -euo pipefail

ROOT="${NIU_ROOT:-}"
if [ -z "$ROOT" ]; then
  ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fi

SWAP_SIZE_GB="${SWAP_SIZE_GB:-2}"
SWAP_FILE="${SWAP_FILE:-/swapfile}"
SWAPPINESS="${SWAPPINESS:-10}"
MARKER_FSTAB="$SWAP_FILE none swap sw 0 0"

RUN_SWAP=1
RUN_CRON=1
for arg in "$@"; do
  case "$arg" in
    --swap-only) RUN_CRON=0 ;;
    --cron-only) RUN_SWAP=0 ;;
    -h|--help)
      echo "用法: sudo bash backend/jobs/setup_server_ops.sh [--swap-only|--cron-only]"
      exit 0
      ;;
  esac
done

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 root 运行: sudo bash $0 $*" >&2
    exit 1
  fi
}

setup_swap() {
  require_root

  if swapon --show 2>/dev/null | awk '{print $1}' | grep -qx "$SWAP_FILE"; then
    echo "Swap 已启用: $SWAP_FILE"
  elif [ -f "$SWAP_FILE" ]; then
    echo "启用已有 swap 文件: $SWAP_FILE"
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" >/dev/null
    swapon "$SWAP_FILE"
  else
    echo "创建 ${SWAP_SIZE_GB}GB swap: $SWAP_FILE"
    if command -v fallocate >/dev/null 2>&1; then
      fallocate -l "${SWAP_SIZE_GB}G" "$SWAP_FILE"
    else
      dd if=/dev/zero of="$SWAP_FILE" bs=1M count=$((SWAP_SIZE_GB * 1024)) status=progress
    fi
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE"
    swapon "$SWAP_FILE"
  fi

  if ! grep -qF "$SWAP_FILE" /etc/fstab 2>/dev/null; then
    echo "$MARKER_FSTAB" >> /etc/fstab
    echo "已写入 /etc/fstab"
  fi

  sysctl -w "vm.swappiness=$SWAPPINESS" >/dev/null
  if ! grep -q '^vm.swappiness=' /etc/sysctl.conf 2>/dev/null; then
    echo "vm.swappiness=$SWAPPINESS" >> /etc/sysctl.conf
  else
    sed -i "s/^vm.swappiness=.*/vm.swappiness=$SWAPPINESS/" /etc/sysctl.conf
  fi

  echo "--- Swap 状态 ---"
  free -h | grep -E 'Mem|Swap'
  swapon --show
}

setup_crontab() {
  export NIU_ROOT="$ROOT"
  bash "$ROOT/backend/jobs/install_server_crontab.sh"
}

echo "项目目录: $ROOT"

if [ "$RUN_SWAP" -eq 1 ]; then
  setup_swap
fi

if [ "$RUN_CRON" -eq 1 ]; then
  setup_crontab
fi

echo "setup_server_ops 完成"
