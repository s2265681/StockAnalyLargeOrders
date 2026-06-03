"""
东方财富免费API数据获取服务
提供实时行情、逐笔成交明细、分时走势数据
"""
import os
import sys
import json
import requests
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cookie 持久化文件路径（与本文件同目录）
_COOKIE_FILE = os.path.join(os.path.dirname(__file__), '..', 'em_cookie.json')


def _safe_request(func, timeout_seconds=8, retry=1):
    """为网络请求添加可靠的超时保护，支持简单退避重试。
    优先使用 eventlet.Timeout；若 eventlet 导致请求异常，
    回退到子进程执行，彻底绕过 monkey_patch 的干扰。
    """
    for attempt in range(retry + 1):
        try:
            import eventlet
            with eventlet.Timeout(timeout_seconds):
                return func()
        except ImportError:
            try:
                return func()
            except Exception:
                return None
        except Exception:
            if attempt < retry:
                time.sleep(0.5 * (attempt + 1))
                continue
            return None
    return None


def _subprocess_fetch_json(url, headers=None, cookies=None, timeout=10):
    """在子进程中用 curl 获取 JSON，彻底绕过 eventlet monkey_patch 对 SSL 的干扰。"""
    import subprocess, json as _json
    cmd = ['curl', '-s', '--max-time', str(timeout), url]
    if headers:
        for k, v in headers.items():
            cmd += ['-H', f'{k}: {v}']
    if cookies:
        cmd += ['-b', cookies]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        if result.returncode == 0 and result.stdout.strip():
            return _json.loads(result.stdout)
    except Exception as e:
        logger.warning(f"subprocess curl 失败: {e}")
    return None


