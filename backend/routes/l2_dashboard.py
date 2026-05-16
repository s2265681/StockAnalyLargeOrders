"""
L2大单看板统一API路由
提供一站式的L2大单数据接口
"""
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from flask import Blueprint, request, jsonify

from services.data_source_adapter import DataSourceAdapter

logger = logging.getLogger(__name__)

l2_dashboard_bp = Blueprint('l2_dashboard', __name__)

adapter = DataSourceAdapter(use_l2=False)


@l2_dashboard_bp.route('/api/v1/l2_dashboard')
def l2_dashboard():
    """L2大单看板统一接口（全量，含分时+大单）"""
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))
    simulate = request.args.get('simulate') in ('1', 'true', 'True')
    simulate_time = request.args.get('simulate_time') if simulate else None

    if not code.isdigit() or len(code) != 6:
        return jsonify({'success': False, 'message': f'无效的股票代码: {code}'}), 400

    try:
        result = adapter.get_l2_dashboard(code, dt=dt, simulate_time=simulate_time)
        return jsonify(result)
    except Exception as e:
        logger.error(f"L2看板接口异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务异常: {str(e)}'}), 500


@l2_dashboard_bp.route('/api/v1/l2_timeshare')
def l2_timeshare():
    """只返回分时走势 + 股票基础信息（轻量，快速渲染分时图用）

    Query Params:
        code: 股票代码
        dt:   日期，YYYY-MM-DD，默认最新交易日
    """
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))

    if not code.isdigit() or len(code) != 6:
        return jsonify({'success': False, 'message': f'无效的股票代码: {code}'}), 400

    try:
        # 并行请求分时数据和资金流向数据
        from routes.stock_timeshare import get_eastmoney_money_flow_data

        executor = ThreadPoolExecutor(max_workers=2)
        try:
            ts_future = executor.submit(adapter.get_timeshare_data, code, dt)
            mf_future = executor.submit(get_eastmoney_money_flow_data, code)
            result = ts_future.result(timeout=30)

            try:
                mf = mf_future.result(timeout=1.5)
                if mf and result.get('success') and result.get('data'):
                    result['data']['money_flow'] = mf
            except TimeoutError:
                mf_future.cancel()
                logger.warning("获取大单净量数据超时，先返回分时数据")
            except Exception as e:
                logger.warning(f"获取大单净量数据失败: {e}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        return jsonify(result)
    except Exception as e:
        logger.error(f"l2_timeshare 接口异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务异常: {str(e)}'}), 500


@l2_dashboard_bp.route('/api/v1/l2_orders')
def l2_orders():
    """只返回大单列表 + 分级统计 + big_map（依赖逐笔，稍慢）

    Query Params:
        code: 股票代码
        dt:   日期，YYYY-MM-DD，默认最新交易日
    """
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))

    if not code.isdigit() or len(code) != 6:
        return jsonify({'success': False, 'message': f'无效的股票代码: {code}'}), 400

    try:
        result = adapter.get_orders_data(code, dt=dt)
        return jsonify(result)
    except Exception as e:
        logger.error(f"l2_orders 接口异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务异常: {str(e)}'}), 500
