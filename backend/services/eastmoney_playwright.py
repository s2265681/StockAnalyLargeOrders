"""
东方财富 Playwright 数据源
使用真实 Chrome 浏览器 + EventSource 劫持，绕过 push2 API 的 TLS 指纹检测

架构：
  - 专用后台线程持有持久 asyncio 事件循环
  - EastMoneyPlaywrightSource：按需加载页面，带内存缓存（适合历史/模拟）
  - LiveFeedManager：持久化页面，监听所有 SSE 帧，有更新时调用回调（适合实时开盘）
"""
import asyncio
import json
import logging
import time
import threading
from datetime import datetime
from typing import Optional, Callable

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_CACHE_TTL_TRADING = 180   # 交易时间内缓存 3 分钟（分时/逐笔是累积数据，不需要秒级刷新）
_CACHE_TTL_CLOSED  = 3600  # 非交易时间缓存 1 小时

# ── 一次性加载脚本：只捕获第一帧（用于按需请求） ──
_INTERCEPT_SCRIPT = r"""
window.__sseCapture__ = {};
const _OrigES = window.EventSource;
window.EventSource = function(url, init) {
    if (url.includes('details/sse')) {
        url = url.replace(/pos=-\d+/, 'pos=-1000000');
    }
    const es = new _OrigES(url, init);
    const key = url.includes('trends2') ? 'trends'
              : url.includes('details') ? 'details'
              : null;
    if (key) {
        es.addEventListener('message', function(e) {
            if (!window.__sseCapture__[key]) {
                window.__sseCapture__[key] = e.data;
            }
        });
    }
    return es;
};
window.EventSource.prototype = _OrigES.prototype;
window.EventSource.CONNECTING = _OrigES.CONNECTING;
window.EventSource.OPEN = _OrigES.OPEN;
window.EventSource.CLOSED = _OrigES.CLOSED;
"""

# ── 持久监听脚本：捕获每一帧并维护版本号（用于 LiveFeedManager） ──
_INTERCEPT_SCRIPT_LIVE = r"""
window.__sseCapture__ = { trends: null, details: null, _v_trends: 0, _v_details: 0 };
const _OrigES = window.EventSource;
window.EventSource = function(url, init) {
    if (url.includes('details/sse')) {
        url = url.replace(/pos=-\d+/, 'pos=-1000000');
    }
    const es = new _OrigES(url, init);
    const key = url.includes('trends2') ? 'trends'
              : url.includes('details') ? 'details'
              : null;
    if (key) {
        es.addEventListener('message', function(e) {
            window.__sseCapture__[key] = e.data;
            window.__sseCapture__['_v_' + key]++;
        });
    }
    return es;
};
window.EventSource.prototype = _OrigES.prototype;
window.EventSource.CONNECTING = _OrigES.CONNECTING;
window.EventSource.OPEN = _OrigES.OPEN;
window.EventSource.CLOSED = _OrigES.CLOSED;
"""


# ───────── 全局专用 Playwright 线程 ─────────

_pw_loop: Optional[asyncio.AbstractEventLoop] = None
_pw_thread: Optional[threading.Thread] = None
_pw_browser = None
_pw_start_lock = threading.Lock()
_pw_proxy: Optional[str] = None


