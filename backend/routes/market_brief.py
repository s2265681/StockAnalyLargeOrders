"""盘前资讯 API"""
import logging
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response
from utils.auth_middleware import login_required
from services.market_brief_service import get_today_brief, generate_today_brief

logger = logging.getLogger(__name__)

market_brief_bp = Blueprint('market_brief', __name__)


@market_brief_bp.route('/api/market-brief/today', methods=['GET'])
def today_brief():
    try:
        brief = get_today_brief()
        if brief is None:
            return v1_success_response({'available': False})
        return v1_success_response({'available': True, **brief})
    except Exception as e:
        logger.error('读取 market_brief 失败: %s', e)
        return v1_error_response('读取盘前资讯失败')


@market_brief_bp.route('/api/market-brief/refresh', methods=['POST'])
@login_required
def refresh_brief():
    """手动触发生成今日盘前资讯（登录用户，耗时约 30–90 秒）。"""
    body = request.get_json(silent=True) or {}
    force = bool(body.get('force'))
    try:
        brief = generate_today_brief(force=force, send_email=False)
        if not brief:
            return v1_error_response('生成失败')
        return v1_success_response({'available': True, **brief}, message='盘前资讯已生成')
    except Exception as e:
        logger.error('生成 market_brief 失败: %s', e, exc_info=True)
        return v1_error_response(f'生成盘前资讯失败: {e}')
