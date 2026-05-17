"""
L2大单看板统一API路由
提供一站式的L2大单数据接口
"""
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from flask import Blueprint, request, jsonify

from services.data_source_adapter import DataSourceAdapter
from services.ths_moneyflow import get_moneyflow

logger = logging.getLogger(__name__)

l2_dashboard_bp = Blueprint('l2_dashboard', __name__)

adapter = DataSourceAdapter(use_l2=False)


def _format_ths_time(value):
    text = str(value or '')
    if len(text) == 4 and text.isdigit():
        return f'{text[:2]}:{text[2:]}'
    return text


def _net_wan(item, in_key, out_key):
    return f"{((float(item.get(in_key) or 0) - float(item.get(out_key) or 0)) / 10000):.3f}"


def _cum_net_wan(item, in_key, out_key):
    return (float(item.get(in_key) or 0) - float(item.get(out_key) or 0)) / 10000


def _minute_moneyflow_deltas(items):
    """同花顺 items 为累计流入/流出，转为四档分钟净流入（万元）。"""
    keys = (
        ('super_big_in', 'super_big_out'),
        ('big_in', 'big_out'),
        ('mid_in', 'mid_out'),
        ('small_in', 'small_out'),
    )
    deltas = []
    for index, item in enumerate(items):
        cumulative = [_cum_net_wan(item, in_key, out_key) for in_key, out_key in keys]
        if index == 0:
            deltas.append(cumulative)
            continue
        previous = items[index - 1]
        previous_cumulative = [
            _cum_net_wan(previous, in_key, out_key) for in_key, out_key in keys
        ]
        deltas.append([
            cumulative[idx] - previous_cumulative[idx]
            for idx in range(4)
        ])
    return deltas


def _build_intraday_game_scores(deltas):
    """按东方财富/同花顺分时博弈：分钟四档零和 + 运行累计 + 归一化到约 ±0.5。"""
    running = [0.0, 0.0, 0.0, 0.0]
    series = [[], [], [], []]
    for minute_delta in deltas:
        average = sum(minute_delta) / 4.0
        zero_sum = [value - average for value in minute_delta]
        for idx in range(4):
            running[idx] += zero_sum[idx]
            series[idx].append(running[idx])

    max_abs = max((abs(value) for row in series for value in row), default=0.0)
    scale = max(max_abs * 2.0, 1.0)
    return [[f"{(value / scale):.3f}" for value in row] for row in series]


def _format_delta_wan(value):
    return f"{float(value):.3f}"


def _convert_ths_moneyflow_to_l2_flow(moneyflow):
    """把同花顺资金分时转换为前端分时博弈线结构（博弈得分 + 分钟净额标注）。"""
    items = (moneyflow or {}).get('items') or []
    if not items:
        return None

    deltas = _minute_moneyflow_deltas(items)
    game_scores = _build_intraday_game_scores(deltas)
    times = []

    chaoda_delta = []
    dadan_delta = []
    zhongdan_delta = []
    sanhu_delta = []

    for index, item in enumerate(items):
        times.append(_format_ths_time(item.get('time')))
        chaoda_delta.append(_format_delta_wan(deltas[index][0]))
        dadan_delta.append(_format_delta_wan(deltas[index][1]))
        zhongdan_delta.append(_format_delta_wan(deltas[index][2]))
        sanhu_delta.append(_format_delta_wan(deltas[index][3]))

    chaoda = game_scores[0]
    dadan = game_scores[1]
    zhongdan = game_scores[2]
    sanhu = game_scores[3]
    zhuli = chaoda[:]

    return {
        'source': moneyflow.get('source', 'ths'),
        'date': moneyflow.get('date', ''),
        'time': times,
        'zhuli': zhuli,
        'sanhu': sanhu,
        'chaoda': chaoda,
        'dadan': dadan,
        'zhongdan': zhongdan,
        'chaoda_delta': chaoda_delta,
        'sanhu_delta': sanhu_delta,
        'summary': moneyflow.get('summary') or {},
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

    if not code.isdigit() or len(code) != 6:
        return jsonify({'success': False, 'message': f'无效的股票代码: {code}'}), 400

    try:
        money_flow = _convert_ths_moneyflow_to_l2_flow(get_moneyflow(code))
        if not money_flow:
            return jsonify({'success': False, 'message': '资金流数据暂不可用', 'data': None})
        return jsonify({'success': True, 'data': money_flow})
    except Exception as e:
        logger.error(f"l2_money_flow 接口异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务异常: {str(e)}'}), 500
