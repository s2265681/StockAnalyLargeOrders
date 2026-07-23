#!/usr/bin/env bash
# 微信支付一键部署：同步证书 + 更新服务器 .env + 迁移 + 重启后端
#
# 用法（网站应用审核通过、AppID 关联完成后）:
#   ./scripts/deploy-wechat-pay.sh --app-id wxXXXXXXXX
#
# 可选:
#   ./scripts/deploy-wechat-pay.sh --app-id wxXXX --dry-run
#   ./scripts/deploy-wechat-pay.sh --app-id wxXXX --skip-migrate
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}ℹ️  $*${NC}"; }
ok()    { echo -e "${GREEN}✅ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $*${NC}"; }
fail()  { echo -e "${RED}❌ $*${NC}"; exit 1; }

APP_ID=""
DRY_RUN=false
SKIP_MIGRATE=false

usage() {
  cat <<'EOF'
微信支付一键部署

前置条件:
  1. 开放平台网站应用已审核通过
  2. 商户平台已关联 AppID 并在开放平台确认
  3. 本地 backend/certs/ 已有 apiclient_key.pem、pub_key.pem
  4. 本地 backend/.env 已配置 WECHAT_API_V3_KEY 等（除 APP_ID 外）
  5. 已配置 scripts/wechat-pay.deploy.env（SSH 信息）

用法:
  ./scripts/deploy-wechat-pay.sh --app-id wxXXXXXXXX [选项]

选项:
  --app-id wxXXX     网站应用 AppID（必填）
  --dry-run          只检查，不实际上传/重启
  --skip-migrate     跳过数据库迁移
  -h, --help         显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) APP_ID="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --skip-migrate) SKIP_MIGRATE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "未知参数: $1（使用 --help 查看用法）" ;;
  esac
done

[[ -n "$APP_ID" ]] || fail "请提供 --app-id wxXXXXXXXX"
[[ "$APP_ID" =~ ^wx[a-zA-Z0-9]{8,}$ ]] || fail "AppID 格式不正确: $APP_ID"

DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-$ROOT_DIR/scripts/wechat-pay.deploy.env}"
[[ -f "$DEPLOY_ENV_FILE" ]] || fail "缺少部署配置: $DEPLOY_ENV_FILE\n请先: cp scripts/wechat-pay.deploy.env.example scripts/wechat-pay.deploy.env"

# shellcheck disable=SC1090
source "$DEPLOY_ENV_FILE"

SERVER_HOST="${SERVER_HOST:?请在 wechat-pay.deploy.env 设置 SERVER_HOST}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_PORT="${SERVER_PORT:-22}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/www/StockAnalyLargeOrders}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://www.stockai.xin}"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$ROOT_DIR/backend/.env}"

SSH_OPTS=(-p "$SERVER_PORT" -o StrictHostKeyChecking=accept-new)
[[ -n "${SSH_KEY:-}" ]] && SSH_OPTS+=(-i "$SSH_KEY")
SSH_TARGET="${SERVER_USER}@${SERVER_HOST}"

ssh_cmd() {
  if $DRY_RUN; then
    info "[dry-run] ssh ${SSH_TARGET} $*"
  else
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$@"
  fi
}

scp_cmd() {
  if $DRY_RUN; then
    info "[dry-run] scp -> ${SSH_TARGET}:$*"
  else
    scp "${SSH_OPTS[@]}" "$@"
  fi
}

read_env_var() {
  local key="$1"
  local file="$2"
  local line
  line=$(grep -E "^${key}=" "$file" | tail -1 || true)
  [[ -n "$line" ]] || return 1
  echo "${line#*=}"
}

info "检查本地文件..."
[[ -f "$LOCAL_ENV_FILE" ]] || fail "缺少本地环境文件: $LOCAL_ENV_FILE"
[[ -f "$ROOT_DIR/backend/certs/apiclient_key.pem" ]] || fail "缺少 backend/certs/apiclient_key.pem"
[[ -f "$ROOT_DIR/backend/certs/pub_key.pem" ]] || fail "缺少 backend/certs/pub_key.pem"

MCH_ID=$(read_env_var WECHAT_MCH_ID "$LOCAL_ENV_FILE" || true)
API_V3_KEY=$(read_env_var WECHAT_API_V3_KEY "$LOCAL_ENV_FILE" || true)
CERT_SERIAL=$(read_env_var WECHAT_CERT_SERIAL_NO "$LOCAL_ENV_FILE" || true)
PUBLIC_KEY_ID=$(read_env_var WECHAT_PAY_PUBLIC_KEY_ID "$LOCAL_ENV_FILE" || true)
NOTIFY_URL=$(read_env_var WECHAT_NOTIFY_URL "$LOCAL_ENV_FILE" || true)

[[ -n "$MCH_ID" ]] || fail "本地 .env 缺少 WECHAT_MCH_ID"
[[ -n "$API_V3_KEY" ]] || fail "本地 .env 缺少 WECHAT_API_V3_KEY"
[[ -n "$CERT_SERIAL" ]] || fail "本地 .env 缺少 WECHAT_CERT_SERIAL_NO"
[[ -n "$PUBLIC_KEY_ID" ]] || fail "本地 .env 缺少 WECHAT_PAY_PUBLIC_KEY_ID"
NOTIFY_URL="${NOTIFY_URL:-https://www.stockai.xin/api/payments/wechat/notify}"

ok "本地配置检查通过"
info "目标服务器: ${SSH_TARGET}"
info "部署路径: ${DEPLOY_ROOT}"
info "AppID: ${APP_ID}"

