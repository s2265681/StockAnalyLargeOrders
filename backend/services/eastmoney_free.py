"""
东方财富免费API数据获取服务
提供实时行情、逐笔成交明细、分时走势数据
"""
import requests
import logging
import time

logger = logging.getLogger(__name__)

class EastMoneyFreeSource:
    """东方财富免费数据源"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/'
        })

    def _get_market_code(self, code):
        """将股票代码转换为东方财富市场代码格式
        Args:
            code: 6位股票代码，如 '000001'
        Returns:
            东方财富格式代码，如 '0.000001' (深圳) 或 '1.600000' (上海)
        """
        if code.startswith(('0', '3')):
            return f'0.{code}'
        elif code.startswith('6'):
            return f'1.{code}'
        else:
            return f'0.{code}'

    def get_realtime_quote(self, code):
        """获取实时行情（含买一/卖一价，用于推算方向）
        Args:
            code: 股票代码
        Returns:
            dict with keys: code, name, price, yesterday_close, open, high, low, volume, turnover, bid1_price, ask1_price, change_percent
            Returns None on failure.
        """
        market_code = self._get_market_code(code)
        url = 'https://push2.eastmoney.com/api/qt/stock/get'
        params = {
            'secid': market_code,
            'fields': 'f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f169,f170',
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'fltt': 2
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富行情接口返回异常: {data}")
                return None

            d = data['data']
            return {
                'code': code,
                'name': d.get('f58', ''),
                'price': d.get('f43', 0) / 100 if isinstance(d.get('f43'), int) else d.get('f43', 0),
                'yesterday_close': d.get('f60', 0) / 100 if isinstance(d.get('f60'), int) else d.get('f60', 0),
                'open': d.get('f46', 0) / 100 if isinstance(d.get('f46'), int) else d.get('f46', 0),
                'high': d.get('f44', 0) / 100 if isinstance(d.get('f44'), int) else d.get('f44', 0),
                'low': d.get('f45', 0) / 100 if isinstance(d.get('f45'), int) else d.get('f45', 0),
                'volume': d.get('f47', 0),
                'turnover': d.get('f48', 0),
                'bid1_price': d.get('f51', 0) / 100 if isinstance(d.get('f51'), int) else d.get('f51', 0),
                'ask1_price': d.get('f52', 0) / 100 if isinstance(d.get('f52'), int) else d.get('f52', 0),
                'change_percent': d.get('f170', 0) / 100 if isinstance(d.get('f170'), int) else d.get('f170', 0),
            }
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}")
            return None

    def get_tick_details(self, code, pos=-1):
        """获取逐笔成交明细
        Args:
            code: 股票代码
            pos: 位置参数，-1 表示获取最新数据
        Returns:
            dict: {
                'details': [{'time': str, 'price': float, 'volume': int(手), 'amount': float(元), 'type': int(1=买 2=卖 4=中性)}],
                'pos': int
            }
        """
        market_code = self._get_market_code(code)
        url = 'https://push2.eastmoney.com/api/qt/stock/details/get'
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4',
            'fields2': 'f51,f52,f53,f54,f55',
            'pos': pos,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'fltt': 2
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富成交明细接口返回异常: {data}")
                return {'details': [], 'pos': pos}

            details_raw = data['data'].get('details', [])
            new_pos = data['data'].get('pos', pos)
            details = []

            for item in details_raw:
                parts = item.split(',')
                if len(parts) < 4:
                    continue

                time_str = parts[0]
                price = float(parts[1])
                volume = int(parts[2])  # 手
                buy_sell_type = int(parts[3])

                details.append({
                    'time': time_str,
                    'price': price,
                    'volume': volume,
                    'amount': round(price * volume * 100, 2),  # 手转股再算金额
                    'type': buy_sell_type
                })

            return {'details': details, 'pos': new_pos}
        except Exception as e:
            logger.error(f"获取成交明细失败: {e}")
            return {'details': [], 'pos': pos}

    def get_timeshare(self, code):
        """获取当日分时走势数据
        Args:
            code: 股票代码
        Returns:
            list of dict: [{'time': str, 'price': float, 'avg_price': float, 'volume': int(手)}]
        """
        market_code = self._get_market_code(code)
        url = 'https://push2his.eastmoney.com/api/qt/stock/trends2/get'
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
            'iscr': 0,
            'ndays': 1,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富分时接口返回异常: {data}")
                return []

            trends_raw = data['data'].get('trends', [])
            result = []

            for item in trends_raw:
                parts = item.split(',')
                if len(parts) < 7:
                    continue

                time_full = parts[0]
                time_str = time_full.split(' ')[1] if ' ' in time_full else time_full

                result.append({
                    'time': time_str,
                    'price': float(parts[1]),
                    'volume': int(float(parts[2])),
                    'avg_price': float(parts[6]) if parts[6] else float(parts[1]),
                })

            return result
        except Exception as e:
            logger.error(f"获取分时数据失败: {e}")
            return []

    def infer_direction(self, buy_sell_type):
        """将东方财富的成交类型转换为买卖方向
        1 = 买盘(主动买入) → '被买'
        2 = 卖盘(主动卖出) → '被卖'
        4 = 中性盘 → '中性'
        """
        if buy_sell_type == 1:
            return '被买'
        elif buy_sell_type == 2:
            return '被卖'
        else:
            return '中性'
