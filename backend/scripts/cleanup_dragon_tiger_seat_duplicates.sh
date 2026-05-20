#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SQL_FILE="$ROOT_DIR/backend/migrations/20260516_cleanup_dragon_tiger_seat_duplicates.sql"

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-123456}"
MYSQL_DATABASE="${MYSQL_DATABASE:-stock}"

if [[ ! -f "$SQL_FILE" ]]; then
  echo "SQL 文件不存在: $SQL_FILE"
  exit 1
fi

echo "开始清理 dragon_tiger_seats 重复数据..."
echo "DB: ${MYSQL_USER}@${MYSQL_HOST}:${MYSQL_PORT}/${MYSQL_DATABASE}"

mysql \
  -h"$MYSQL_HOST" \
  -P"$MYSQL_PORT" \
  -u"$MYSQL_USER" \
  -p"$MYSQL_PASSWORD" \
  "$MYSQL_DATABASE" < "$SQL_FILE"

echo "清理完成。可用以下 SQL 校验是否仍有重复："
echo "SELECT date, code, direction, seat_name, buy_amount, sell_amount, net_amount, COUNT(*) AS cnt"
echo "FROM dragon_tiger_seats"
echo "GROUP BY date, code, direction, seat_name, buy_amount, sell_amount, net_amount"
echo "HAVING cnt > 1;"
