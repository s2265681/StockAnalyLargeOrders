"""AI 账号切换 API"""
import logging

from flask import Blueprint, request

from config.ai_accounts import (
    get_active_account,
    get_active_account_id,
    list_accounts_public,
    set_active_account_id,
)
from utils.auth_middleware import admin_required
from utils.response import v1_error_response, v1_success_response

logger = logging.getLogger(__name__)

ai_account_bp = Blueprint("ai_account", __name__)


@ai_account_bp.route("/api/v1/ai-account", methods=["GET"])
def get_ai_account():
    """查看当前 AI 账号与可用列表（不含密钥）"""
    active = get_active_account()
    return v1_success_response(data={
        "active": get_active_account_id(),
        "active_label": active.label,
        "api_url": active.api_url,
        "models": active.models,
        "accounts": list_accounts_public(),
    })


@ai_account_bp.route("/api/v1/ai-account", methods=["POST"])
@admin_required
def switch_ai_account():
    """切换 AI 账号（写入 backend/data/ai_account.active，无需重启）"""
    body = request.get_json(silent=True) or {}
    account_id = (body.get("account") or request.args.get("account") or "").strip()
    if not account_id:
        return v1_error_response(message="请提供 account 参数，如 anyrouter 或 kalowave")
    try:
        set_active_account_id(account_id)
    except ValueError as e:
        return v1_error_response(message=str(e))

    from utils.claude_client import refresh_client_credentials
    refresh_client_credentials()

    active = get_active_account()
    logger.info("AI 账号已切换为 %s (%s)", active.id, active.label)
    return v1_success_response(
        data={
            "active": active.id,
            "active_label": active.label,
            "api_url": active.api_url,
            "models": active.models,
            "accounts": list_accounts_public(),
        },
        message=f"已切换到 {active.label}",
    )
