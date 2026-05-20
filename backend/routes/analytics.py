"""页面访问统计：看盘日活等"""
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request

from utils.auth_middleware import login_required
from utils.db import execute_query, execute_write
from utils.response import v1_success_response, v1_error_response

logger = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__)

CN_TZ = timezone(timedelta(hours=8))
PAGE_STOCK_DASHBOARD = 'stock-dashboard'


def _today_cn():
    return datetime.now(CN_TZ).date()


@analytics_bp.route('/api/analytics/page-visit', methods=['POST'])
@login_required
def record_page_visit():
    """记录用户当日访问某页面（幂等，同一天多次调用只更新 last_seen_at）"""
    body = request.get_json(silent=True) or {}
    page = (body.get('page') or '').strip()
    if page != PAGE_STOCK_DASHBOARD:
        return v1_error_response('不支持的页面')

    user_id = request.current_user['user_id']
    today = _today_cn()

    try:
        execute_write(
            'INSERT INTO page_daily_activity (user_id, page, activity_date) '
            'VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE last_seen_at = CURRENT_TIMESTAMP',
            (user_id, page, today),
        )
    except Exception as e:
        logger.error(f'记录页面访问失败: {e}')
        return v1_error_response('记录失败')

    return v1_success_response(message='ok')


@analytics_bp.route('/api/analytics/dashboard-dau', methods=['GET'])
@login_required
def dashboard_dau():
    """今日使用过看盘页的账号数（登录用户可读）"""
    date_str = request.args.get('date')
    if date_str:
        try:
            activity_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return v1_error_response('date 格式应为 YYYY-MM-DD')
    else:
        activity_date = _today_cn()

    rows = execute_query(
        'SELECT COUNT(*) AS cnt FROM page_daily_activity '
        'WHERE page = %s AND activity_date = %s',
        (PAGE_STOCK_DASHBOARD, activity_date),
    )
    count = int(rows[0]['cnt']) if rows else 0

    return v1_success_response(data={
        'page': PAGE_STOCK_DASHBOARD,
        'date': activity_date.isoformat(),
        'count': count,
    })
