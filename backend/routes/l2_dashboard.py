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


def _build_trading_axis():
    """生成 A 股分钟时间轴，用于资金流兜底对齐前端分时图。"""
    axis = []
    for hour, start, end in ((9, 30, 59), (10, 0, 59), (11, 0, 30), (13, 0, 59), (14, 0, 59), (15, 0, 0)):
        for minute in range(start, end + 1):
            axis.append(f"{hour:02d}:{minute:02d}")
    return axis


def _build_money_flow_from_orders(orders_result):
    """资金流接口不可用时，用大单方向按分钟聚合出可画线的兜底数据。"""
    if not orders_result or not orders_result.get('success'):
        return None

    orders = (orders_result.get('data') or {}).get('large_orders') or []
    if not orders:
        return None

    axis = _build_trading_axis()
    time_index = {time_key: idx for idx, time_key in enumerate(axis)}
    chaoda = [0.0] * len(axis)
    dadan = [0.0] * len(axis)
    zhongdan = [0.0] * len(axis)
    sanhu = [0.0] * len(axis)

    for order in orders:
        minute = str(order.get('time', ''))[:5]
        idx = time_index.get(minute)
        if idx is None:
            continue

        amount_wan = float(order.get('amount') or 0)
        if amount_wan <= 0:
            continue

        direction = order.get('direction') or order.get('type') or ''
        sign = -1 if direction in ('被卖', '主卖', 'sell') else 1
        signed_amount = sign * amount_wan

        if amount_wan >= 300:
            chaoda[idx] += signed_amount
        elif amount_wan >= 100:
            dadan[idx] += signed_amount
        elif amount_wan >= 50:
            zhongdan[idx] += signed_amount
        else:
            sanhu[idx] += signed_amount

    def cumulative(values):
        total = 0.0
        result = []
        for value in values:
            total += value
            result.append(f"{total:.3f}")
        return result

    return {
        'zhuli': cumulative([chaoda[i] + dadan[i] for i in range(len(axis))]),
        'sanhu': cumulative(sanhu),
        'chaoda': cumulative(chaoda),
        'dadan': cumulative(dadan),
        'zhongdan': cumulative(zhongdan),
        'source': 'orders_fallback',
    }


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
                mf = mf_future.result(timeout=8)
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


@l2_dashboard_bp.route('/api/v1/l2_money_flow')
def l2_money_flow():
    """独立返回大/小资金线需要的分钟资金流数据。"""
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))

    if not code.isdigit() or len(code) != 6:
        return jsonify({'success': False, 'message': f'无效的股票代码: {code}'}), 400

    try:
        from routes.stock_timeshare import get_eastmoney_money_flow_data

        money_flow = get_eastmoney_money_flow_data(code)
        if not money_flow:
            money_flow = _build_money_flow_from_orders(adapter.get_orders_data(code, dt=dt))
        if not money_flow:
            return jsonify({'success': False, 'message': '资金流数据暂不可用', 'data': None})
        return jsonify({'success': True, 'data': money_flow})
    except Exception as e:
        logger.error(f"l2_money_flow 接口异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务异常: {str(e)}'}), 500
