"""
数据源适配器
负责调用数据源获取原始数据，进行大单识别、分级统计，返回统一格式
"""
import logging
import time
from datetime import datetime

from .eastmoney_free import EastMoneyFreeSource
from .eastmoney_l2 import EastMoneyL2Source

logger = logging.getLogger(__name__)

# 大单分级阈值（单位：元）
LEVEL_THRESHOLDS = {
    'above_300': 3_000_000,
    'above_100': 1_000_000,
    'above_50':  500_000,
    'above_30':  300_000,
}

# 简单内存缓存
_cache = {}
CACHE_TTL = 5  # 秒


class DataSourceAdapter:
    """数据源适配器，统一免费/L2数据源，输出标准格式"""

    def __init__(self, use_l2=False):
        if use_l2:
            self.source = EastMoneyL2Source()
            self.source_name = 'eastmoney_l2'
        else:
            self.source = EastMoneyFreeSource()
            self.source_name = 'eastmoney_free'

    def get_l2_dashboard(self, code):
        """获取L2大单看板全量数据，结果缓存5秒"""
        cache_key = f'l2_dashboard_{code}'
        now = time.time()

        if cache_key in _cache:
            cached_time, cached_data = _cache[cache_key]
            if now - cached_time < CACHE_TTL:
                return cached_data

        result = self._build_dashboard(code)
        _cache[cache_key] = (now, result)
        return result

    def _build_dashboard(self, code):
        """构建完整的看板数据"""
        # 1. 获取实时行情
        quote = self.source.get_realtime_quote(code)
        if not quote:
            return {'success': False, 'message': '获取行情数据失败'}

        # 2. 获取逐笔成交明细
        tick_result = self.source.get_tick_details(code)
        all_details = tick_result.get('details', [])

        # 3. 获取分时走势
        timeshare = self.source.get_timeshare(code)

        # 4. 标注买卖方向
        for detail in all_details:
            detail['direction'] = self.source.infer_direction(detail['type'])

        # 5. 识别大单并分级
        large_orders = self._identify_large_orders(all_details)
        statistics = self._calculate_statistics(all_details)
        big_map = self._build_big_map(large_orders)

        return {
            'success': True,
            'data': {
                'stock_info': {
                    'code': quote['code'],
                    'name': quote['name'],
                    'price': quote['price'],
                    'yesterday_close': quote['yesterday_close'],
                    'open': quote['open'],
                    'high': quote['high'],
                    'low': quote['low'],
                    'volume': quote['volume'],
                    'turnover': quote['turnover'],
                    'change_percent': quote['change_percent'],
                },
                'timeshare': timeshare,
                'statistics': statistics,
                'large_orders': large_orders,
                'big_map': big_map,
                'data_source': self.source_name,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        }

    def _identify_large_orders(self, details):
        """从逐笔明细中识别大单（成交额>=30万），按金额降序"""
        large = []
        for d in details:
            if d['amount'] >= LEVEL_THRESHOLDS['above_30']:
                large.append({
                    'time': d['time'],
                    'direction': d['direction'],
                    'price': d['price'],
                    'volume_lots': d['volume'],
                    'amount': round(d['amount'] / 10000, 2),  # 万元
                })
        large.sort(key=lambda x: x['amount'], reverse=True)
        return large

    def _calculate_statistics(self, details):
        """按分级统计大单买卖笔数和金额"""
        stats = {}
        for level_key in list(LEVEL_THRESHOLDS.keys()) + ['below_30']:
            stats[level_key] = {
                'buy_count': 0, 'sell_count': 0,
                'buy_amount': 0.0, 'sell_amount': 0.0,
            }

        for d in details:
            amount = d['amount']
            is_buy = d['direction'] in ('被买', '主买')
            amount_wan = amount / 10000

            if amount >= LEVEL_THRESHOLDS['above_300']:
                level_key = 'above_300'
            elif amount >= LEVEL_THRESHOLDS['above_100']:
                level_key = 'above_100'
            elif amount >= LEVEL_THRESHOLDS['above_50']:
                level_key = 'above_50'
            elif amount >= LEVEL_THRESHOLDS['above_30']:
                level_key = 'above_30'
            else:
                level_key = 'below_30'

            if is_buy:
                stats[level_key]['buy_count'] += 1
                stats[level_key]['buy_amount'] = round(stats[level_key]['buy_amount'] + amount_wan, 2)
            else:
                stats[level_key]['sell_count'] += 1
                stats[level_key]['sell_amount'] = round(stats[level_key]['sell_amount'] + amount_wan, 2)

        return stats

    def _build_big_map(self, large_orders):
        """构建分时图大单标注数据（按分钟分组）"""
        big_map = {}
        for order in large_orders:
            time_str = order['time']
            minute_key = time_str[:5] if len(time_str) >= 5 else time_str

            if minute_key not in big_map:
                big_map[minute_key] = []

            big_map[minute_key].append({
                'type': order['direction'],
                'volume': order['volume_lots'],
                'amount': order['amount'],
            })

        return big_map
