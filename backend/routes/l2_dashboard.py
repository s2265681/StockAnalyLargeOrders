"""
L2大单看板统一API路由
提供一站式的L2大单数据接口
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

from services.data_source_adapter import DataSourceAdapter

logger = logging.getLogger(__name__)

l2_dashboard_bp = Blueprint('l2_dashboard', __name__)

# 创建适配器实例（默认使用免费数据源）
adapter = DataSourceAdapter(use_l2=False)


@l2_dashboard_bp.route('/api/v1/l2_dashboard')
def l2_dashboard():
    """L2大单看板统一接口

    Query Params:
        code: 股票代码，默认 '000001'
        dt: 日期，格式 YYYY-MM-DD，默认当天

    Returns:
        JSON: 统一格式的L2看板数据
    """
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))
    simulate = request.args.get('simulate') in ('1', 'true', 'True')
    simulate_time = request.args.get('simulate_time') if simulate else None

    # 基本校验
    if not code.isdigit() or len(code) != 6:
        return jsonify({'success': False, 'message': f'无效的股票代码: {code}'}), 400

    try:
        result = adapter.get_l2_dashboard(code, dt=dt, simulate_time=simulate_time)
        return jsonify(result)
    except Exception as e:
        logger.error(f"L2看板接口异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务异常: {str(e)}'}), 500
