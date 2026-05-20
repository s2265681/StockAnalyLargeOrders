"""盘前资讯 API"""
import logging
from flask import Blueprint
from utils.response import v1_success_response, v1_error_response
from services.market_brief_service import get_today_brief

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
