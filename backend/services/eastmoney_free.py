"""
东方财富免费API数据获取服务
提供实时行情、逐笔成交明细、分时走势数据
"""
import requests
import logging
import time
from datetime import datetime

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

    def _get_akshare_symbol(self, code):
        if code.startswith(('0', '3')):
            return f'sz{code}'
        if code.startswith('6'):
            return f'sh{code}'
        return f'sz{code}'

    @staticmethod
    def parse_trend_item(item):
        """解析东方财富分时行：时间,开,收,高,低,成交量(手),成交额,均价"""
        parts = item.split(',')
        if len(parts) < 8:
            return None

        time_full = parts[0]
        time_str = time_full.split(' ')[1] if ' ' in time_full else time_full
        return {
            'time': time_str,
            'price': float(parts[1]),
            'volume': int(float(parts[5])),
            'amount': float(parts[6]) if parts[6] else 0.0,
            'avg_price': float(parts[7]) if parts[7] else float(parts[1]),
        }

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

    def get_tick_details(self, code, pos=-100000, dt=None):
        """获取逐笔成交明细
        Args:
            code: 股票代码
            pos: 位置参数，默认尽量获取当天完整成交明细
            dt: 日期，格式 YYYY-MM-DD，默认当天
        Returns:
            dict: {
                'details': [{'time': str, 'price': float, 'volume': int(手), 'amount': float(元), 'type': int(1=买 2=卖 4=中性)}],
                'pos': int
            }
        """
        today = datetime.now().strftime('%Y-%m-%d')
        is_today = (dt is None or dt == today)

        market_code = self._get_market_code(code)

        # 历史日期使用历史成交明细接口
        if not is_today:
            return self._get_history_tick_details(code, dt)

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
                return self._get_intraday_details_akshare(code, dt)

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
            return self._get_intraday_details_akshare(code, dt)

    def get_timeshare(self, code, dt=None):
        """获取分时走势数据
        Args:
            code: 股票代码
            dt: 日期，格式 YYYY-MM-DD，默认当天
        Returns:
            list of dict: [{'time': str, 'price': float, 'avg_price': float, 'volume': int(手)}]
        """
        today = datetime.now().strftime('%Y-%m-%d')
        is_today = (dt is None or dt == today)

        if not is_today:
            return self._get_history_timeshare(code, dt)

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
                return self._get_minute_timeshare_akshare(code, dt)

            trends_raw = data['data'].get('trends', [])
            result = []

            for item in trends_raw:
                parsed = self.parse_trend_item(item)
                if parsed:
                    result.append(parsed)

            return result
        except Exception as e:
            logger.error(f"获取分时数据失败: {e}")
            return self._get_minute_timeshare_akshare(code, dt)

    def _get_history_timeshare(self, code, dt):
        """使用1分钟K线接口获取历史日期的分时数据
        Args:
            code: 股票代码
            dt: 日期，格式 YYYY-MM-DD
        Returns:
            list of dict: [{'time': str, 'price': float, 'avg_price': float, 'volume': int(手)}]
        """
        market_code = self._get_market_code(code)
        date_compact = dt.replace('-', '')  # YYYYMMDD
        url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': 1,       # 1分钟K线
            'fqt': 1,       # 前复权
            'beg': date_compact,
            'end': date_compact,
            'lmt': 242,     # 一个交易日最多约242条1分钟K线
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富历史分钟K线接口返回异常: {data}")
                return self._get_minute_timeshare_akshare(code, dt)

            klines_raw = data['data'].get('klines', [])
            result = []
            cumulative_turnover = 0.0
            cumulative_volume = 0

            for item in klines_raw:
                parts = item.split(',')
                if len(parts) < 7:
                    continue

                # 1分钟K线格式: 时间,开,收,高,低,成交量(手),成交额,振幅,涨跌幅,涨跌额,换手率
                time_full = parts[0]  # "2026-04-27 09:31"
                time_str = time_full.split(' ')[1] if ' ' in time_full else time_full
                close_price = float(parts[2])  # 收盘价（该分钟最后成交价）
                volume = int(float(parts[5]))  # 成交量（手）
                turnover = float(parts[6])     # 成交额

                cumulative_turnover += turnover
                cumulative_volume += volume
                avg_price = cumulative_turnover / (cumulative_volume * 100) if cumulative_volume > 0 else close_price

                result.append({
                    'time': time_str,
                    'price': close_price,
                    'volume': volume,
                    'amount': turnover,
                    'avg_price': round(avg_price, 3),
                })

            if result:
                return result

            return self._get_minute_timeshare_akshare(code, dt)
        except Exception as e:
            logger.error(f"获取历史分时数据失败({dt}): {e}")
            return self._get_minute_timeshare_akshare(code, dt)

    def _get_minute_timeshare_akshare(self, code, dt=None):
        """使用 akshare 新浪分钟数据兜底，恢复最新交易日分时"""
        try:
            import akshare as ak

            symbol = self._get_akshare_symbol(code)
            df = ak.stock_zh_a_minute(symbol=symbol, period='1', adjust='')
            if df is None or df.empty or 'day' not in df.columns:
                return []

            target_dt = dt
            if not target_dt:
                target_dt = str(df.iloc[-1]['day'])[:10]

            day_df = df[df['day'].astype(str).str[:10] == target_dt].copy()
            if day_df.empty:
                latest_dt = str(df.iloc[-1]['day'])[:10]
                day_df = df[df['day'].astype(str).str[:10] == latest_dt].copy()

            result = []
            cumulative_turnover = 0.0
            cumulative_volume_shares = 0
            for _, row in day_df.iterrows():
                time_str = str(row['day'])[11:16]
                close_price = float(row['close'])
                volume_shares = int(float(row.get('volume', 0) or 0))
                turnover = close_price * volume_shares
                cumulative_turnover += turnover
                cumulative_volume_shares += volume_shares
                avg_price = cumulative_turnover / cumulative_volume_shares if cumulative_volume_shares else close_price
                result.append({
                    'time': time_str,
                    'price': close_price,
                    'volume': int(volume_shares / 100),
                    'amount': round(turnover, 2),
                    'avg_price': round(avg_price, 3),
                })

            return result
        except Exception as e:
            logger.error(f"akshare分钟分时兜底失败({dt}): {e}")
            return []

    def get_daily_kline(self, code, dt):
        """获取指定日期的日K线数据（含昨收）
        Args:
            code: 股票代码
            dt: 日期，格式 YYYY-MM-DD
        Returns:
            dict: {open, close, high, low, volume, turnover, preclose, change_percent} 或 None
        """
        market_code = self._get_market_code(code)
        date_compact = dt.replace('-', '')
        url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': 101,    # 日K线
            'fqt': 1,
            'beg': date_compact,
            'end': date_compact,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('rc') != 0 or not data.get('data'):
                return None

            klines = data['data'].get('klines', [])
            if not klines:
                return None

            # 日K线格式: 日期,开,收,高,低,成交量(手),成交额,振幅,涨跌幅,涨跌额,换手率
            parts = klines[0].split(',')
            if len(parts) < 9:
                return None

            close = float(parts[2])
            change_percent = float(parts[8])
            # 从涨跌幅反推昨收: preclose = close / (1 + change_percent/100)
            preclose = round(close / (1 + change_percent / 100), 2) if change_percent != 0 else close

            return {
                'open': float(parts[1]),
                'close': close,
                'high': float(parts[3]),
                'low': float(parts[4]),
                'volume': int(float(parts[5])),
                'turnover': float(parts[6]),
                'preclose': preclose,
                'change_percent': change_percent,
            }
        except Exception as e:
            logger.error(f"获取日K线数据失败({dt}): {e}")
            return None

    def _get_history_tick_details(self, code, dt):
        """获取历史日期的逐笔成交明细
        使用东方财富历史成交明细接口
        Args:
            code: 股票代码
            dt: 日期，格式 YYYY-MM-DD
        Returns:
            dict: {'details': [...], 'pos': 0}
        """
        market_code = self._get_market_code(code)
        # 历史逐笔明细使用不同的接口
        url = 'https://push2his.eastmoney.com/api/qt/stock/details/get'
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4',
            'fields2': 'f51,f52,f53,f54,f55',
            'pos': -1,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'fltt': 2,
            'cb': '',
            'dates': dt.replace('-', ''),  # 格式: 20250716
        }

        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富历史成交明细接口返回异常: {data}")
                return self._get_intraday_details_akshare(code, dt)

            details_raw = data['data'].get('details', [])
            details = []

            for item in details_raw:
                parts = item.split(',')
                if len(parts) < 4:
                    continue

                time_str = parts[0]
                price = float(parts[1])
                volume = int(parts[2])
                buy_sell_type = int(parts[3])

                details.append({
                    'time': time_str,
                    'price': price,
                    'volume': volume,
                    'amount': round(price * volume * 100, 2),
                    'type': buy_sell_type
                })

            return {'details': details, 'pos': 0}
        except Exception as e:
            logger.error(f"获取历史成交明细失败({dt}): {e}")
            return self._get_intraday_details_akshare(code, dt)

    def _get_intraday_details_akshare(self, code, dt=None):
        """使用 akshare 当日分笔成交兜底，尽量恢复大单明细"""
        try:
            import akshare as ak

            df = ak.stock_intraday_em(symbol=code)
            if df is None or df.empty:
                return {'details': [], 'pos': 0}

            type_map = {
                '买盘': 1,
                '卖盘': 2,
                '中性盘': 4,
            }
            details = []
            for _, row in df.iterrows():
                price = float(row.get('成交价', 0) or 0)
                volume = int(float(row.get('手数', 0) or 0))
                if not price or not volume:
                    continue
                details.append({
                    'time': str(row.get('时间', ''))[:8],
                    'price': price,
                    'volume': volume,
                    'amount': round(price * volume * 100, 2),
                    'type': type_map.get(row.get('买卖盘性质'), 4),
                })

            return {'details': details, 'pos': 0}
        except Exception as e:
            logger.error(f"akshare分笔成交兜底失败: {e}")
            return self._get_intraday_details_sina(code, dt)

    def _get_intraday_details_sina(self, code, dt=None):
        """使用新浪分笔成交兜底，支持指定交易日"""
        if not dt:
            return {'details': [], 'pos': 0}

        try:
            import akshare as ak

            df = ak.stock_intraday_sina(
                symbol=self._get_akshare_symbol(code),
                date=dt.replace('-', ''),
            )
            if df is None or df.empty:
                return {'details': [], 'pos': 0}

            kind_map = {
                'U': 1,
                'D': 2,
                'E': 4,
            }
            details = []
            for _, row in df.iterrows():
                price = float(row.get('price', 0) or 0)
                volume_shares = int(float(row.get('volume', 0) or 0))
                if not price or not volume_shares:
                    continue
                details.append({
                    'time': str(row.get('ticktime', ''))[:8],
                    'price': price,
                    'volume': int(volume_shares / 100),
                    'amount': round(price * volume_shares, 2),
                    'type': kind_map.get(row.get('kind'), 4),
                })

            return {'details': details, 'pos': 0}
        except Exception as e:
            logger.error(f"新浪分笔成交兜底失败({dt}): {e}")
            return {'details': [], 'pos': 0}

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