info "同步证书到服务器..."
if $DRY_RUN; then
  info "[dry-run] mkdir ${DEPLOY_ROOT}/backend/certs"
  info "[dry-run] upload apiclient_key.pem pub_key.pem"
else
  ssh_cmd "mkdir -p ${DEPLOY_ROOT}/backend/certs && chmod 700 ${DEPLOY_ROOT}/backend/certs"
  scp_cmd "$ROOT_DIR/backend/certs/apiclient_key.pem" \
          "$ROOT_DIR/backend/certs/pub_key.pem" \
          "${SSH_TARGET}:${DEPLOY_ROOT}/backend/certs/"
  ssh_cmd "chmod 600 ${DEPLOY_ROOT}/backend/certs/apiclient_key.pem ${DEPLOY_ROOT}/backend/certs/pub_key.pem"
fi
ok "证书同步完成"

info "更新服务器 backend/.env 微信支付配置..."
REMOTE_ENV_BLOCK=$(cat <<EOF
# ========== 微信支付（由 deploy-wechat-pay.sh 更新）==========
WECHAT_PAY_ENABLED=1
WECHAT_APP_ID=${APP_ID}
WECHAT_MCH_ID=${MCH_ID}
WECHAT_API_V3_KEY=${API_V3_KEY}
WECHAT_CERT_SERIAL_NO=${CERT_SERIAL}
WECHAT_NOTIFY_URL=${NOTIFY_URL}
WECHAT_PRIVATE_KEY_PATH=certs/apiclient_key.pem
WECHAT_PAY_PUBLIC_KEY_PATH=certs/pub_key.pem
WECHAT_PAY_PUBLIC_KEY_ID=${PUBLIC_KEY_ID}
EOF
)

if $DRY_RUN; then
  info "[dry-run] 将写入服务器 .env 微信支付段落（AppID=${APP_ID}）"
else
  ssh_cmd "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
ENV_FILE="${DEPLOY_ROOT}/backend/.env"
touch "\$ENV_FILE"
if grep -q '^# ========== 微信支付' "\$ENV_FILE"; then
  awk '
    BEGIN { skip=0 }
    /^# ========== 微信支付/ { skip=1; next }
    skip && /^[A-Z_]+=/ { next }
    skip && /^$/ { skip=0; next }
    skip && /^# ==========/ { skip=0 }
    { print }
  ' "\$ENV_FILE" > "\$ENV_FILE.tmp" && mv "\$ENV_FILE.tmp" "\$ENV_FILE"
fi
cat >> "\$ENV_FILE" <<'WECHAT_ENV'
${REMOTE_ENV_BLOCK}
WECHAT_ENV
chmod 600 "\$ENV_FILE"
REMOTE_SCRIPT
fi
ok "服务器 .env 已更新"

if ! $SKIP_MIGRATE; then
  info "执行数据库迁移..."
  MIGRATIONS=(
    "migrations/20260723_wechat_pay_orders.sql"
    "migrations/20260723_test_pay_plans.sql"
  )
  for mig in "${MIGRATIONS[@]}"; do
    if $DRY_RUN; then
      info "[dry-run] apply ${mig}"
    else
      ssh_cmd "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
cd "${DEPLOY_ROOT}/backend"
if [ -f "${mig}" ]; then
  set -a
  [ -f .env ] && . ./.env
  set +a
  echo "Applying ${mig}"
  MYSQL_PWD="\${MYSQL_PASSWORD:-123456}" mysql \
    -h"\${MYSQL_HOST:-127.0.0.1}" \
    -P"\${MYSQL_PORT:-3306}" \
    -u"\${MYSQL_USER:-root}" \
    "\${MYSQL_DATABASE:-stock}" < "${mig}"
else
  echo "Skip missing ${mig}"
fi
REMOTE_SCRIPT
    fi
  done
  ok "数据库迁移完成"
else
  warn "已跳过数据库迁移 (--skip-migrate)"
fi

info "安装依赖并重启后端..."
if $DRY_RUN; then
  info "[dry-run] pip install -r requirements.txt && pm2 restart"
else
  ssh_cmd "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
cd "${DEPLOY_ROOT}"
git pull origin master 2>/dev/null || git pull origin main 2>/dev/null || true
cd backend
if [ ! -d venv ]; then python3 -m venv venv; fi
source venv/bin/activate
pip install -q -r requirements.txt
deactivate
cd "${DEPLOY_ROOT}"
chmod +x backend/scripts/ensure_single_backend.sh
bash backend/scripts/ensure_single_backend.sh
REMOTE_SCRIPT
fi
ok "后端已重启"

info "验证支付配置..."
if $DRY_RUN; then
  warn "dry-run 模式，跳过线上验证"
else
  sleep 3
  BODY=$(curl -fsS "${PUBLIC_BASE_URL}/api/orders/payment-config" || true)
  if echo "$BODY" | grep -q '"wechat_enabled"[[:space:]]*:[[:space:]]*true'; then
    ok "支付配置已启用: ${PUBLIC_BASE_URL}/api/orders/payment-config"
  else
    warn "支付配置接口未返回 wechat_enabled=true"
    echo "响应: ${BODY:-<empty>}"
    fail "请检查服务器日志: pm2 logs StockAnalysisLargeOrders"
  fi
fi

echo ""
ok "🎉 微信支付部署完成"
echo ""
echo "下一步测试:"
echo "  1. 打开 ${PUBLIC_BASE_URL} 登录账号"
echo "  2. 进入 VIP 开通页，选择「测试VIP 1分」"
echo "  3. 微信扫码支付 ¥0.01"
echo "  4. 确认 VIP 已激活"
echo ""
echo "若需仅检查不部署: ./scripts/deploy-wechat-pay.sh --app-id ${APP_ID} --dry-run"
