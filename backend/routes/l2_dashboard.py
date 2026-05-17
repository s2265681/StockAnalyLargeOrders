"""
L2大单看板统一API路由
提供一站式的L2大单数据接口
"""
import logging
from datetime import datetime
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


def _convert_eastmoney_fflow_to_l2_flow(mf):
    """东财 fflow（当日累计净流入，万元）→ 前端分时博弈线结构，
    形状与 _convert_ths_moneyflow_to_l2_flow 完全一致（含 chaoda_delta），
    用作同花顺无深市数据时的兜底，避免沪深数据形状不一致导致“时有时无”。
    """
    if not mf:
        return None
    times = mf.get('time') or []
    chaoda_cum = [float(x or 0) for x in (mf.get('chaoda') or [])]   # 超大单
    dadan_cum = [float(x or 0) for x in (mf.get('dadan') or [])]     # 大单
    zhongdan_cum = [float(x or 0) for x in (mf.get('zhongdan') or [])]  # 中单
    sanhu_cum = [float(x or 0) for x in (mf.get('sanhu') or [])]     # 小单
    n = min(len(times), len(chaoda_cum), len(dadan_cum), len(zhongdan_cum), len(sanhu_cum))
    if n == 0:
        return None

    def _deltas(cum):
        return [cum[0] if i == 0 else cum[i] - cum[i - 1] for i in range(n)]

    cd, dd, zd, sd = (_deltas(chaoda_cum), _deltas(dadan_cum),
                      _deltas(zhongdan_cum), _deltas(sanhu_cum))
    # _build_intraday_game_scores 期望每分钟 [超大,大,中,小]
    minute_deltas = [[cd[i], dd[i], zd[i], sd[i]] for i in range(n)]
    game = _build_intraday_game_scores(minute_deltas)

    chaoda = game[0]
    dadan = game[1]
    zhongdan = game[2]
    sanhu = game[3]
    chaoda_delta = [_format_delta_wan(v) for v in cd]
    sanhu_delta = [_format_delta_wan(v) for v in sd]
    main_net_wan = round(chaoda_cum[n - 1] + dadan_cum[n - 1], 2)

    return {
        'source': 'eastmoney_fflow',
        'date': '',
        'time': times[:n],
        'zhuli': chaoda[:],
        'sanhu': sanhu,
        'chaoda': chaoda,
        'dadan': dadan,
        'zhongdan': zhongdan,
        'chaoda_delta': chaoda_delta,
        'sanhu_delta': sanhu_delta,
        'summary': {
            'super_big_net_wan': round(chaoda_cum[n - 1], 2),
            'big_net_wan': round(dadan_cum[n - 1], 2),
            'main_net_wan': main_net_wan,
            'mid_net_wan': round(zhongdan_cum[n - 1], 2),
            'small_net_wan': round(sanhu_cum[n - 1], 2),
        },
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
        # 资金流（主力/散户线）单独走 /api/v1/l2_money_flow（同花顺，含分钟净额 delta）。
        # 此处不再内嵌东财 fflow：东财常不可达会拖满 8s，且其数据缺 chaoda_delta，
        # 与同花顺形状不一致，前端二选一时会“时有时无”。本接口只管分时，保持单一数据源。
        result = adapter.get_timeshare_data(code, dt)
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
            # 同花顺对深市(00/30)恒无分钟资金流，回退东财 fflow（沪深通用）
            from routes.stock_timeshare import get_eastmoney_money_flow_data
            money_flow = _convert_eastmoney_fflow_to_l2_flow(
                get_eastmoney_money_flow_data(code))
        if not money_flow:
            return jsonify({'success': False, 'message': '资金流数据暂不可用', 'data': None})
        return jsonify({'success': True, 'data': money_flow})
    except Exception as e:
        logger.error(f"l2_money_flow 接口异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务异常: {str(e)}'}), 500