def _loop_worker(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _pw_loop, _pw_thread
    with _pw_start_lock:
        if _pw_loop is None or not _pw_loop.is_running():
            _pw_loop = asyncio.new_event_loop()
            _pw_thread = threading.Thread(
                target=_loop_worker, args=(_pw_loop,), daemon=True
            )
            _pw_thread.start()
    return _pw_loop


def _submit(coro, timeout: float = 45) -> object:
    """提交协程到专用循环，阻塞等待结果"""
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def _submit_nowait(coro) -> None:
    """提交协程到专用循环，不等待结果（fire and forget）"""
    loop = _ensure_loop()
    asyncio.run_coroutine_threadsafe(coro, loop)


async def _get_browser_async():
    global _pw_browser
    if _pw_browser is not None and _pw_browser.is_connected():
        return _pw_browser
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    kwargs = dict(
        headless=True,
        args=['--headless=new', '--disable-blink-features=AutomationControlled', '--no-sandbox']
    )
    if _pw_proxy:
        kwargs['proxy'] = {'server': _pw_proxy}
    _pw_browser = await pw.chromium.launch(**kwargs)
    logger.info(f"Playwright Chromium 已启动 (proxy={_pw_proxy})")
    return _pw_browser


async def _fetch_sse_async(code: str, market: int) -> dict:
    """按需加载页面获取一次性 SSE 数据（3 分钟 TTL 缓存，加载完即关闭页面）"""
    market_prefix = 'sz' if market == 0 else 'sh'
    url = f"https://quote.eastmoney.com/{market_prefix}{code}.html"

    browser = await _get_browser_async()
    ctx = await browser.new_context(user_agent=UA)
    await ctx.add_init_script(_INTERCEPT_SCRIPT)
    page = await ctx.new_page()

    try:
        await page.goto(url, wait_until='load', timeout=25000)
        for _ in range(15):
            await asyncio.sleep(1)
            cap = await page.evaluate("() => Object.keys(window.__sseCapture__ || {})")
            if 'trends' in cap and 'details' in cap:
                break

        result = {}
        for key in ['trends', 'details']:
            raw = await page.evaluate(f"() => window.__sseCapture__['{key}']")
            if raw:
                try:
                    result[key] = json.loads(raw)
                except Exception as e:
                    logger.warning(f"SSE {key} 解析失败: {e}")
        return result
    finally:
        await ctx.close()


# ───────── 按需缓存数据源 ─────────

class EastMoneyPlaywrightSource:
    """一次页面加载同时返回分时 + 逐笔数据，带内存缓存（适合历史查询/模拟回放）"""

    _cache: dict = {}

    @staticmethod
    def set_proxy(proxy: Optional[str]):
        global _pw_proxy
        _pw_proxy = proxy

    @staticmethod
    def _is_trading_time() -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = now.hour * 60 + now.minute
        return (9 * 60 + 15) <= t <= (15 * 60 + 5)

    @classmethod
    def _cache_ttl(cls) -> int:
        return _CACHE_TTL_TRADING if cls._is_trading_time() else _CACHE_TTL_CLOSED

    @classmethod
    def _get_cached(cls, code: str) -> Optional[dict]:
        entry = cls._cache.get(code)
        if entry and time.time() - entry['ts'] < cls._cache_ttl():
            return entry['data']
        return None

    @classmethod
    def _set_cache(cls, code: str, data: dict):
        cls._cache[code] = {'ts': time.time(), 'data': data}

    @staticmethod
    def _get_market(code: str) -> int:
        return 1 if code.startswith(('6', '5', '9')) else 0

    # 并发去重：同一股票只允许一次 Playwright 加载并行
    _fetch_events: dict = {}        # code -> threading.Event
    _fetch_events_lock = threading.Lock()

    def get_all_data(self, code: str) -> dict:
        # 快路径：缓存命中，直接返回
        cached = self._get_cached(code)
        if cached is not None:
            logger.debug(f"Playwright 缓存命中: {code}")
            return cached

        # 去重：如果已有线程正在加载同一股票，等待其完成后读缓存
        with self._fetch_events_lock:
            event = self._fetch_events.get(code)
            if event is not None:
                # 等待方
                should_load = False
            else:
                event = threading.Event()
                self._fetch_events[code] = event
                should_load = True

        if not should_load:
            logger.debug(f"Playwright 等待并发加载完成: {code}")
            event.wait(timeout=50)
            return self._get_cached(code) or {}

        # 加载方：真正执行 Playwright 页面加载
        try:
            market = self._get_market(code)
            data = _submit(_fetch_sse_async(code, market), timeout=45)
            self._set_cache(code, data)
            return data
        except Exception as e:
            logger.error(f"Playwright 页面加载失败: {e}")
            return {}
        finally:
            # 通知等待方（无论成功/失败都要释放）
            with self._fetch_events_lock:
                self._fetch_events.pop(code, None)
            event.set()

    def get_timeshare(self, code: str, dt: str = None) -> list:
        data = self.get_all_data(code)
        trends_resp = data.get('trends', {})
        if not trends_resp or trends_resp.get('rc') != 0 or not trends_resp.get('data'):
            return []

        raw = trends_resp['data'].get('trends', [])
        if dt:
            raw = [t for t in raw if t.startswith(dt)]

        result = []
        for item in raw:
            parts = item.split(',')
            if len(parts) < 7:
                continue
            try:
                result.append({
                    'time': parts[0][-5:],
                    'price': float(parts[1]),
                    'avg_price': float(parts[7]) if len(parts) > 7 else float(parts[1]),
                    'volume': int(parts[5]),
                    'amount': float(parts[6]),
                })
            except (ValueError, IndexError):
                continue
        return result

    def get_tick_details(self, code: str, dt: str = None) -> dict:
        data = self.get_all_data(code)
        details_resp = data.get('details', {})
        if not details_resp or details_resp.get('rc') != 0 or not details_resp.get('data'):
            return {'details': [], 'pos': 0}

        raw = details_resp['data'].get('details', [])
        details = []
        for item in raw:
            parts = item.split(',')
            if len(parts) < 4:
                continue
            try:
                price = float(parts[1])
                volume = int(parts[2])
                details.append({
                    'time': parts[0],
                    'price': price,
                    'volume': volume,
                    'amount': round(price * volume * 100, 2),
                    'type': int(parts[3]),
                })
            except (ValueError, IndexError):
                continue
        return {'details': details, 'pos': 0}


# ───────── 实时推流管理器 ─────────

class LiveFeedManager:
    """
    持久化 Playwright 页面，实时订阅东财 SSE 数据流。
    页面保持打开，每秒轮询 JS 内版本号，有新帧时调用 callback(code, raw_data)。

    用法：
        feed = LiveFeedManager()
        feed.subscribe('002081', my_callback)   # 非阻塞，fire-and-forget
        feed.unsubscribe('002081')
        feed.stop_all()
    """

    def __init__(self):
        # code -> {ctx, page, callback, v_trends, v_details, active}
        self._feeds: dict = {}

    def subscribe(self, code: str, callback: Callable):
        """订阅股票实时数据（非阻塞）"""
        if code in self._feeds:
            return
        market = 1 if code.startswith(('6', '5', '9')) else 0
        _submit_nowait(self._open_feed(code, market, callback))

    def unsubscribe(self, code: str):
        """取消订阅（非阻塞）"""
        if code in self._feeds:
            _submit_nowait(self._close_feed(code))

    def stop_all(self):
        for code in list(self._feeds.keys()):
            self.unsubscribe(code)

    @property
    def active_codes(self):
        return set(self._feeds.keys())

    async def _open_feed(self, code: str, market: int, callback: Callable):
        if code in self._feeds:
            return
        try:
            market_prefix = 'sz' if market == 0 else 'sh'
            url = f"https://quote.eastmoney.com/{market_prefix}{code}.html"

            browser = await _get_browser_async()
            ctx = await browser.new_context(user_agent=UA)
            await ctx.add_init_script(_INTERCEPT_SCRIPT_LIVE)
            page = await ctx.new_page()

            await page.goto(url, wait_until='load', timeout=25000)

            # 等第一帧 SSE 到来（最多 15 秒）
            for _ in range(15):
                await asyncio.sleep(1)
                ready = await page.evaluate(
                    "() => window.__sseCapture__._v_trends > 0 && window.__sseCapture__._v_details > 0"
                )
                if ready:
                    break

            feed = {
                'ctx': ctx, 'page': page, 'callback': callback,
                'v_trends': 0, 'v_details': 0, 'active': True,
            }
            self._feeds[code] = feed

            # 推送初始帧
            await self._extract_and_notify(code)

            # 启动轮询协程
            asyncio.ensure_future(self._poll_loop(code))
            logger.info(f"LiveFeed 已启动: {code}")

        except Exception as e:
            logger.error(f"LiveFeed 启动失败 {code}: {e}")
            self._feeds.pop(code, None)

    async def _poll_loop(self, code: str):
        """每秒检查 SSE 版本号，有变化时提取数据并通知"""
        while True:
            await asyncio.sleep(1)
            feed = self._feeds.get(code)
            if not feed or not feed.get('active'):
                break
            try:
                v = await feed['page'].evaluate(
                    "() => ({vt: window.__sseCapture__._v_trends, vd: window.__sseCapture__._v_details})"
                )
                if v['vt'] != feed['v_trends'] or v['vd'] != feed['v_details']:
                    feed['v_trends'] = v['vt']
                    feed['v_details'] = v['vd']
                    await self._extract_and_notify(code)
            except Exception as e:
                logger.warning(f"LiveFeed poll 异常 {code}: {e}")
                break
        logger.info(f"LiveFeed poll 循环结束: {code}")
        self._feeds.pop(code, None)

    async def _extract_and_notify(self, code: str):
        """从页面 JS 内存读取最新 SSE 数据，更新缓存并在线程池中调用回调（避免阻塞 asyncio 循环）"""
        feed = self._feeds.get(code)
        if not feed:
            return
        page = feed['page']
        result = {}
        for key in ['trends', 'details']:
            raw = await page.evaluate(f"() => window.__sseCapture__['{key}']")
            if raw:
                try:
                    result[key] = json.loads(raw)
                except Exception:
                    pass
        if result:
            # 先更新缓存，让后续 adapter.get_l2_dashboard 能直接命中
            EastMoneyPlaywrightSource._set_cache(code, result)
            # 把可能含有阻塞 HTTP 请求的回调放到线程池，不阻塞 Playwright asyncio 循环
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(None, feed['callback'], code, result)
            except Exception as e:
                logger.error(f"LiveFeed 回调异常 {code}: {e}")

    async def _close_feed(self, code: str):
        feed = self._feeds.pop(code, None)
        if feed:
            feed['active'] = False
            try:
                await feed['ctx'].close()
            except Exception:
                pass
            logger.info(f"LiveFeed 已停止: {code}")

import asyncio
import json
import logging
import time
import threading
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_CACHE_TTL_TRADING = 180   # 交易时间内缓存 3 分钟（分时/逐笔是累积数据，不需要秒级刷新）
_CACHE_TTL_CLOSED  = 3600  # 非交易时间缓存 1 小时

_INTERCEPT_SCRIPT = r"""
window.__sseCapture__ = {};
const _OrigES = window.EventSource;
window.EventSource = function(url, init) {
    if (url.includes('details/sse')) {
        url = url.replace(/pos=-\d+/, 'pos=-1000000');
    }
    const es = new _OrigES(url, init);
    const key = url.includes('trends2') ? 'trends'
              : url.includes('details') ? 'details'
              : null;
    if (key) {
        es.addEventListener('message', function(e) {
            if (!window.__sseCapture__[key]) {
                window.__sseCapture__[key] = e.data;
            }
        });
    }
    return es;
};
window.EventSource.prototype = _OrigES.prototype;
window.EventSource.CONNECTING = _OrigES.CONNECTING;
window.EventSource.OPEN = _OrigES.OPEN;
window.EventSource.CLOSED = _OrigES.CLOSED;
"""


# ───────── 全局专用 Playwright 线程 ─────────

_pw_loop: Optional[asyncio.AbstractEventLoop] = None
_pw_thread: Optional[threading.Thread] = None
_pw_browser = None
_pw_start_lock = threading.Lock()
_pw_proxy: Optional[str] = None


def _loop_worker(loop: asyncio.AbstractEventLoop):
    """后台线程：持续运行 asyncio 事件循环"""
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """确保后台 asyncio 循环已启动"""
    global _pw_loop, _pw_thread
    with _pw_start_lock:
        if _pw_loop is None or not _pw_loop.is_running():
            _pw_loop = asyncio.new_event_loop()
            _pw_thread = threading.Thread(
                target=_loop_worker, args=(_pw_loop,), daemon=True
            )
            _pw_thread.start()
    return _pw_loop


def _submit(coro, timeout: float = 45) -> object:
    """把协程提交到专用 asyncio 循环，阻塞等待结果"""
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


async def _get_browser_async():
    """在专用循环内懒加载 Playwright 浏览器"""
    global _pw_browser
    if _pw_browser is not None and _pw_browser.is_connected():
        return _pw_browser
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    kwargs = dict(
        headless=True,
        args=['--headless=new', '--disable-blink-features=AutomationControlled', '--no-sandbox']
    )
    if _pw_proxy:
        kwargs['proxy'] = {'server': _pw_proxy}
    _pw_browser = await pw.chromium.launch(**kwargs)
    logger.info(f"Playwright Chromium 已启动 (proxy={_pw_proxy})")
    return _pw_browser


async def _fetch_sse_async(code: str, market: int) -> dict:
    """在专用循环内加载东财页面，劫持 SSE 数据。
    - 每次独立 BrowserContext，避免跨请求状态污染
    - finally 关闭 ctx 立即释放内存（约 50MB/次）
    - 实际耗时 ~4-8 秒，由 TTL 缓存控制频率（交易时间 3 分钟/次）
    """
    market_prefix = 'sz' if market == 0 else 'sh'
    url = f"https://quote.eastmoney.com/{market_prefix}{code}.html"

    browser = await _get_browser_async()
    ctx = await browser.new_context(user_agent=UA)
    await ctx.add_init_script(_INTERCEPT_SCRIPT)
    page = await ctx.new_page()

    try:
        await page.goto(url, wait_until='load', timeout=25000)
        for _ in range(15):
            await asyncio.sleep(1)
            cap = await page.evaluate("() => Object.keys(window.__sseCapture__ || {})")
            if 'trends' in cap and 'details' in cap:
                break

        result = {}
        for key in ['trends', 'details']:
            raw = await page.evaluate(f"() => window.__sseCapture__['{key}']")
            if raw:
                try:
                    result[key] = json.loads(raw)
                except Exception as e:
                    logger.warning(f"SSE {key} 解析失败: {e}")
        return result
    finally:
        await ctx.close()


# ───────── 公开服务类 ─────────

class EastMoneyPlaywrightSource:
    """一次页面加载同时返回分时 + 逐笔数据，带内存缓存"""

    _cache: dict = {}

    @staticmethod
    def set_proxy(proxy: Optional[str]):
        global _pw_proxy
        _pw_proxy = proxy

    @staticmethod
    def _is_trading_time() -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = now.hour * 60 + now.minute
        return (9 * 60 + 15) <= t <= (15 * 60 + 5)

    @classmethod
    def _cache_ttl(cls) -> int:
        return _CACHE_TTL_TRADING if cls._is_trading_time() else _CACHE_TTL_CLOSED

    @classmethod
    def _get_cached(cls, code: str) -> Optional[dict]:
        entry = cls._cache.get(code)
        if entry and time.time() - entry['ts'] < cls._cache_ttl():
            return entry['data']
        return None

    @classmethod
    def _set_cache(cls, code: str, data: dict):
        cls._cache[code] = {'ts': time.time(), 'data': data}

    @staticmethod
    def _get_market(code: str) -> int:
        return 1 if code.startswith(('6', '5', '9')) else 0

    def get_all_data(self, code: str) -> dict:
        """一次加载页面，同时返回分时 + 逐笔（带缓存）"""
        cached = self._get_cached(code)
        if cached is not None:
            logger.debug(f"Playwright 缓存命中: {code}")
            return cached

        market = self._get_market(code)
        try:
            data = _submit(_fetch_sse_async(code, market), timeout=45)
            self._set_cache(code, data)
            return data
        except Exception as e:
            logger.error(f"Playwright 页面加载失败: {e}")
            return {}

    def get_timeshare(self, code: str, dt: str = None) -> list:
        data = self.get_all_data(code)
        trends_resp = data.get('trends', {})
        if not trends_resp or trends_resp.get('rc') != 0 or not trends_resp.get('data'):
            return []

        raw = trends_resp['data'].get('trends', [])
        if dt:
            raw = [t for t in raw if t.startswith(dt)]

        result = []
        for item in raw:
            parts = item.split(',')
            if len(parts) < 7:
                continue
            try:
                result.append({
                    'time': parts[0][-5:],
                    'price': float(parts[1]),
                    'avg_price': float(parts[7]) if len(parts) > 7 else float(parts[1]),
                    'volume': int(parts[5]),
                    'amount': float(parts[6]),
                })
            except (ValueError, IndexError):
                continue
        return result

    def get_tick_details(self, code: str, dt: str = None) -> dict:
        data = self.get_all_data(code)
        details_resp = data.get('details', {})
        if not details_resp or details_resp.get('rc') != 0 or not details_resp.get('data'):
            return {'details': [], 'pos': 0}

        raw = details_resp['data'].get('details', [])
        details = []
        for item in raw:
            parts = item.split(',')
            if len(parts) < 4:
                continue
            try:
                price = float(parts[1])
                volume = int(parts[2])
                details.append({
                    'time': parts[0],
                    'price': price,
                    'volume': volume,
                    'amount': round(price * volume * 100, 2),
                    'type': int(parts[3]),
                })
            except (ValueError, IndexError):
                continue
        return {'details': details, 'pos': 0}
