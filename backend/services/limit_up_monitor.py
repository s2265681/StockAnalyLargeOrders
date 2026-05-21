"""
封单监控服务
追踪涨停股票的封单状态，包括封单量、封单趋势、开板次数等
"""
import logging
from collections import deque
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)

# 模块级浮动市值缓存，key: (code, date_str) -> float_market_cap (元)
_float_market_cap_cache: dict = {}

# 单例实例
_instance = None
_instance_date: str = ""


def _get_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _fetch_float_market_cap(code: str) -> float:
    """通过 akshare 获取流通市值（元），失败返回 0"""
    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=code)
        if df is None or df.empty:
            return 0.0
        # 字段：item / value
        values = dict(zip(df['item'], df['value']))
        # 流通市值单位为亿元
        raw = values.get('流通市值', 0)
        return float(raw) * 1e8 if raw else 0.0
    except Exception as e:
        logger.warning(f"获取流通市值失败 {code}: {e}")
        return 0.0


def _get_float_market_cap(code: str) -> float:
    """获取流通市值（元），每日缓存"""
    today = _get_today()
    cache_key = (code, today)
    if cache_key not in _float_market_cap_cache:
        _float_market_cap_cache[cache_key] = _fetch_float_market_cap(code)
    return _float_market_cap_cache[cache_key]


class LimitUpMonitor:
    """
    封单监控服务（单例，每日状态重置）
    """

    def __new__(cls):
        global _instance, _instance_date
        today = _get_today()
        if _instance is None or _instance_date != today:
            _instance = super().__new__(cls)
            _instance._init_state()
            _instance_date = today
        return _instance

    def _init_state(self):
        """初始化每日状态"""
        # key: code -> dict with per-stock tracking state
        self._stocks: dict = {}

    def _get_stock_state(self, code: str) -> dict:
        """获取或初始化股票状态"""
        if code not in self._stocks:
            self._stocks[code] = {
                'seal_samples': deque(maxlen=60),   # 封单额（万元）历史样本
                'break_count': 0,                    # 开板次数
                'first_limit_time': None,            # 首次涨停时间 (HH:MM)
                'was_limit_up': False,               # 上一时刻是否涨停
            }
        return self._stocks[code]

    def _empty_result(self) -> dict:
        """返回所有字段归零的默认结果"""
        return {
            'is_limit_up': False,
            'limit_up_price': 0.0,
            'seal_amount': 0.0,
            'seal_volume_lots': 0,
            'seal_ratio': 0.0,
            'seal_trend': 0.0,
            'seal_trend_label': '封单平稳',
            'break_count': 0,
            'first_limit_time': None,
            'turnover_at_limit': 0.0,
            'seal_data_valid': False,
        }

    def analyze(self, code: str, quote: dict, order_book: dict) -> dict:
        """
        分析封单状态

        Args:
            code: 股票代码
            quote: 实时行情，来自 EastMoneyFreeSource.get_realtime_quote()
            order_book: 五档盘口，来自 EastMoneyFreeSource.get_order_book()

        Returns:
            封单分析结果字典
        """
        if not quote or not order_book:
            return self._empty_result()

        try:
            yesterday_close = float(quote.get('yesterday_close', 0) or 0)
            current_price = float(quote.get('price', 0) or 0)
            name = quote.get('name', '')
            turnover = float(quote.get('turnover', 0) or 0)  # 成交额（元）

            if yesterday_close <= 0:
                return self._empty_result()

            # 判断是否为ST股票（含*ST / ST）
            is_st = 'ST' in name.upper() if name else False

            # 计算涨停价
            if is_st:
                limit_up_price = round(yesterday_close * 1.05, 2)
            else:
                limit_up_price = round(yesterday_close * 1.1, 2)

            # 判断当前是否涨停（允许 0.005 误差）
            is_limit_up = abs(current_price - limit_up_price) <= 0.005

            # 获取股票追踪状态
            state = self._get_stock_state(code)

            # 涨停价买一：封单金额（万元）+ 封单量（手，1手=100股）
            seal_amount = 0.0
            seal_volume_lots = 0
            bids = order_book.get('bids', [])
            if bids and is_limit_up:
                bid1 = bids[0]
                bid1_price = float(bid1.get('price', 0) or 0)
                bid1_amount = float(bid1.get('amount', 0) or 0)
                bid1_volume = float(bid1.get('volume', 0) or 0)  # 股
                if abs(bid1_price - limit_up_price) <= 0.005:
                    seal_amount = round(bid1_amount / 10000, 2)  # 元 -> 万元
                    seal_volume_lots = int(bid1_volume // 100)  # 股 -> 手

            # 获取流通市值（元）
            float_market_cap = _get_float_market_cap(code)

            # 计算封单比（封单额元 / 流通市值元）
            if float_market_cap > 0:
                seal_ratio = round(seal_amount * 10000 / float_market_cap, 6)
            else:
                seal_ratio = 0.0

            # 更新封单样本队列
            state['seal_samples'].append(seal_amount)

            # 线性回归计算封单趋势斜率
            samples = list(state['seal_samples'])
            if len(samples) >= 2:
                x = np.arange(len(samples), dtype=float)
                y = np.array(samples, dtype=float)
                # 使用 numpy 线性回归
                coeffs = np.polyfit(x, y, 1)
                seal_trend = float(coeffs[0])
            else:
                seal_trend = 0.0

            # 封单趋势标签
            if seal_trend > 0.1:
                seal_trend_label = '加封中'
            elif seal_trend < -0.1:
                seal_trend_label = '减封中'
            else:
                seal_trend_label = '封单平稳'

            # 更新开板次数：was_limit_up=True → is_limit_up=False
            was_limit_up = state['was_limit_up']
            if was_limit_up and not is_limit_up:
                state['break_count'] += 1

            # 记录首次涨停时间
            if is_limit_up and state['first_limit_time'] is None:
                state['first_limit_time'] = datetime.now().strftime('%H:%M')

            # 更新涨停状态
            state['was_limit_up'] = is_limit_up

            # 换手率（成交额 / 流通市值）
            if float_market_cap > 0:
                turnover_at_limit = round(turnover / float_market_cap * 100, 4)
            else:
                turnover_at_limit = 0.0

            ob_source = (order_book or {}).get('source', 'empty')
            has_order_book = (
                ob_source not in ('empty', '')
                and (bool(bids) or bool(order_book.get('asks')))
            )
            seal_data_valid = bool(is_limit_up and has_order_book)

            return {
                'is_limit_up': is_limit_up,
                'limit_up_price': limit_up_price,
                'seal_amount': seal_amount,
                'seal_volume_lots': seal_volume_lots,
                'seal_ratio': seal_ratio,
                'seal_trend': round(seal_trend, 4),
                'seal_trend_label': seal_trend_label,
                'break_count': state['break_count'],
                'first_limit_time': state['first_limit_time'],
                'turnover_at_limit': turnover_at_limit,
                'seal_data_valid': seal_data_valid,
            }

        except Exception as e:
            logger.error(f"封单分析异常 {code}: {e}", exc_info=True)
            return self._empty_result()
