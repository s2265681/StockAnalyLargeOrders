"""
竞价筛选条件服务
从全市场竞价金额排行中筛选沪深A股主板票（排除ST）

stockapi 扫全市场，每种排序返回前50条；三种排序（委托额/成交额/开盘额）取并集，
可覆盖全市场竞价金额约前55-60支；过滤主板后通常得到40+支主板候选池。
"""
import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

_STOCKAPI_TOKEN = 'c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e'
_STOCKAPI_BASE = 'http://user.stockapi.com.cn/v1/base/jjqcUser'
_STOCKAPI_TYPES = [1, 2, 3]  # 1=委托额 2=成交额 3=开盘额

# 主板代码前缀（沪深A股主板，排除科创/创业/北交）
_MAIN_BOARD_PREFIXES = ('000', '001', '002', '003', '600', '601', '603', '605', '606')


def _fetch_stockapi_raw(trade_date: str, period: int = 0, api_type: int = 1) -> list[dict]:
    url = (
        f"{_STOCKAPI_BASE}?tradeDate={trade_date}"
        f"&period={period}&type={api_type}&token={_STOCKAPI_TOKEN}"
    )
    cmd = ['curl', '-s', '--max-time', '15', '--insecure',
           '-H', 'Referer: http://user.stockapi.com.cn/bidding',
           '-H', 'User-Agent: Mozilla/5.0', url]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20)
        d = json.loads(r.stdout)
        if d.get('code') == 20000:
            return d.get('data') or []
    except Exception as e:
        logger.warning(f"stockapi type={api_type} 失败: {e}")
    return []


def _is_main_board(code: str) -> bool:
    return code.startswith(_MAIN_BOARD_PREFIXES)


def _board_label(code: str) -> str:
    if code.startswith(('688', '689')):
        return '科创'
    if code.startswith(('300', '301', '302')):
        return '创业'
    if code.startswith(('8', '4')):
        return '北交'
    return '主板'


def get_main_board_top_auction(
    trade_date: str,
    period: int = 0,
    top_n: int = 60,
) -> list[dict]:
    """
    从全市场竞价金额前 N 支中，筛选沪深A股主板票（排除ST），按委托额降序返回。

    参数：
        trade_date  — YYYY-MM-DD 或 YYYYMMDD
        period      — 0=早盘竞价 1=尾盘
        top_n       — 目标主板股票数量（实际数量受数据源限制，通常40-45支）

    返回列表字段：
        code, name, board, auction_order_amt(万元), auction_trade_amt(万元),
        auction_change_pct(%)
    """
    if len(trade_date) == 8:
        trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

    # 并发拉三种排序，合并去重
    raw_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(_fetch_stockapi_raw, trade_date, period, t): t
            for t in _STOCKAPI_TYPES
        }
        for future in as_completed(futures):
            for r in future.result():
                code = str(r.get('code', '')).zfill(6)
                if not code:
                    continue
                cur = raw_map.get(code, {})
                raw_map[code] = {
                    'code': code,
                    'name': r.get('name') or cur.get('name', ''),
                    'auction_order_amt': max(
                        float(r.get('qcwtje') or 0) / 10000,
                        cur.get('auction_order_amt', 0),
                    ),
                    'auction_trade_amt': max(
                        float(r.get('qccje') or 0) / 10000,
                        cur.get('auction_trade_amt', 0),
                    ),
                    'auction_change_pct': float(r.get('qczf') or 0),
                }

    if not raw_map:
        return []

    # 按委托额排序后过滤：主板 + 非ST
    all_sorted = sorted(raw_map.values(), key=lambda x: x['auction_order_amt'], reverse=True)
    result = []
    for s in all_sorted:
        code = s['code']
        name = s['name']
        if not _is_main_board(code):
            continue
        if 'ST' in name.upper():
            continue
        s['board'] = _board_label(code)
        result.append(s)
        if len(result) >= top_n:
            break

    return result


def filter_by_auction_change(
    stocks: list[dict], min_pct: float = 2.0, max_pct: float = 7.0
) -> list[dict]:
    """按竞价涨幅区间过滤"""
    return [s for s in stocks if min_pct <= s.get('auction_change_pct', 0) <= max_pct]


def _curl(url: str, ref: str = 'https://gu.qq.com/') -> str:
    try:
        r = subprocess.run(
            ['curl', '-s', '--max-time', '12',
             '-H', f'Referer: {ref}', '-H', 'User-Agent: Mozilla/5.0', url],
            capture_output=True, timeout=15,
        )
        return r.stdout.decode('utf-8', errors='replace')
    except Exception:
        return ''


def _get_mktcap_batch(codes: list[str]) -> dict[str, float]:
    """腾讯API批量查流通市值(亿), 返回 {code: cap}"""
    if not codes:
        return {}
    secids = ','.join([('sz' if c.startswith(('0', '3')) else 'sh') + c for c in codes])
    text = _curl(f'https://qt.gtimg.cn/q={secids}')
    result: dict[str, float] = {}
    for line in text.split('\n'):
        if '"' not in line or '~' not in line:
            continue
        try:
            fields = line.split('"')[1].split('~')
            if len(fields) >= 45:
                code6 = fields[2]
                result[code6] = float(fields[44]) if fields[44] else 0.0
        except Exception:
            pass
    return result


