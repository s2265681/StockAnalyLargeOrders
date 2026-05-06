"""
数据源适配器
负责调用数据源获取原始数据，进行大单识别、分级统计，返回统一格式
"""
import logging
import time
from datetime import datetime, timedelta

from .eastmoney_free import EastMoneyFreeSource
from .eastmoney_l2 import EastMoneyL2Source
from .limit_up_monitor import LimitUpMonitor
from .ths_moneyflow import get_moneyflow

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
CACHE_TTL = 2  # 秒

# Playwright 数据源（懒加载）
_playwright_source = None

def _get_playwright_source():
    global _playwright_source
    if _playwright_source is None:
        try:
            from .eastmoney_playwright import EastMoneyPlaywrightSource
            import os
            # 从系统代理设置自动推断
            proxy = os.environ.get('https_proxy') or os.environ.get('http_proxy') or None
            # 尝试从 macOS 系统代理读取
            if not proxy:
                try:
                    import subprocess
                    r = subprocess.run(['networksetup', '-getsecurewebproxy', 'Wi-Fi'],
                                       capture_output=True, text=True, timeout=2)
                    lines = {l.split(':')[0].strip(): l.split(':', 1)[-1].strip()
                             for l in r.stdout.splitlines() if ':' in l}
                    if lines.get('Enabled', '').lower() == 'yes':
                        host = lines.get('Server', '127.0.0.1')
                        port = lines.get('Port', '7890')
                        proxy = f"http://{host}:{port}"
                except Exception:
                    pass
            if proxy:
                EastMoneyPlaywrightSource.set_proxy(proxy)
                logger.info(f"Playwright 数据源已配置代理: {proxy}")
            _playwright_source = EastMoneyPlaywrightSource()
        except ImportError:
            logger.warning("playwright 未安装，逐笔数据将使用估算模式")
            _playwright_source = None
    return _playwright_source


