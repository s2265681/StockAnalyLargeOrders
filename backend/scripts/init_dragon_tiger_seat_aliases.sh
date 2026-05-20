#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SQL_FILE="$ROOT_DIR/backend/migrations/20260516_create_dragon_tiger_seat_aliases.sql"

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-123456}"
MYSQL_DATABASE="${MYSQL_DATABASE:-stock}"

if [[ ! -f "$SQL_FILE" ]]; then
  echo "SQL 文件不存在: $SQL_FILE"
  exit 1
fi

echo "初始化龙虎榜席位映射表..."
echo "DB: ${MYSQL_USER}@${MYSQL_HOST}:${MYSQL_PORT}/${MYSQL_DATABASE}"

mysql \
  -h"$MYSQL_HOST" \
  -P"$MYSQL_PORT" \
  -u"$MYSQL_USER" \
  -p"$MYSQL_PASSWORD" \
  "$MYSQL_DATABASE" < "$SQL_FILE"

echo "初始化完成。当前映射条数："
mysql \
  -N \
  -h"$MYSQL_HOST" \
  -P"$MYSQL_PORT" \
  -u"$MYSQL_USER" \
  -p"$MYSQL_PASSWORD" \
  "$MYSQL_DATABASE" \
  -e "SELECT COUNT(*) FROM dragon_tiger_seat_aliases WHERE is_active=1;"
