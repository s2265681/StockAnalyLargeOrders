"""
AI 诊股接口
- POST /api/v1/ai-diagnosis
- GET  /api/v1/ai-diagnosis/cache
- POST /api/v1/ai-diagnosis/chat
"""
import logging

from flask import Blueprint, request

from services.ai_diagnosis_service import (
    get_cache,
    get_trading_date_str,
    normalize_code,
    run_chat,
    run_diagnosis,
)
from utils.response import v1_error_response, v1_success_response

logger = logging.getLogger(__name__)

ai_diagnosis_bp = Blueprint("ai_diagnosis", __name__)


@ai_diagnosis_bp.route("/api/v1/ai-diagnosis", methods=["POST"])
def post_diagnosis():
    body = request.get_json(silent=True) or {}
    code = normalize_code(body.get("code", ""))
    force_refresh = bool(body.get("force_refresh"))

    if not code or len(code) != 6:
        return v1_error_response(message="请提供有效的6位股票代码")

    try:
        data = run_diagnosis(code, force_refresh=force_refresh)
        return v1_success_response(data=data)
    except ValueError as e:
        return v1_error_response(message=str(e))
    except RuntimeError as e:
        return v1_error_response(message=str(e))
    except Exception as e:
        logger.error(f"诊股失败: {e}", exc_info=True)
        return v1_error_response(message=f"诊股失败: {str(e)}")


@ai_diagnosis_bp.route("/api/v1/ai-diagnosis/cache", methods=["GET"])
def get_diagnosis_cache():
    code = normalize_code(request.args.get("code", ""))
    dt = (request.args.get("date") or get_trading_date_str()).replace("-", "")

    if not code:
        return v1_error_response(message="请提供 code 参数")

    cached = get_cache(dt, code)
    if not cached:
        return v1_success_response(data=None)
    return v1_success_response(data={
        "code": code,
        "date": dt,
        "snapshot": cached["snapshot"],
        "report": cached["report"],
        "cached": True,
    })


@ai_diagnosis_bp.route("/api/v1/ai-diagnosis/chat", methods=["POST"])
def post_diagnosis_chat():
    body = request.get_json(silent=True) or {}
    code = normalize_code(body.get("code", ""))
    message = (body.get("message") or "").strip()
    context = body.get("context") or {}

    if not code:
        return v1_error_response(message="请提供 code")
    if not message:
        return v1_error_response(message="请输入追问内容")

    try:
        data = run_chat(code, message, context)
        return v1_success_response(data=data)
    except RuntimeError as e:
        return v1_error_response(message=str(e))
    except Exception as e:
        logger.error(f"追问失败: {e}", exc_info=True)
        return v1_error_response(message=f"追问失败: {str(e)}")