class DataSourceAdapter:
    """数据源适配器，统一免费/L2数据源，输出标准格式"""

    def __init__(self, use_l2=False):
        if use_l2:
            self.source = EastMoneyL2Source()
            self.source_name = 'eastmoney_l2'
        else:
            self.source = EastMoneyFreeSource()
            self.source_name = 'eastmoney_free'
        self.limit_up_monitor = LimitUpMonitor()

    def get_l2_dashboard(self, code, dt=None, simulate_time=None):
        """获取L2大单看板全量数据，结果缓存5秒"""
        today = datetime.now().strftime('%Y-%m-%d')
        if dt is None:
            dt = today
        is_today = (dt == today)

        cache_key = f'l2_dashboard_{code}_{dt}_{simulate_time or "live"}'
        now = time.time()

        if cache_key in _cache:
            cached_time, cached_data = _cache[cache_key]
            ttl = CACHE_TTL if is_today else 300
            if now - cached_time < ttl:
                return cached_data

        result = self._build_dashboard(code, dt=dt, simulate_time=simulate_time)
        _cache[cache_key] = (now, result)
        return result

    def get_timeshare_data(self, code, dt=None):
        """只返回分时走势 + 股票基础信息（轻量，适合首屏快速渲染）"""
        today = datetime.now().strftime('%Y-%m-%d')
        if dt is None:
            dt = today
        is_today = (dt == today)

        cache_key = f'l2_timeshare_{code}_{dt}'
        now = time.time()
        if cache_key in _cache:
            ts, cached = _cache[cache_key]
            if now - ts < (CACHE_TTL if is_today else 300):
                return cached

        result = self._build_timeshare(code, dt=dt)
        _cache[cache_key] = (now, result)
        return result

    def get_orders_data(self, code, dt=None):
        """只返回大单列表 + 分级统计 + big_map（依赖逐笔，稍慢）"""
        today = datetime.now().strftime('%Y-%m-%d')
        if dt is None:
            dt = today
        is_today = (dt == today)

        cache_key = f'l2_orders_{code}_{dt}'
        now = time.time()
        if cache_key in _cache:
            ts, cached = _cache[cache_key]
            if now - ts < (CACHE_TTL if is_today else 300):
                return cached

        result = self._build_orders(code, dt=dt)
        _cache[cache_key] = (now, result)
        return result

    def _build_timeshare(self, code, dt=None):
        """构建分时 + 股票基础信息（不含逐笔/大单）"""
        today = datetime.now().strftime('%Y-%m-%d')
        if dt is None:
            dt = today
        is_today = (dt == today)

        quote = self.source.get_realtime_quote(code)
        pw = _get_playwright_source()
        # 历史日期：页面 SSE 只有当日分时，Playwright 按日期过滤会得到空列表，必须走 REST trends2
        if pw and is_today:
            try:
                timeshare = pw.get_timeshare(code, dt=dt)
                if not timeshare:
                    timeshare = self.source.get_timeshare(code, dt=dt)
            except Exception as e:
                logger.warning(f"Playwright 分时失败，回退: {e}")
                timeshare = self.source.get_timeshare(code, dt=dt)
        else:
            timeshare = self.source.get_timeshare(code, dt=dt)
        if not quote:
            quote = self._build_fallback_quote(code, dt, timeshare)

        if is_today or not timeshare:
            stock_info = {
                'code': quote['code'], 'name': quote['name'],
                'price': quote['price'], 'yesterday_close': quote['yesterday_close'],
                'open': quote['open'], 'high': quote['high'], 'low': quote['low'],
                'volume': quote['volume'], 'turnover': quote['turnover'],
                'change_percent': quote['change_percent'],
            }
        else:
            hist_kline = self.source.get_daily_kline(code, dt)
            if hist_kline:
                stock_info = {
                    'code': quote['code'], 'name': quote['name'],
                    'price': hist_kline['close'], 'yesterday_close': hist_kline['preclose'],
                    'open': hist_kline['open'], 'high': hist_kline['high'], 'low': hist_kline['low'],
                    'volume': hist_kline['volume'], 'turnover': hist_kline['turnover'],
                    'change_percent': hist_kline['change_percent'],
                }
            else:
                prices = [t['price'] for t in timeshare if t.get('price')]
                stock_info = {
                    'code': quote['code'], 'name': quote['name'],
                    'price': prices[-1] if prices else 0,
                    'yesterday_close': prices[0] if prices else 0,
                    'open': prices[0] if prices else 0,
                    'high': max(prices) if prices else 0,
                    'low': min(prices) if prices else 0,
                    'volume': 0, 'turnover': 0, 'change_percent': 0,
                }

        order_book = (self.source.get_order_book(code)
                       if hasattr(self.source, 'get_order_book') else self._empty_order_book())
        limit_up_data = self.limit_up_monitor.analyze(code, quote, order_book)
        snap = self._session_snapshot(
            code, dt, timeshare, quote, is_today, simulate_time=None,
            order_book=order_book, limit_up_data=limit_up_data,
        )
        return {
            'success': True,
            'data': {
                'stock_info': stock_info,
                'timeshare': timeshare,
                'order_book': order_book,
                'session_snapshot': snap,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        }

    def _session_snapshot(self, code, dt, timeshare, quote, is_today, simulate_time=None,
                          order_book=None, limit_up_data=None):
        """集合竞价成交量、尾盘相对昨日全日量比等（volume 单位：手）"""
        if not timeshare:
            return {}

        order_book = order_book or {}
        limit_up_data = limit_up_data or {}

        def _tkey(t):
            return str(t.get('time', '') or '')[:5]

        auction_rows = [t for t in timeshare if _tkey(t) and _tkey(t) < '09:30']
        auction_vol = 0
        auction_amt = 0.0
        if auction_rows:
            sorted_a = sorted(auction_rows, key=lambda x: _tkey(x))
            fv = int(sorted_a[0].get('volume', 0) or 0)
            lv = int(sorted_a[-1].get('volume', 0) or 0)
            fa = float(sorted_a[0].get('amount', 0) or 0)
            la = float(sorted_a[-1].get('amount', 0) or 0)
            # 累计量额：末减首；否则按分钟相加（兼容不同字段语义）
            if lv >= fv:
                auction_vol = lv - fv
            else:
                auction_vol = sum(int(t.get('volume', 0) or 0) for t in sorted_a)
            if la >= fa:
                auction_amt = max(la - fa, 0.0)
            else:
                auction_amt = sum(float(t.get('amount', 0) or 0) for t in sorted_a)
        auction_last = None
        for t in sorted(auction_rows, key=lambda x: _tkey(x)):
            if t.get('price') is not None:
                auction_last = float(t['price'])

        # 东财 trends2 多数不含 9:15–9:25 竞价点，分时里筛不到竞价价；用今开作匹配价近似（与 9:25 统一价一致）
        auction_from_open_fallback = False
        if auction_last is None and quote:
            op = float(quote.get('open', 0) or 0)
            if op > 0:
                auction_last = op
                auction_from_open_fallback = True

        # 模拟切片：必须用分时累计量；否则当日优先用行情接口总量（更贴近交易所）
        if simulate_time:
            day_vol = sum(int(t.get('volume', 0) or 0) for t in timeshare)
        elif is_today and quote and quote.get('volume'):
            day_vol = int(quote['volume'])
        else:
            day_vol = sum(int(t.get('volume', 0) or 0) for t in timeshare)

        yvol = None
        try:
            d0 = datetime.strptime(dt, '%Y-%m-%d')
            for i in range(1, 15):
                d1 = d0 - timedelta(days=i)
                if d1.weekday() >= 5:
                    continue
                pd = d1.strftime('%Y-%m-%d')
                yk = self.source.get_daily_kline(code, pd)
                if yk and yk.get('volume'):
                    yvol = int(yk['volume'])
                    break
        except Exception as e:
            logger.debug(f"session_snapshot 昨日量: {e}")

        prev_close = float(quote.get('yesterday_close', 0) or 0) if quote else 0.0
        auction_chg = None
        if auction_last and prev_close > 0:
            auction_chg = round((auction_last - prev_close) / prev_close * 100, 2)

        ratio = None
        if yvol and yvol > 0 and day_vol >= 0:
            ratio = round(day_vol / yvol * 100, 1)

        # 五档卖单合计（手）：盘口 volume 为股
        total_ask_volume_hands = None
        asks = order_book.get('asks') or []
        if asks:
            share_sum = sum(int(a.get('volume', 0) or 0) for a in asks)
            if share_sum > 0:
                total_ask_volume_hands = round(share_sum / 100, 2)

        # 封成比：涨停封单金额 / 当日成交额（%）
        seal_to_turnover_percent = None
        seal_wan = float(limit_up_data.get('seal_amount', 0) or 0)
        turnover = float(quote.get('turnover', 0) or 0) if quote else 0.0
        if seal_wan > 0 and turnover > 0:
            seal_to_turnover_percent = round(seal_wan * 10000 / turnover * 100, 2)

        return {
            'auction_last_price': auction_last,
            'auction_change_percent': auction_chg,
            'auction_volume_hands': auction_vol,
            'auction_amount': round(auction_amt, 2),
            'auction_from_open_fallback': auction_from_open_fallback,
            'today_volume_hands': day_vol,
            'yesterday_volume_hands': yvol,
            'volume_vs_yesterday_percent': ratio,
            'total_ask_volume_hands': total_ask_volume_hands,
            'seal_to_turnover_percent': seal_to_turnover_percent,
        }

    def _build_orders(self, code, dt=None):
        """构建大单列表 + 分级统计 + big_map（依赖逐笔数据）"""
        today = datetime.now().strftime('%Y-%m-%d')
        if dt is None:
            dt = today

        pw = _get_playwright_source()
        if pw:
            try:
                tick_result = pw.get_tick_details(code, dt=dt)
                if not tick_result.get('details'):
                    tick_result = self.source.get_tick_details(code, dt=dt)
            except Exception as e:
                logger.warning(f"Playwright 逐笔失败，回退: {e}")
                tick_result = self.source.get_tick_details(code, dt=dt)
        else:
            tick_result = self.source.get_tick_details(code, dt=dt)
        all_details = tick_result.get('details', [])

        is_today = dt == today
        if not all_details:
            # 无逐笔时用分时估算（仅当日复用 Playwright 分时缓存）
            if pw and is_today:
                try:
                    timeshare = pw.get_timeshare(code, dt=dt)
                except Exception:
                    timeshare = self.source.get_timeshare(code, dt=dt)
            else:
                timeshare = self.source.get_timeshare(code, dt=dt)
            all_details = self._build_minute_amount_details(timeshare)

        self._annotate_directions(all_details)
        large_orders = self._identify_large_orders(all_details)
        statistics = self._calculate_statistics(all_details)
        big_map = self._build_big_map(large_orders)

        return {
            'success': True,
            'data': {
                'large_orders': large_orders,
                'orders': large_orders,
                'statistics': statistics,
                'big_map': big_map,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        }

    def _build_dashboard(self, code, dt=None, simulate_time=None):
        """构建完整的看板数据"""
        today = datetime.now().strftime('%Y-%m-%d')
        if dt is None:
            dt = today
        is_today = (dt == today)

        # 1. 获取实时行情（总是获取最新的）
        quote = self.source.get_realtime_quote(code)

        # 2. 获取逐笔成交明细：优先用 Playwright（绕过 TLS 指纹检测），失败回退到原接口
        pw = _get_playwright_source()
        if pw:
            try:
                tick_result = pw.get_tick_details(code, dt=dt)
                n = len(tick_result.get('details', []))
                logger.info(f"Playwright 逐笔: {n} 条")
                if n == 0:
                    tick_result = self.source.get_tick_details(code, dt=dt)
            except Exception as e:
                logger.warning(f"Playwright 逐笔失败，回退: {e}")
                tick_result = self.source.get_tick_details(code, dt=dt)
        else:
            tick_result = self.source.get_tick_details(code, dt=dt)
        all_details = tick_result.get('details', [])

        # 3. 获取分时走势：仅当日走 Playwright（历史日页面无该日 trends）
        if pw and is_today:
            try:
                timeshare = pw.get_timeshare(code, dt=dt)
                if not timeshare:
                    timeshare = self.source.get_timeshare(code, dt=dt)
            except Exception as e:
                logger.warning(f"Playwright 分时失败，回退: {e}")
                timeshare = self.source.get_timeshare(code, dt=dt)
        else:
            timeshare = self.source.get_timeshare(code, dt=dt)
        if not quote:
            quote = self._build_fallback_quote(code, dt, timeshare)
        order_book = self.source.get_order_book(code) if hasattr(self.source, 'get_order_book') else self._empty_order_book()

        # 4. 标注买卖方向。免费源的中性盘按相邻价格变化归因，便于统一红/绿展示。
        self._annotate_directions(all_details)
        if not all_details:
            all_details = self._build_minute_amount_details(timeshare)

        if simulate_time:
            timeshare, all_details = self._slice_intraday_data(timeshare, all_details, simulate_time)

        # 5. 识别大单并分级
        large_orders = self._identify_large_orders(all_details)
        statistics = self._calculate_statistics(all_details)
        big_map = self._build_big_map(large_orders)

        # 构建 stock_info，历史日期从分时数据推导
        if is_today or not timeshare:
            stock_info = {
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
            }
        else:
            # 历史日期：从分时数据和日K线推导
            prices = [t['price'] for t in timeshare if t.get('price')]
            hist_kline = self.source.get_daily_kline(code, dt)
            if hist_kline:
                stock_info = {
                    'code': quote['code'],
                    'name': quote['name'],
                    'price': hist_kline['close'],
                    'yesterday_close': hist_kline['preclose'],
                    'open': hist_kline['open'],
                    'high': hist_kline['high'],
                    'low': hist_kline['low'],
                    'volume': hist_kline['volume'],
                    'turnover': hist_kline['turnover'],
                    'change_percent': hist_kline['change_percent'],
                }
            elif quote and quote.get('yesterday_close') and quote.get('price'):
                stock_info = {
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
                }
            else:
                # 回退：从分时数据推导
                high = max(prices) if prices else 0
                low = min(prices) if prices else 0
                last_price = prices[-1] if prices else 0
                open_price = prices[0] if prices else 0
                stock_info = {
                    'code': quote['code'],
                    'name': quote['name'],
                    'price': last_price,
                    'yesterday_close': open_price,  # 近似值
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'volume': 0,
                    'turnover': 0,
                    'change_percent': round((last_price - open_price) / open_price * 100, 2) if open_price else 0,
                }

        # 6. 封单监控
        limit_up_data = self.limit_up_monitor.analyze(code, quote, order_book)

        snap = self._session_snapshot(
            code, dt, timeshare, quote, is_today, simulate_time=simulate_time,
            order_book=order_book, limit_up_data=limit_up_data,
        )

        # 7. 同花顺资金分时（超大单/大单/小单流入流出）
        moneyflow = {}
        if is_today:
            try:
                moneyflow = get_moneyflow(code)
            except Exception as e:
                logger.warning(f"同花顺资金分时获取失败: {e}")

        return {
            'success': True,
            'data': {
                'stock_info': stock_info,
                'timeshare': timeshare,
                'statistics': statistics,
                'large_orders': large_orders,
                'orders': large_orders,
                'big_map': big_map,
                'order_book': order_book,
                'session_snapshot': snap,
                'limit_up_monitor': limit_up_data,
                'moneyflow': moneyflow,
                'simulation': {
                    'enabled': bool(simulate_time),
                    'simulate_time': simulate_time,
                },
                'data_source': self.source_name,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        }

    def _slice_intraday_data(self, timeshare, details, simulate_time):
        """按模拟时间裁剪分时和逐笔数据"""
        cutoff = simulate_time[:5]

        def minute_of(value):
            return str(value or '')[:5]

        sliced_timeshare = [
            point for point in timeshare
            if minute_of(point.get('time')) <= cutoff
        ]
        sliced_details = [
            detail for detail in details
            if minute_of(detail.get('time')) <= cutoff
        ]
        return sliced_timeshare, sliced_details

    def _build_fallback_quote(self, code, dt, timeshare):
        """实时行情接口不可用时，用日K/分时/基础信息兜底，避免整页失败"""
        hist_kline = self.source.get_daily_kline(code, dt) if dt else None
        prices = [p['price'] for p in timeshare if p.get('price')]

        if hist_kline:
            price = hist_kline['close']
            return {
                'code': code,
                'name': self._get_fallback_stock_name(code),
                'price': price,
                'yesterday_close': hist_kline['preclose'],
                'open': hist_kline['open'],
                'high': hist_kline['high'],
                'low': hist_kline['low'],
                'volume': hist_kline['volume'],
                'turnover': hist_kline['turnover'],
                'change_percent': hist_kline['change_percent'],
            }

        limit_up_quote = self._get_limit_up_quote(code, dt)
        if limit_up_quote:
            return limit_up_quote

        if prices:
            open_price = prices[0]
            last_price = prices[-1]
            return {
                'code': code,
                'name': self._get_fallback_stock_name(code),
                'price': last_price,
                'yesterday_close': open_price,
                'open': open_price,
                'high': max(prices),
                'low': min(prices),
                'volume': sum(p.get('volume', 0) for p in timeshare),
                'turnover': sum(p.get('amount', 0) for p in timeshare),
                'change_percent': round((last_price - open_price) / open_price * 100, 2) if open_price else 0,
            }

        try:
            from routes.stock_basic import get_stock_basic_data
            basic = get_stock_basic_data(code)
            return {
                'code': code,
                'name': basic.get('name', self._get_fallback_stock_name(code)),
                'price': basic.get('current_price', 0),
                'yesterday_close': basic.get('yesterday_close', 0),
                'open': basic.get('open', 0),
                'high': basic.get('high', 0),
                'low': basic.get('low', 0),
                'volume': basic.get('volume', 0),
                'turnover': basic.get('turnover', 0),
                'change_percent': basic.get('change_percent', 0),
            }
        except Exception as e:
            logger.warning(f"基础信息兜底失败: {e}")

        return {
            'code': code,
            'name': self._get_fallback_stock_name(code),
            'price': 0,
            'yesterday_close': 0,
            'open': 0,
            'high': 0,
            'low': 0,
            'volume': 0,
            'turnover': 0,
            'change_percent': 0,
        }

    def _empty_order_book(self):
        return {
            'bids': [],
            'asks': [],
            'spread': 0,
            'bid_amount': 0,
            'ask_amount': 0,
        }

    def _get_fallback_stock_name(self, code):
        try:
            from utils.stock_utils import get_stock_name_by_code
            return get_stock_name_by_code(code)
        except Exception:
            return f'股票{code}'

    def _get_limit_up_quote(self, code, dt):
        """日K不可用时，从涨停池补充涨跌幅和昨收，避免一字板被画成0%"""
        if not dt:
            return None

        try:
            import akshare as ak

            df = ak.stock_zt_pool_em(date=dt.replace('-', ''))
            if df is None or df.empty:
                return None

            code_str = str(code).zfill(6)
            row_df = df[df['代码'].astype(str).str.zfill(6) == code_str]
            if row_df.empty:
                return None

            row = row_df.iloc[0]
            price = float(row.get('最新价', 0) or 0)
            change_percent = float(row.get('涨跌幅', 0) or 0)
            if not price:
                return None

            yesterday_close = round(price / (1 + change_percent / 100), 2) if change_percent else price
            return {
                'code': code_str,
                'name': row.get('名称', self._get_fallback_stock_name(code_str)),
                'price': price,
                'yesterday_close': yesterday_close,
                'open': price,
                'high': price,
                'low': price,
                'volume': 0,
                'turnover': float(row.get('成交额', 0) or 0),
                'change_percent': round(change_percent, 2),
            }
        except Exception as e:
            logger.warning(f"涨停池行情兜底失败: {e}")
            return None

    def _annotate_directions(self, details):
        """为逐笔成交标注买卖方向，中性盘按价格变化归因到买/卖"""
        previous_price = None
        last_direction = None

        for detail in sorted(details, key=lambda x: x.get('time', '')):
            direction = self.source.infer_direction(detail['type'])

            if direction == '中性':
                price = detail.get('price')
                if previous_price is not None and price is not None:
                    direction = '被买' if price >= previous_price else '被卖'
                else:
                    direction = last_direction or '被买'
                detail['direction_inferred'] = True
            else:
                detail['direction_inferred'] = False

            detail['direction'] = direction
            previous_price = detail.get('price', previous_price)
            if direction in ('被买', '主买', '被卖', '主卖'):
                last_direction = direction

    def _build_minute_amount_details(self, timeshare):
        """历史逐笔为空时，用分钟K线成交额估算大单统计和图上标注"""
        details = []
        previous_price = None
        for point in timeshare:
            amount = point.get('amount')
            price = point.get('price')
            volume = point.get('volume', 0)
            if not amount or amount < LEVEL_THRESHOLDS['above_30']:
                previous_price = price
                continue

            direction = '被买' if previous_price is None or price >= previous_price else '被卖'
            details.append({
                'time': point.get('time', ''),
                'price': price,
                'volume': volume,
                'amount': amount,
                'type': 1 if direction in ('主买', '被买') else 2,
                'direction': direction,
                'estimated': True,
            })
            previous_price = price
        return details

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
                'neutral_count': 0, 'neutral_amount': 0.0,
            }

        for d in details:
            amount = d['amount']
            direction = d['direction']
            is_buy = direction in ('被买', '主买')
            is_sell = direction in ('被卖', '主卖')
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
            elif is_sell:
                stats[level_key]['sell_count'] += 1
                stats[level_key]['sell_amount'] = round(stats[level_key]['sell_amount'] + amount_wan, 2)
            else:
                stats[level_key]['neutral_count'] += 1
                stats[level_key]['neutral_amount'] = round(stats[level_key]['neutral_amount'] + amount_wan, 2)

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
                'time': order['time'],
                'price': order['price'],
                'volume': order['volume_lots'],
                'amount': order['amount'],
            })

        return big_map
