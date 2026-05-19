#!/usr/bin/env bash
# 切换 AI 账号：./scripts/switch_ai_account.sh anyrouter|kalowave
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT="${1:-}"
if [[ -z "$ACCOUNT" ]]; then
  echo "用法: $0 anyrouter|kalowave"
  exit 1
fi
mkdir -p "$ROOT/data"
printf '{\n  "account": "%s"\n}\n' "$ACCOUNT" > "$ROOT/data/ai_account.active"
echo "已切换 AI 账号为: $ACCOUNT"
echo "当前配置: curl -s http://localhost:9001/api/v1/ai-account | python3 -m json.tool"