def _count_limit_up_and_prev_vol(
    code: str, target_date: str
) -> tuple[int, float | None, float | None, float | None, float | None, float | None, float | None]:
    """
    返回 (涨停次数, prev_vol(手), close_price, prev_close, prev_prev_close, next_close, open_price)
    target_date 格式 YYYY-MM-DD
    当 target_date 不在 K 线（竞价期间）时 close_price/open_price=None，prev/prev_prev 取最后两根
    """
    prefix = 'sz' if code.startswith(('0', '3')) else 'sh'
    url = (f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
           f'?_var=kline_dayqfq&param={prefix}{code},day,,,250,qfq')
    text = _curl(url)
    cnt = 0
    prev_vol: float | None = None
    close_price: float | None = None
    open_price: float | None = None
    prev_close: float | None = None
    prev_prev_close: float | None = None
    next_close: float | None = None
    try:
        idx = text.index('{')
        d = json.loads(text[idx:])
        klines = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        prev_c: float | None = None
        for i, k in enumerate(klines):
            try:
                c = float(k[2])
                if prev_c and prev_c > 0 and (c - prev_c) / prev_c * 100 >= 9.8:
                    cnt += 1
                if str(k[0]) == target_date:
                    close_price = c
                    open_price = float(k[1])
                    if i > 0:
                        prev_vol = float(klines[i - 1][5])
                        prev_close = float(klines[i - 1][2])
                    if i > 1:
                        prev_prev_close = float(klines[i - 2][2])
                    if i + 1 < len(klines):
                        next_close = float(klines[i + 1][2])
                prev_c = c
            except Exception:
                pass
        # target_date 不在 K 线（竞价期间），用最后两根作 prev/prev_prev
        if close_price is None and klines:
            n = len(klines)
            try:
                prev_vol = float(klines[-1][5])
                prev_close = float(klines[-1][2])
            except Exception:
                pass
            if n >= 2:
                try:
                    prev_prev_close = float(klines[-2][2])
                except Exception:
                    pass
    except Exception:
        pass
    return cnt, prev_vol, close_price, prev_close, prev_prev_close, next_close, open_price


def run_advanced_screen(trade_date: str, period: int = 0) -> list[dict]:
    """
    完整高级筛选流程，返回通过所有条件的股票列表，含 vol_ratio 字段。

    条件：全市场主板非ST → 竞价涨幅2-7% → 流通市值30-300亿 → 近1年涨停>2次
    vol_ratio = 竞价委托手 / 前一日成交量(手)
    """
    from services.auction_grab_service import merge_stock_meta

    # 标准化日期格式
    if len(trade_date) == 8:
        td_dash = f'{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}'
    else:
        td_dash = trade_date

    # 1. 全市场主板非ST
    step1 = get_main_board_top_auction(trade_date, period=period, top_n=60)
    if not step1:
        return []

    # 2. 竞价涨幅 2-7%
    step2 = filter_by_auction_change(step1, 2.0, 7.0)
    if not step2:
        return []

    # 3. 流通市值 30-300亿（批量查）
    mktcap = _get_mktcap_batch([s['code'] for s in step2])
    step3 = []
    for s in step2:
        cap = mktcap.get(s['code'], 0)
        if 30 <= cap <= 300:
            s['mktcap'] = cap
            step3.append(s)
    if not step3:
        return []

    # 4. 近1年涨停>2次 + 计算 vol_ratio / close_change_pct / prev_day_change_pct（并发查 K 线）
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            ex.submit(_count_limit_up_and_prev_vol, s['code'], td_dash): s
            for s in step3
        }
        for future in as_completed(futures):
            s = futures[future]
            try:
                limit_up_cnt, prev_vol, close_price, prev_close, prev_prev_close, next_close, open_price = future.result()
            except Exception:
                limit_up_cnt, prev_vol, close_price, prev_close, prev_prev_close, next_close, open_price = 0, None, None, None, None, None, None
            s['limit_up_cnt'] = limit_up_cnt
            # vol_ratio: 竞价委托手 / 昨日成交量(手)；竞价期间用 prev_close 近似当日价
            ref_price = close_price or prev_close
            if prev_vol and prev_vol > 0 and ref_price and ref_price > 0:
                grab_hands = s['auction_order_amt'] * 10000 / ref_price / 100
                s['vol_ratio'] = round(grab_hands / prev_vol, 4)
            else:
                s['vol_ratio'] = None
            # 收盘涨幅（target_date 当日）；竞价期间 close_price=None → None
            if close_price and prev_close and prev_close > 0:
                s['close_change_pct'] = round((close_price - prev_close) / prev_close * 100, 2)
            else:
                s['close_change_pct'] = None
            s['today_change_pct'] = s['close_change_pct']
            # 上一日涨幅（target_date 前一日）
            if prev_close and prev_prev_close and prev_prev_close > 0:
                s['prev_day_change_pct'] = round((prev_close - prev_prev_close) / prev_prev_close * 100, 2)
            else:
                s['prev_day_change_pct'] = None
            # 后一日涨幅（target_date 后一日）
            if next_close and close_price and close_price > 0:
                s['next_day_change_pct'] = round((next_close - close_price) / close_price * 100, 2)
            else:
                s['next_day_change_pct'] = None
            # 竞价到收盘涨幅（集合竞价开盘价→收盘价）
            if close_price and open_price and open_price > 0:
                s['auction_to_close_pct'] = round((close_price - open_price) / open_price * 100, 2)
            else:
                s['auction_to_close_pct'] = None

    step4 = [s for s in step3 if s.get('limit_up_cnt', 0) > 2]
    if not step4:
        return []

    # 5. 补充行业/题材
    merge_stock_meta(step4)

    return step4