def _subprocess_fetch_akshare_bid_ask(code: str, timeout: int = 12) -> dict | None:
    """在独立子进程中调用 akshare 五档盘口，绕过 eventlet 对网络库的干扰。"""
    import subprocess
    script = (
        "import akshare as ak, json, sys\n"
        "code = json.loads(sys.argv[1])\n"
        "df = ak.stock_bid_ask_em(symbol=code)\n"
        "print(json.dumps(dict(zip(df['item'].tolist(), df['value'].tolist()))))\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, '-c', script, json.dumps(code)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except Exception as e:
        logger.warning(f"subprocess akshare 盘口失败 {code}: {e}")
    return None


class EastMoneyFreeSource:
    """东方财富免费数据源"""

    # 类级别：跟踪最近一次成功调用时间（被动健康状态）
    _last_success_ts: float = 0.0
    _last_error: str = ''

    # 类级别：存储登录 Cookie 字符串，所有实例共享
    _em_cookie: str = ''

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://quote.eastmoney.com/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': 'https://quote.eastmoney.com',
        })
        # 盘口数据缓存：{code: (raw_data_dict, timestamp)}，供 get_order_book 复用
        self._ob_cache: dict = {}
        # 启动时从文件加载 Cookie
        self._load_cookie_from_file()

    # ── Cookie 管理 ──────────────────────────────────────────────────────────

    @classmethod
    def set_em_cookie(cls, cookie_str: str):
        """更新登录 Cookie，并持久化到文件，所有实例下次请求立即生效"""
        cls._em_cookie = cookie_str.strip()
        try:
            path = os.path.normpath(_COOKIE_FILE)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'cookie': cls._em_cookie, 'updated_at': time.time()}, f)
            logger.info(f"东方财富 Cookie 已保存到 {path}")
        except Exception as e:
            logger.warning(f"Cookie 持久化失败: {e}")

    @classmethod
    def get_cookie_status(cls) -> dict:
        """返回 Cookie 设置状态"""
        has_cookie = bool(cls._em_cookie)
        return {
            'has_cookie': has_cookie,
            'cookie_preview': cls._em_cookie[:40] + '...' if len(cls._em_cookie) > 40 else cls._em_cookie,
        }

    def _load_cookie_from_file(self):
        """从文件加载持久化的 Cookie（仅在类变量为空时执行）"""
        if EastMoneyFreeSource._em_cookie:
            return
        try:
            path = os.path.normpath(_COOKIE_FILE)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                cookie = data.get('cookie', '')
                if cookie:
                    EastMoneyFreeSource._em_cookie = cookie
                    logger.info("已从文件加载东方财富登录 Cookie")
        except Exception as e:
            logger.warning(f"加载 Cookie 文件失败: {e}")

    def _make_auth_session(self) -> requests.Session:
        """返回一个携带登录 Cookie 的临时 Session（不影响主 session）"""
        s = requests.Session()
        s.headers.update(self.session.headers)
        if EastMoneyFreeSource._em_cookie:
            s.headers['Cookie'] = EastMoneyFreeSource._em_cookie
        return s

    @classmethod
    def get_health(cls) -> dict:
        """返回东方财富 API 的被动健康状态（不发额外请求）"""
        import time
        now = time.time()
        age = now - cls._last_success_ts if cls._last_success_ts else None
        if age is None:
            status = 'unknown'
        elif age < 120:
            status = 'online'
        elif age < 600:
            status = 'degraded'
        else:
            status = 'offline'
        return {
            'status': status,
            'eastmoney': status in ('online', 'degraded'),
            'last_success_ago_s': round(age) if age is not None else None,
            'last_error': cls._last_error,
        }

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

    def get_daily_change_percent(self, code, dt):
        """用腾讯日线收盘价计算指定日期涨跌幅，作为东方财富日K为空时的轻量兜底。"""
        try:
            target_dt = datetime.strptime(dt, '%Y-%m-%d')
        except ValueError:
            return None

        symbol = self._get_akshare_symbol(code)
        start_dt = (target_dt - timedelta(days=30)).strftime('%Y-%m-%d')
        from urllib.parse import urlencode
        params = {
            'param': f'{symbol},day,{start_dt},{dt},40,qfq',
        }
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?{urlencode(params)}"

        data = _subprocess_fetch_json(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://gu.qq.com/',
        })
        if not data or data.get('code') != 0:
            return None

        try:
            stock_data = data.get('data', {}).get(symbol, {})
            rows = stock_data.get('qfqday') or stock_data.get('day') or []
            target_index = next((i for i, row in enumerate(rows) if row and row[0] == dt), None)
            if target_index is None or target_index <= 0:
                return None

            prev_close = float(rows[target_index - 1][2])
            close = float(rows[target_index][2])
            if prev_close <= 0:
                return None
            return round((close - prev_close) / prev_close * 100, 2)
        except Exception as e:
            logger.warning(f"腾讯日线涨幅解析失败 code={code} date={dt}: {e}")
            return None

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
        """获取实时行情（同时预取五档盘口，供 get_order_book 复用，减少请求数）
        Args:
            code: 股票代码
        Returns:
            dict with keys: code, name, price, yesterday_close, open, high, low,
                            volume, turnover, bid1_price, ask1_price, change_percent
            Returns None on failure.
        """
        market_code = self._get_market_code(code)
        url = 'https://push2.eastmoney.com/api/qt/stock/get'
        # 行情字段 + 五档盘口字段合并为一次请求
        params = {
            'secid': market_code,
            'fields': (
                'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18,f19,f20,'
                'f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f169,f170'
            ),
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'fltt': 2
        }

        def _do_request():
            resp = self.session.get(url, params=params, timeout=8)
            resp.raise_for_status()
            return resp.json()

        try:
            data = _safe_request(_do_request, timeout_seconds=10)
            if data is None:
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                data = _subprocess_fetch_json(full_url, headers={
                    'Referer': 'https://quote.eastmoney.com/',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                })
            if data is None:
                logger.warning("东方财富行情接口超时或不可达")
                return None

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富行情接口返回异常: {data}")
                return None

            d = data['data']
            import time as _time
            EastMoneyFreeSource._last_success_ts = _time.time()
            EastMoneyFreeSource._last_error = ''

            # 顺带缓存五档盘口，供 get_order_book 直接使用
            self._ob_cache[code] = (d, _time.time())

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
            EastMoneyFreeSource._last_error = str(e)[:80]
            logger.error(f"获取实时行情失败: {e}")
            return None

    def get_order_book(self, code):
        """获取五档盘口。
        若 get_realtime_quote 刚刚（15s内）已获取过该股数据，直接从缓存解析，
        不再发额外请求；否则调东方财富接口，失败降级 akshare。
        volume 单位为股，amount 单位为元。
        """
        import time as _time
        cached = self._ob_cache.get(code)
        if cached:
            raw_d, ts = cached
            if _time.time() - ts < 15:
                result = self._parse_order_book_from_raw(raw_d)
                if result and (result['bids'] or result['asks']):
                    return result
        result = self._get_order_book_eastmoney(code)
        if result and (result['bids'] or result['asks']):
            return result
        return self._get_order_book_akshare(code)

    def _parse_order_book_from_raw(self, d: dict):
        """从行情原始 dict（f1-f20）解析五档盘口，供缓存复用"""
        def _price(val):
            if val is None or val == '-':
                return 0.0
            return float(val) / 100 if isinstance(val, int) else self._safe_float(val)
        def _vol(val):
            if val is None or val == '-':
                return 0
            return int(float(val)) if val else 0
        bid_fields = [(1, 'f10', 'f9'), (2, 'f8', 'f7'), (3, 'f6', 'f5'),
                      (4, 'f4', 'f3'), (5, 'f2', 'f1')]
        ask_fields = [(1, 'f12', 'f11'), (2, 'f14', 'f13'), (3, 'f16', 'f15'),
                      (4, 'f18', 'f17'), (5, 'f20', 'f19')]
        bids, asks = [], []
        for level, pf, vf in bid_fields:
            price = _price(d.get(pf))
            vol = _vol(d.get(vf))
            if price > 0 and vol > 0:
                bids.append({'level': level, 'price': price, 'volume': vol * 100,
                             'amount': round(price * vol * 100, 2)})
        for level, pf, vf in ask_fields:
            price = _price(d.get(pf))
            vol = _vol(d.get(vf))
            if price > 0 and vol > 0:
                asks.append({'level': level, 'price': price, 'volume': vol * 100,
                             'amount': round(price * vol * 100, 2)})
        bid_amount = sum(b['amount'] for b in bids)
        ask_amount = sum(a['amount'] for a in asks)
        spread = round(asks[0]['price'] - bids[0]['price'], 4) if bids and asks else 0
        return {'bids': bids, 'asks': asks, 'spread': spread,
                'bid_amount': round(bid_amount, 2), 'ask_amount': round(ask_amount, 2),
                'source': 'eastmoney_cache'}

    def _get_order_book_eastmoney(self, code):
        """通过东方财富行情接口直接获取五档盘口
        字段映射（fltt=2，价格需 /100）：
          bid5: f2(价), f1(量)   bid4: f4, f3   bid3: f6, f5
          bid2: f8, f7           bid1: f10, f9
          ask1: f12, f11         ask2: f14, f13  ask3: f16, f15
          ask4: f18, f17         ask5: f20, f19
        """
        market_code = self._get_market_code(code)
        url = 'https://push2.eastmoney.com/api/qt/stock/get'
        params = {
            'secid': market_code,
            'fields': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18,f19,f20',
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'fltt': 2,
        }

        def _do_request():
            resp = self.session.get(url, params=params, timeout=8)
            resp.raise_for_status()
            return resp.json()

        data = None
        try:
            data = _safe_request(_do_request, timeout_seconds=10)
        except Exception as e:
            logger.error(f"获取五档盘口失败: {e}")

        if data is None:
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            logger.info("eventlet 请求失败，尝试 subprocess curl（五档盘口）")
            data = _subprocess_fetch_json(full_url, headers={
                'Referer': 'https://quote.eastmoney.com/',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            })

        if not data or data.get('rc') != 0 or not data.get('data'):
            return None

        try:
            d = data['data']

            def _price(val):
                if val is None or val == '-':
                    return 0.0
                return float(val) / 100 if isinstance(val, int) else self._safe_float(val)

            def _vol(val):
                if val is None or val == '-':
                    return 0
                return int(float(val)) if val else 0

            # bid: 买一=level1, 买五=level5（由近到远）
            bid_fields = [(1, 'f10', 'f9'), (2, 'f8', 'f7'), (3, 'f6', 'f5'),
                          (4, 'f4', 'f3'), (5, 'f2', 'f1')]
            # ask: 卖一=level1, 卖五=level5（由近到远）
            ask_fields = [(1, 'f12', 'f11'), (2, 'f14', 'f13'), (3, 'f16', 'f15'),
                          (4, 'f18', 'f17'), (5, 'f20', 'f19')]

            bids, asks = [], []
            for level, pf, vf in bid_fields:
                price = _price(d.get(pf))
                vol = _vol(d.get(vf))
                if price > 0 and vol > 0:
                    bids.append({
                        'level': level,
                        'price': price,
                        'volume': vol * 100,          # 手 → 股
                        'amount': round(price * vol * 100, 2),
                    })

            for level, pf, vf in ask_fields:
                price = _price(d.get(pf))
                vol = _vol(d.get(vf))
                if price > 0 and vol > 0:
                    asks.append({
                        'level': level,
                        'price': price,
                        'volume': vol * 100,
                        'amount': round(price * vol * 100, 2),
                    })

            bid_amount = round(sum(b['amount'] for b in bids), 2)
            ask_amount = round(sum(a['amount'] for a in asks), 2)
            spread = round(asks[0]['price'] - bids[0]['price'], 3) if bids and asks else 0

            return {
                'bids': bids,
                'asks': asks,
                'spread': spread,
                'bid_amount': bid_amount,
                'ask_amount': ask_amount,
                'source': 'eastmoney.qt.stock.get',
            }
        except Exception as e:
            logger.warning(f"东方财富五档盘口获取失败: {e}")
            return None

    def _build_order_book_from_akshare_values(self, values: dict, source: str):
        """将 akshare buy_N / buy_N_vol 字段解析为标准五档结构。volume 单位为股。"""
        bids, asks = [], []
        for level in range(1, 6):
            bid_price = self._safe_float(values.get(f'buy_{level}'))
            bid_volume = self._safe_float(values.get(f'buy_{level}_vol'))
            ask_price = self._safe_float(values.get(f'sell_{level}'))
            ask_volume = self._safe_float(values.get(f'sell_{level}_vol'))

            if bid_price and bid_volume:
                bids.append({
                    'level': level,
                    'price': bid_price,
                    'volume': int(bid_volume),
                    'amount': round(bid_price * bid_volume, 2),
                })
            if ask_price and ask_volume:
                asks.append({
                    'level': level,
                    'price': ask_price,
                    'volume': int(ask_volume),
                    'amount': round(ask_price * ask_volume, 2),
                })

        if not bids and not asks:
            return None

        bid_amount = round(sum(b['amount'] for b in bids), 2)
        ask_amount = round(sum(a['amount'] for a in asks), 2)
        spread = round(asks[0]['price'] - bids[0]['price'], 3) if bids and asks else 0
        return {
            'bids': bids,
            'asks': asks,
            'spread': spread,
            'bid_amount': bid_amount,
            'ask_amount': ask_amount,
            'source': source,
        }

    def _get_order_book_akshare(self, code):
        """akshare 五档盘口（降级备用，优先子进程以兼容 eventlet）"""
        values = _subprocess_fetch_akshare_bid_ask(code)
        if values:
            result = self._build_order_book_from_akshare_values(
                values, 'akshare.stock_bid_ask_em.subprocess')
            if result:
                return result

        try:
            import akshare as ak

            def _fetch():
                return ak.stock_bid_ask_em(symbol=code)

            df = _safe_request(_fetch, timeout_seconds=8)
            if df is None or df.empty:
                return self._empty_order_book()

            values = dict(zip(df['item'], df['value']))
            result = self._build_order_book_from_akshare_values(
                values, 'akshare.stock_bid_ask_em')
            return result or self._empty_order_book()
        except Exception:
            return self._empty_order_book()

    @staticmethod
    def _safe_float(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _empty_order_book(self):
        return {
            'bids': [],
            'asks': [],
            'spread': 0,
            'bid_amount': 0,
            'ask_amount': 0,
            'source': 'empty',
        }

    def get_minute_money_flow(self, code):
        """分钟级主力资金/散户累计净流入（东财 fflow/kline，数值为万元字符串）"""
        url = 'https://push2.eastmoney.com/api/qt/stock/fflow/kline/get'
        params = {
            'fields1': 'f1,f2,f3,f7',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65',
            'klt': '1',
            'fqt': '1',
            'secid': self._get_market_code(code),
            'beg': '0',
            'end': '20500101',
            'lmt': '256',
        }

        auth_session = self._make_auth_session()

        def _do_request():
            resp = auth_session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()

        data = _safe_request(_do_request, timeout_seconds=12)
        if data is None:
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            data = _subprocess_fetch_json(full_url, headers={
                'Referer': 'https://quote.eastmoney.com/',
                'User-Agent': self.session.headers.get('User-Agent', ''),
            }, cookies=EastMoneyFreeSource._em_cookie or None)

        if not data or not data.get('data'):
            return None

        klines = data['data'].get('klines', [])
        if not klines:
            return None

        zero = '0.000'
        time_data, zhuli_data, sanhu_data = [], [], []
        chaoda_data, dadan_data, zhongdan_data = [], [], []
        for kline in klines:
            parts = kline.split(',')
            raw_time = parts[0] if parts else ''
            time_data.append(raw_time.split(' ')[1] if ' ' in raw_time else raw_time)
            if len(parts) < 6:
                for bucket in (zhuli_data, sanhu_data, chaoda_data, dadan_data, zhongdan_data):
                    bucket.append(zero)
                continue
            try:
                zhuli = float(parts[1] or 0)
                xiaodan = float(parts[2] or 0)
                zhongdan = float(parts[3] or 0)
                dadan = float(parts[4] or 0)
                chaoda = float(parts[5] or 0)
                zhuli_data.append(f'{zhuli / 10000:.3f}')
                sanhu_data.append(f'{xiaodan / 10000:.3f}')
                chaoda_data.append(f'{chaoda / 10000:.3f}')
                dadan_data.append(f'{dadan / 10000:.3f}')
                zhongdan_data.append(f'{zhongdan / 10000:.3f}')
            except (ValueError, IndexError):
                for bucket in (zhuli_data, sanhu_data, chaoda_data, dadan_data, zhongdan_data):
                    bucket.append(zero)

        return {
            'time': time_data,
            'zhuli': zhuli_data,
            'sanhu': sanhu_data,
            'chaoda': chaoda_data,
            'dadan': dadan_data,
            'zhongdan': zhongdan_data,
        }

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

        def _do_request():
            resp = self.session.get(url, params=params, timeout=8)
            resp.raise_for_status()
            return resp.json()

        try:
            data = _safe_request(_do_request, timeout_seconds=10)
            if data is None:
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                logger.info("eventlet 请求失败，尝试 subprocess curl（当日逐笔）")
                data = _subprocess_fetch_json(full_url, headers={
                    'Referer': 'https://quote.eastmoney.com/',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                })
            if data is None:
                logger.warning("东方财富成交明细接口超时或不可达")
                return self._get_intraday_details_sina(code, dt)

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富成交明细接口返回异常: {data}")
                return self._get_intraday_details_sina(code, dt)

            details_raw = data['data'].get('details', [])
            new_pos = data['data'].get('pos', pos)
            details = []

            for item in details_raw:
                parts = item.split(',')
                if len(parts) < 5:
                    continue

                time_str = parts[0]
                price = float(parts[1])
                volume = int(parts[2])  # 手
                trade_count = int(parts[3])  # 笔数
                buy_sell_type = int(parts[4])  # 买卖方向: 1=主买(外盘) 2=主卖(内盘) 4=中性

                details.append({
                    'time': time_str,
                    'price': price,
                    'volume': volume,
                    'amount': round(price * volume * 100, 2),  # 手转股再算金额
                    'type': buy_sell_type,
                    'trade_count': trade_count,
                })

            return {'details': details, 'pos': new_pos}
        except Exception as e:
            logger.error(f"获取成交明细失败: {e}")
            return self._get_intraday_details_sina(code, dt)

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

        def _do_request():
            resp = self.session.get(url, params=params, timeout=8)
            resp.raise_for_status()
            return resp.json()

        data = None
        try:
            data = _safe_request(_do_request, timeout_seconds=10)
        except Exception as e:
            logger.error(f"获取实时分时数据失败: {e}")

        if data is None:
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            logger.info("eventlet 请求失败，尝试 subprocess curl（实时分时）")
            data = _subprocess_fetch_json(full_url, headers={
                'Referer': 'https://quote.eastmoney.com/',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            })

        if data and data.get('rc') == 0 and data.get('data'):
            trends_raw = data['data'].get('trends', [])
            result = []
            for item in trends_raw:
                parsed = self.parse_trend_item(item)
                if parsed:
                    result.append(parsed)
            if result:
                return result
            logger.warning(f"东方财富实时分时接口 trends 为空，降级到最近交易日 K 线 code={code}")
        else:
            logger.warning(f"东方财富实时分时接口异常，降级到最近交易日 K 线 code={code}")

        # 降级：往前找最近有数据的交易日（最多 7 天），用 1 分钟 K 线代替
        return self._get_latest_kline_timeshare(code, today)

    def _get_history_timeshare(self, code, dt):
        """获取历史日期分时数据（优先 AkShare/Tencent，东财 trends2 兜底）
        Args:
            code: 股票代码
            dt: 日期，格式 YYYY-MM-DD
        Returns:
            list of dict: [{'time': str, 'price': float, 'avg_price': float, 'volume': int(手)}]
        """
        minute_rows = self._get_minute_timeshare_akshare(code, dt)
        if minute_rows:
            return minute_rows

        today = datetime.now().strftime('%Y-%m-%d')
        # 根据自然日差距估算需要多少交易日的数据（多加几天余量）
        try:
            delta_days = (datetime.strptime(today, '%Y-%m-%d') - datetime.strptime(dt, '%Y-%m-%d')).days
        except ValueError:
            delta_days = 5
        ndays = min(max((delta_days // 5 + 1) * 5, 5), 30)

        market_code = self._get_market_code(code)
        url = 'https://push2his.eastmoney.com/api/qt/stock/trends2/get'
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
            'iscr': 0,
            'ndays': ndays,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
        }

        def _do_request():
            resp = self.session.get(url, params=params, timeout=8)
            resp.raise_for_status()
            return resp.json()

        try:
            data = _safe_request(_do_request, timeout_seconds=10)
            if data is None:
                # eventlet 下请求失败，用子进程 curl 兜底
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                logger.info(f"eventlet 请求失败，尝试 subprocess curl（历史分时 {dt}）")
                data = _subprocess_fetch_json(full_url, headers={
                    'Referer': 'https://quote.eastmoney.com/',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                })
            if data is None:
                logger.warning(f"东方财富 trends2 接口超时（历史分时 {dt}）")
                return self._get_minute_timeshare_akshare(code, dt)

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富 trends2 接口异常（历史分时 {dt}）: rc={data.get('rc')}")
                return self._get_minute_timeshare_akshare(code, dt)

            trends_raw = data['data'].get('trends', [])
            result = []
            for item in trends_raw:
                # 仅保留目标日期的行，格式: "YYYY-MM-DD HH:MM,..."
                if not item.startswith(dt):
                    continue
                parsed = self.parse_trend_item(item)
                if parsed:
                    result.append(parsed)

            if result:
                return result

            logger.warning(f"trends2 返回数据中未找到 {dt} 的分时记录（ndays={ndays}）")
            return self._get_minute_timeshare_akshare(code, dt)
        except Exception as e:
            logger.error(f"获取历史分时数据失败({dt}): {e}")
            return self._get_minute_timeshare_akshare(code, dt)

    def _get_latest_kline_timeshare(self, code, from_date_str, max_days=7):
        """往前找最近有 1 分钟 K 线数据的交易日（跳过周末），用于实时分时降级"""
        from datetime import timedelta
        start_dt = datetime.strptime(from_date_str, '%Y-%m-%d')
        for i in range(max_days):
            check_dt = start_dt - timedelta(days=i)
            if check_dt.weekday() >= 5:   # 跳过周末
                continue
            date_str = check_dt.strftime('%Y-%m-%d')
            result = self._get_history_timeshare(code, date_str)
            if result:
                if i > 0:
                    logger.info(f"分时数据回退到 {date_str}（请求日期 {from_date_str} 无数据）")
                return result
        logger.warning(f"最近 {max_days} 天均无分时数据 code={code}")
        return []

    def _get_minute_timeshare_akshare(self, code, dt=None):
        """历史分时兜底：优先直连新浪分钟线，AkShare 作为备用。"""
        rows = self._get_minute_timeshare_sina_kline(code, dt)
        if rows:
            return rows

        try:
            import subprocess
            import sys

            symbol = self._get_akshare_symbol(code)
            script = f"""
import akshare as ak
df = ak.stock_zh_a_minute(symbol={symbol!r}, period='1', adjust='')
if df is None or df.empty:
    print('[]')
else:
    df = df.copy()
    df['day'] = df['day'].astype(str)
    print(df[['day', 'close', 'volume']].to_json(orient='records', force_ascii=False))
"""
            proc = subprocess.run(
                [sys.executable, '-c', script],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.returncode != 0:
                logger.warning(f"AkShare 分钟线子进程失败 code={code}: {proc.stderr[:200]}")
                return []

            records = json.loads(proc.stdout.strip() or '[]')
            rows = self._build_timeshare_from_minute_records(records, dt)
            if not rows:
                logger.warning(f"AkShare 分钟线未找到目标日期 code={code} dt={dt}")
            return rows
        except Exception as e:
            logger.warning(f"AkShare 分钟线兜底失败 code={code} dt={dt}: {e}")
            return []

    def _get_minute_timeshare_sina_kline(self, code, dt=None):
        """直连新浪分钟线，避免 AkShare 冷启动导入开销。"""
        try:
            import subprocess
            from urllib.parse import urlencode

            symbol = self._get_akshare_symbol(code)
            params = urlencode({
                'symbol': symbol,
                'scale': '1',
                'ma': 'no',
                'datalen': '1970',
            })
            url = (
                'https://quotes.sina.cn/cn/api/jsonp_v2.php/=/'
                f'CN_MarketDataService.getKLineData?{params}'
            )
            proc = subprocess.run(
                ['curl', '-sS', '--max-time', '5', url],
                capture_output=True,
                text=True,
                timeout=7,
            )
            if proc.returncode != 0 or not proc.stdout:
                logger.warning(f"新浪分钟线请求失败 code={code}: {proc.stderr[:200]}")
                return []

            text = proc.stdout
            if '=(' not in text:
                logger.warning(f"新浪分钟线响应格式异常 code={code}")
                return []

            records = json.loads(text.split('=(', 1)[1].rsplit(');', 1)[0])
            rows = self._build_timeshare_from_minute_records(records, dt)
            if not rows:
                logger.warning(f"新浪分钟线未找到目标日期 code={code} dt={dt}")
            return rows
        except Exception as e:
            logger.warning(f"新浪分钟线兜底失败 code={code} dt={dt}: {e}")
            return []

    @staticmethod
    def _build_timeshare_from_minute_records(records, dt=None):
        """将 AkShare 分钟线记录转换为项目统一分时结构。"""
        try:
            rows = []
            total_value = 0.0
            total_volume = 0

            for row in records:
                day = str(row.get('day', ''))
                if dt and not day.startswith(dt):
                    continue

                time_str = day[-8:-3] if len(day) >= 16 else day[-5:]
                if not time_str or time_str < '09:30':
                    continue

                price = float(row.get('close') or 0)
                raw_volume = int(float(row.get('volume') or 0))
                if price <= 0:
                    continue

                # stock_zh_a_minute 的 volume 为股，项目内统一按“手”处理。
                volume = raw_volume // 100 if raw_volume >= 100 else raw_volume
                total_value += price * volume
                total_volume += volume
                avg_price = total_value / total_volume if total_volume else price

                rows.append({
                    'time': time_str,
                    'price': price,
                    'volume': volume,
                    'amount': price * volume * 100,
                    'avg_price': avg_price,
                })

            return rows
        except Exception as e:
            logger.warning(f"AkShare 分钟线记录解析失败 dt={dt}: {e}")
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

        def _do_request():
            resp = self.session.get(url, params=params, timeout=8)
            resp.raise_for_status()
            return resp.json()

        data = None
        try:
            data = _safe_request(_do_request, timeout_seconds=10)
        except Exception as e:
            logger.error(f"获取日K线失败: {e}")

        if data is None:
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            logger.info(f"eventlet 请求失败，尝试 subprocess curl（日K线 {dt}）")
            data = _subprocess_fetch_json(full_url, headers={
                'Referer': 'https://quote.eastmoney.com/',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            })

        if data is None:
            logger.warning("东方财富日K线接口不可达，回退腾讯日K")
            return self._get_tencent_daily_kline(code, dt)

        try:
            if data.get('rc') != 0 or not data.get('data'):
                return self._get_tencent_daily_kline(code, dt)

            klines = data['data'].get('klines', [])
            if not klines:
                # 请求日为周末/停牌等，东财返回空，回退腾讯并取≤dt最近交易日
                return self._get_tencent_daily_kline(code, dt)

            # 日K线格式: 日期,开,收,高,低,成交量(手),成交额,振幅,涨跌幅,涨跌额,换手率
            parts = klines[0].split(',')
            if len(parts) < 9:
                return None

            close = float(parts[2])
            change_percent = float(parts[8])
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
            return self._get_tencent_daily_kline(code, dt)

    def _get_tencent_daily_kline(self, code, dt):
        """腾讯日K兜底：东财不可达或请求日无数据（周末/停牌）时使用。
        取 <= dt 的最近交易日，昨收=上一交易日收盘价，避免一字涨停被画成 0%。
        """
        try:
            datetime.strptime(dt, '%Y-%m-%d')
        except (ValueError, TypeError):
            return None

        symbol = self._get_akshare_symbol(code)
        try:
            start_dt = (datetime.strptime(dt, '%Y-%m-%d') - timedelta(days=400)).strftime('%Y-%m-%d')
        except ValueError:
            return None

        from urllib.parse import urlencode
        # 不复权（不带 qfq），保证昨收/涨跌幅与交易所口径一致
        params = {'param': f'{symbol},day,{start_dt},{dt},640,'}
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?{urlencode(params)}"

        data = _subprocess_fetch_json(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://gu.qq.com/',
        })
        if not data or data.get('code') != 0:
            return None

        try:
            stock_data = data.get('data', {}).get(symbol, {})
            rows = stock_data.get('day') or stock_data.get('qfqday') or []
            rows = [r for r in rows if r and len(r) >= 5 and r[0] <= dt]
            if len(rows) < 2:
                return None

            row = rows[-1]
            prev_close = float(rows[-2][2])
            close = float(row[2])
            if prev_close <= 0:
                return None

            change_percent = round((close - prev_close) / prev_close * 100, 2)
            return {
                'open': float(row[1]),
                'close': close,
                'high': float(row[3]),
                'low': float(row[4]),
                'volume': int(float(row[5])) if len(row) > 5 and row[5] else 0,
                'turnover': 0.0,
                'preclose': prev_close,
                'change_percent': change_percent,
            }
        except (ValueError, IndexError, KeyError, TypeError) as e:
            logger.warning(f"腾讯日K解析失败 code={code} dt={dt}: {e}")
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

        # 历史逐笔需要登录态，优先使用带 Cookie 的 session
        auth_session = self._make_auth_session()
        has_cookie = bool(EastMoneyFreeSource._em_cookie)
        if not has_cookie:
            logger.info("东方财富历史逐笔：未设置 Cookie，匿名请求可能返回空（建议在前端设置登录 Cookie）")

        def _do_request():
            resp = auth_session.get(url, params=params, timeout=8)
            resp.raise_for_status()
            return resp.json()

        try:
            data = _safe_request(_do_request, timeout_seconds=10)
            if data is None:
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                cookie_str = EastMoneyFreeSource._em_cookie or None
                logger.info(f"eventlet 请求失败，尝试 subprocess curl（历史逐笔 {dt}）")
                data = _subprocess_fetch_json(full_url, headers={
                    'Referer': 'https://quote.eastmoney.com/',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                }, cookies=cookie_str)
            if data is None:
                logger.warning("东方财富历史成交明细接口超时或不可达")
                return self._get_intraday_details_sina(code, dt)

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富历史成交明细接口返回异常 (has_cookie={has_cookie}): rc={data.get('rc')} msg={data.get('message','')}")
                return self._get_intraday_details_sina(code, dt)

            details_raw = data['data'].get('details', [])
            if not details_raw and not has_cookie:
                logger.warning("历史逐笔返回空列表，请在前端「设置 Cookie」后重试")

            details = []

            for item in details_raw:
                parts = item.split(',')
                if len(parts) < 5:
                    continue

                time_str = parts[0]
                price = float(parts[1])
                volume = int(parts[2])
                trade_count = int(parts[3])  # 笔数
                buy_sell_type = int(parts[4])  # 买卖方向: 1=主买(外盘) 2=主卖(内盘) 4=中性

                details.append({
                    'time': time_str,
                    'price': price,
                    'volume': volume,
                    'amount': round(price * volume * 100, 2),
                    'type': buy_sell_type,
                    'trade_count': trade_count,
                })

            return {'details': details, 'pos': 0}
        except Exception as e:
            logger.error(f"获取历史成交明细失败({dt}): {e}")
            return self._get_intraday_details_sina(code, dt)

    def _get_intraday_details_akshare(self, code, dt=None):
        """当日逐笔兜底：直接返回空"""
        return self._get_intraday_details_sina(code, dt)

    def _get_intraday_details_sina(self, code, dt=None):
        """历史逐笔兜底：东方财富历史接口失败时返回空"""
        logger.warning(f"逐笔成交获取失败，返回空列表 code={code} dt={dt}")
        return {'details': [], 'pos': 0}

    def infer_direction(self, buy_sell_type):
        """将东方财富的成交类型(f55)转换为买卖方向
        1 = 外盘（成交在卖方挂单价，买方主动吃单）→ '主买'
        2 = 内盘（成交在买方挂单价，卖方主动砸单）→ '主卖'
        4 = 中性盘（集合竞价等，成交价在买卖之间）→ '中性'
        """
        if buy_sell_type == 1:
            return '主买'
        elif buy_sell_type == 2:
            return '主卖'
        else:
            return '中性'
