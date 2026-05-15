"""
股票成交明细与大单接口模块
数据源：DataSourceAdapter（东方财富）
"""
import logging
from datetime import datetime
from flask import Blueprint, request
from utils.response import success_response, error_response, v1_success_response, v1_error_response
from utils.date_utils import validate_and_get_trading_date

logger = logging.getLogger(__name__)

stock_tick_bp = Blueprint('stock_tick', __name__)

from services.data_source_adapter import DataSourceAdapter
_adapter = DataSourceAdapter(use_l2=False)


def _get_dashboard(code, dt):
    """获取L2看板数据（含大单列表和统计）"""
    trading_date = validate_and_get_trading_date(dt)
    return _adapter.get_l2_dashboard(code, dt=trading_date), trading_date


@stock_tick_bp.route('/api/stock/large-orders', methods=['GET'])
def get_large_orders():
    """获取大单明细"""
    code = request.args.get('stock_code', request.args.get('code', '000001'))
    dt = request.args.get('date', request.args.get('dt'))
    try:
        result, trading_date = _get_dashboard(code, dt)
        if not result.get('success'):
            return error_response(message='获取大单数据失败')
        return success_response(data={
            'stock_code': code,
            'trading_date': trading_date,
            'large_orders': result['data']['large_orders'],
            'statistics': result['data']['statistics'],
        })
    except Exception as e:
        logger.error(f"获取大单数据失败: {e}")
        return error_response(message=f'获取大单数据失败: {str(e)}')


@stock_tick_bp.route('/api/v1/dadan', methods=['GET'])
def get_dadan():
    """竞品格式 - 大单明细接口"""
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))
    try:
        result, trading_date = _get_dashboard(code, dt)
        if not result.get('success'):
            return v1_error_response(message='获取大单数据失败')

        orders = result['data']['large_orders']
        dadan_list = [
            {
                'time': o.get('time', ''),
                'status': o.get('direction', ''),
                'price': o.get('price', 0),
                'volume': o.get('volume_lots', 0),
                'amount': o.get('amount', 0),  # 已是万元
                'is_buy': o.get('direction', '') in ('被买', '主买'),
                'concentrated': o.get('concentrated', False),  # 集中成交标记
                'trade_count': o.get('trade_count', 1),
            }
            for o in orders
        ]

        return v1_success_response(data={
            'code': code,
            'date': dt,
            'dadan_list': dadan_list[:20],
            'total_count': len(dadan_list),
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
    except Exception as e:
        logger.error(f"获取大单数据失败: {e}")
        return v1_error_response(message=f'获取大单数据失败: {str(e)}')


@stock_tick_bp.route('/api/v1/dadantongji')
def get_dadan_statistics():
    """竞品格式 - 大单统计接口"""
    code = request.args.get('stock_code', request.args.get('code', '000001'))
    dt = request.args.get('date', request.args.get('dt'))
    try:
        result, trading_date = _get_dashboard(code, dt)
        if not result.get('success'):
            return v1_error_response(message='获取大单统计失败')

        stats = result['data']['statistics']
        level_map = [
            ('above_300', '大于300万'),
            ('above_100', '大于100万'),
            ('above_50',  '大于50万'),
            ('above_30',  '大于30万'),
            ('below_30',  '小于30万'),
        ]
        formatted = [
            {
                'level': label,
                'buy_count': stats.get(key, {}).get('buy_count', 0),
                'sell_count': stats.get(key, {}).get('sell_count', 0),
                'buy_amount': stats.get(key, {}).get('buy_amount', 0.0),
                'sell_amount': stats.get(key, {}).get('sell_amount', 0.0),
                'net_count': (stats.get(key, {}).get('buy_count', 0)
                              - stats.get(key, {}).get('sell_count', 0)),
            }
            for key, label in level_map
        ]

        return v1_success_response(data={
            'stock_code': code,
            'trading_date': trading_date,
            'statistics': formatted,
            'data_source': 'eastmoney_free',
        })
    except Exception as e:
        logger.error(f"大单统计失败: {e}")
        return v1_error_response(message=f'大单统计失败: {str(e)}')
