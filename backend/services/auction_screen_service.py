"""
竞价筛选条件服务
从全市场竞价金额排行中筛选沪深A股主板票（排除ST）

stockapi 扫全市场，每种排序返回前50条；三种排序（委托额/成交额/开盘额）取并集，
可覆盖全市场竞价金额约前55-60支；过滤主板后通常得到40+支主板候选池。
"""
import json
import logging
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

_STOCKAPI_TOKEN = 'c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e'
_STOCKAPI_BASE = 'http://user.stockapi.com.cn/v1/base/jjqcUser'
_STOCKAPI_TYPES = [1, 2, 3]  # 1=委托额 2=成交额 3=开盘额

# 主板代码前缀（沪深A股主板，排除科创/创业/北交）
_MAIN_BOARD_PREFIXES = ('000', '001', '002', '003', '600', '601', '603', '605', '606')

# ── stockapi 双层缓存（内存 + 磁盘持久化，防止重启丢失 + 防止每日限额耗尽）────
# 历史日期：永久缓存；当日数据：60 秒刷新
_STOCKAPI_TTL_TODAY = 60
_STOCKAPI_TTL_HIST = 86400 * 30
_CACHE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'stockapi_cache.json')
_STOCKAPI_RESULT_CACHE: dict[str, dict] = {}


def _load_disk_cache() -> None:
    """启动时从磁盘恢复历史 stockapi 缓存"""
    global _STOCKAPI_RESULT_CACHE
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
                _STOCKAPI_RESULT_CACHE = json.load(f)
            logger.info(f"stockapi 磁盘缓存加载 {len(_STOCKAPI_RESULT_CACHE)} 条")
    except Exception as e:
        logger.warning(f"加载 stockapi 磁盘缓存失败: {e}")
        _STOCKAPI_RESULT_CACHE = {}


def _save_disk_cache() -> None:
    """将历史日期的缓存写入磁盘（不保存今日数据，避免陈旧）"""
    from datetime import date as _date
    today = _date.today().strftime('%Y-%m-%d')
    to_save = {k: v for k, v in _STOCKAPI_RESULT_CACHE.items() if not k.startswith(today)}
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(to_save, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"保存 stockapi 磁盘缓存失败: {e}")


# 模块加载时立即恢复磁盘缓存
_load_disk_cache()


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
    from utils.stock_code import is_valid_stock_code
    if not is_valid_stock_code(code):
        return False
    return code.startswith(_MAIN_BOARD_PREFIXES)


def _fallback_candidate_pool(
    trade_date: str,
    period: int,
    cached: dict | None,
    *,
    reason: str,
) -> list[dict]:
    """stockapi 无有效数据时：沿用历史缓存或 DB 快照"""
    if cached and cached.get('data'):
        logger.warning(f"stockapi {trade_date} {reason}，沿用内存/磁盘缓存")
        return [dict(s) for s in cached['data']]
    db_stocks = _load_from_db(trade_date, period)
    if db_stocks:
        logger.info(f"stockapi {trade_date} {reason}，DB 回退 {len(db_stocks)} 支")
        return [dict(s) for s in db_stocks]

    from datetime import datetime, timedelta
    from utils.date_utils import get_valid_trading_date

    today_str = get_valid_trading_date()
    if trade_date == today_str:
        d = datetime.strptime(trade_date, '%Y-%m-%d')
        prev = d
        for _ in range(7):
            prev -= timedelta(days=1)
            if prev.weekday() >= 5:
                continue
            prev_str = prev.strftime('%Y-%m-%d')
            prev_stocks = _load_from_db(prev_str, period)
            if prev_stocks:
                logger.info(
                    f"stockapi {trade_date} {reason}，回退上一交易日 {prev_str}: {len(prev_stocks)} 支"
                )
                return [dict(s) for s in prev_stocks]

    logger.warning(f"stockapi {trade_date} {reason}，DB 也无数据")
    return []


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
    结果在内存中缓存：历史日期永久缓存，当日数据60秒刷新，防止超出 stockapi 日调用限额。

    参数：
        trade_date  — YYYY-MM-DD 或 YYYYMMDD
        period      — 0=早盘竞价 1=尾盘
        top_n       — 目标主板股票数量（实际数量受数据源限制，通常40-45支）
    """
    from datetime import date as _date

    if len(trade_date) == 8:
        trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

    today_str = _date.today().strftime('%Y-%m-%d')
    is_today = (trade_date == today_str)
    ttl = _STOCKAPI_TTL_TODAY if is_today else _STOCKAPI_TTL_HIST
    cache_key = f"{trade_date}_{period}"

    cached = _STOCKAPI_RESULT_CACHE.get(cache_key)
    if cached and cached.get('data') and (time.time() - cached['ts']) < ttl:
        return [dict(s) for s in cached['data']]  # 返回副本，避免被调用方修改

    from utils.stock_code import is_valid_stock_code

    # 并发拉三种排序，合并去重
    raw_map: dict[str, dict] = {}
    masked_rows = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(_fetch_stockapi_raw, trade_date, period, t): t
            for t in _STOCKAPI_TYPES
        }
        for future in as_completed(futures):
            for r in future.result():
                code = str(r.get('code', '')).zfill(6)
                if not is_valid_stock_code(code):
                    masked_rows += 1
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
        reason = '返回脱敏代码' if masked_rows else '无数据'
        fallback = _fallback_candidate_pool(trade_date, period, cached, reason=reason)
        if fallback:
            _STOCKAPI_RESULT_CACHE[cache_key] = {'ts': time.time(), 'data': fallback}
        return fallback

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

    if not result:
        reason = '无有效主板候选'
        if masked_rows:
            reason = f'返回脱敏代码({masked_rows}条)'
        fallback = _fallback_candidate_pool(trade_date, period, cached, reason=reason)
        if fallback:
            _STOCKAPI_RESULT_CACHE[cache_key] = {'ts': time.time(), 'data': fallback}
            if not is_today:
                _save_disk_cache()
            return fallback
        return []

    _STOCKAPI_RESULT_CACHE[cache_key] = {'ts': time.time(), 'data': result}
    if not is_today:
        _save_disk_cache()  # 历史数据持久化到磁盘，重启后无需重新拉取
    return [dict(s) for s in result]


def _load_from_db(trade_date: str, period: int) -> list[dict]:
    """当 stockapi 超限时，从 auction_grab_stocks 表回退构建候选池"""
    date_compact = trade_date.replace('-', '')
    try:
        from utils.db import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT code, name, grab_order_amount, grab_turnover, grab_change_pct
                   FROM auction_grab_stocks WHERE date=%s AND period=%s""",
                (date_compact, period),
            )
            rows = cur.fetchall()
        conn.close()
        result = []
        for row in rows:
            code = str(row['code']).zfill(6)
            if not _is_main_board(code):
                continue
            result.append({
                'code': code,
                'name': row.get('name') or '',
                'auction_order_amt': float(row.get('grab_order_amount') or 0),
                'auction_trade_amt': float(row.get('grab_turnover') or 0),
                'auction_change_pct': float(row.get('grab_change_pct') or 0),
                'board': _board_label(code),
            })
        if result:
            logger.info(f"stockapi 超限，DB 回退 {trade_date} period={period}: {len(result)} 支")
        return result
    except Exception as e:
        logger.warning(f"DB 回退失败 {trade_date}: {e}")
        return []


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


_INDEX_NAME_MAP = {
    '000001': '上证指数',
    '000300': '沪深300',
    '399001': '深证成指',
}


def get_market_sentiment() -> dict:
    """
    查上证/沪深300/深证三大指数实时涨幅，评估大面风险。
    risk_level: 'danger' | 'caution' | 'neutral' | 'positive'
    指数名称使用硬编码映射，避免 Tencent API GBK 编码导致乱码。
    """
    text = _curl('https://qt.gtimg.cn/q=sh000001,sh000300,sz399001')
    indexes = []
    for line in text.split('\n'):
        if '"' not in line or '~' not in line:
            continue
        try:
            fields = line.split('"')[1].split('~')
            if len(fields) >= 6:
                code6 = fields[2].strip()
                current = float(fields[3]) if fields[3] else 0.0
                prev_close = float(fields[4]) if fields[4] else 0.0
                if prev_close <= 0:
                    continue
                pct = (current - prev_close) / prev_close * 100
                name = _INDEX_NAME_MAP.get(code6, code6)
                indexes.append({
                    'name': name,
                    'code': code6,
                    'change_pct': round(pct, 2),
                })
        except Exception:
            pass

    if not indexes:
        return {'risk_level': 'unknown', 'hint': '', 'indexes': []}

    avg = sum(i['change_pct'] for i in indexes) / len(indexes)

    if avg <= -1.5:
        risk = 'danger'
        hint = f'大盘全线低开（均跌 {avg:.2f}%），大面风险极高，建议今日不参与竞价抢筹'
    elif avg <= -0.8:
        risk = 'caution'
        hint = f'大盘竞价偏弱（均跌 {abs(avg):.2f}%），大面风险较高，建议轻仓或观望'
    elif avg >= 0.8:
        risk = 'positive'
        hint = f'大盘竞价高开（均涨 {avg:.2f}%），市场情绪偏好，可正常参与'
    else:
        risk = 'neutral'
        hint = f'大盘竞价平稳（{avg:+.2f}%），市场情绪中性，谨慎参与'

    return {
        'risk_level': risk,
        'avg_change': round(avg, 2),
        'hint': hint,
        'indexes': indexes,
    }


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
    完整高级筛选流程，返回通过所有条件的股票列表。

    条件（按顺序）：
      主板非ST → 竞价涨幅2-5% → 流通市值30-300亿 → 近1年涨停>2次
      → 竞价量比≥3%（竞价委托手/昨日成交量） → 竞价委托额≥200万
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

    # 2. 竞价涨幅 1-7%
    step2 = filter_by_auction_change(step1, 1.0, 7.0)
    if not step2:
        return []

    # 3. 流通市值 20-500亿
    mktcap = _get_mktcap_batch([s['code'] for s in step2])
    step3 = []
    for s in step2:
        cap = mktcap.get(s['code'], 0)
        if 20 <= cap <= 500:
            s['mktcap'] = cap
            step3.append(s)
    if not step3:
        return []

    # 4. 近1年涨停>2次 + 计算 vol_ratio / 各涨幅 / 竞价换手率（并发查 K 线，限4线程防崩）
    with ThreadPoolExecutor(max_workers=4) as ex:
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
            # 竞价换手率 = 竞价委托金额(万) / 流通市值(亿×10000万)
            cap = s.get('mktcap') or 0
            if cap > 0:
                s['auction_turnover_rate'] = round(s['auction_order_amt'] / (cap * 10000), 5)
            else:
                s['auction_turnover_rate'] = None
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

    # 近1年涨停 > 1次（有涨停基因）
    step4 = [s for s in step3 if s.get('limit_up_cnt', 0) > 1]
    if not step4:
        return []

    # 5. 竞价量比 ≥ 2%；量比无法计算的保留
    step5 = [s for s in step4 if s.get('vol_ratio') is None or s['vol_ratio'] >= 0.02]
    if not step5:
        step5 = step4  # 全都没量比数据时回退

    # 6. 竞价委托额 ≥ 100万：过滤极小单子噪音
    step6 = [s for s in step5 if s.get('auction_order_amt', 0) >= 100]
    if not step6:
        step6 = step5  # 回退

    # 7. 补充行业/题材
    merge_stock_meta(step6)

    return step6


# ─── 回测优化 ────────────────────────────────────────────────────────────────

# 每个参数集字段说明：
#   min_pct/max_pct  竞价涨幅区间(%)
#   min_mkt/max_mkt  流通市值区间(亿)
#   min_lu           近1年涨停次数下限（严格大于）
#   min_vr           竞价量比下限（竞价委托手/昨日成交量），None=不限
#   min_order        竞价委托金额下限(万元)，None=不限
_BACKTEST_PARAM_SETS = [
    # ── 基线 ──────────────────────────────────────────────────────────────────
    {'name': '旧策略(2-7%/30-300亿)',   'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': None,  'min_order': None},
    # ── 竞价涨幅优化 ──────────────────────────────────────────────────────────
    {'name': '涨幅1.5-4%',             'min_pct': 1.5, 'max_pct': 4.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': None,  'min_order': None},
    {'name': '涨幅2-4%',               'min_pct': 2.0, 'max_pct': 4.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': None,  'min_order': None},
    {'name': '涨幅2-5%',               'min_pct': 2.0, 'max_pct': 5.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': None,  'min_order': None},
    {'name': '涨幅2-6%',               'min_pct': 2.0, 'max_pct': 6.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': None,  'min_order': None},
    {'name': '涨幅3-6%',               'min_pct': 3.0, 'max_pct': 6.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': None,  'min_order': None},
    # ── 市值优化 ──────────────────────────────────────────────────────────────
    {'name': '市值50-200亿',            'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 50,  'max_mkt': 200, 'min_lu': 2, 'min_vr': None,  'min_order': None},
    {'name': '市值30-150亿',            'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 30,  'max_mkt': 150, 'min_lu': 2, 'min_vr': None,  'min_order': None},
    # ── 竞价量比优化 ──────────────────────────────────────────────────────────
    {'name': '+量比≥2%',               'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': 0.02,  'min_order': None},
    {'name': '+量比≥3%',               'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': 0.03,  'min_order': None},
    {'name': '+量比≥5%',               'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': 0.05,  'min_order': None},
    # ── 委托额过滤 ────────────────────────────────────────────────────────────
    {'name': '+委托≥300万',             'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': None,  'min_order': 300},
    {'name': '+委托≥500万',             'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 2, 'min_vr': None,  'min_order': 500},
    # ── 涨停基因增强 ──────────────────────────────────────────────────────────
    {'name': '涨停>3次',               'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 3, 'min_vr': None,  'min_order': None},
    {'name': '涨停>4次',               'min_pct': 2.0, 'max_pct': 7.0, 'min_mkt': 30,  'max_mkt': 300, 'min_lu': 4, 'min_vr': None,  'min_order': None},
    # ── 综合组合（当前策略） ──────────────────────────────────────────────────
    {'name': '当前策略(2-6%+量比2%)',  'min_pct': 2.0, 'max_pct': 6.0, 'min_mkt': 50,  'max_mkt': 200, 'min_lu': 2, 'min_vr': 0.02,  'min_order': 200},
    # ── 复合最优候选 ──────────────────────────────────────────────────────────
    {'name': '组合A(2-5%/50-200亿/量比2%)',  'min_pct': 2.0, 'max_pct': 5.0, 'min_mkt': 50, 'max_mkt': 200, 'min_lu': 2, 'min_vr': 0.02, 'min_order': 300},
    {'name': '组合B(2-5%/50-200亿/量比3%)',  'min_pct': 2.0, 'max_pct': 5.0, 'min_mkt': 50, 'max_mkt': 200, 'min_lu': 3, 'min_vr': 0.03, 'min_order': 500},
    {'name': '组合C(2-4%/50-150亿/量比3%)',  'min_pct': 2.0, 'max_pct': 4.0, 'min_mkt': 50, 'max_mkt': 150, 'min_lu': 3, 'min_vr': 0.03, 'min_order': 300},
    {'name': '组合D(3-6%/50-200亿/量比2%)',  'min_pct': 3.0, 'max_pct': 6.0, 'min_mkt': 50, 'max_mkt': 200, 'min_lu': 3, 'min_vr': 0.02, 'min_order': 300},
]


def _fetch_raw_klines(code: str) -> list:
    """获取复权日K线（最近250日），用于回测"""
    prefix = 'sz' if code.startswith(('0', '3')) else 'sh'
    url = (f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
           f'?_var=kline_dayqfq&param={prefix}{code},day,,,250,qfq')
    text = _curl(url)
    try:
        idx = text.index('{')
        d = json.loads(text[idx:])
        return d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
    except Exception:
        return []


def _kline_metrics_for_date(klines: list, target_date: str) -> dict:
    """从 K 线列表提取指定日期的关键指标（limit_up_cnt_1y / auction_to_close_pct 等）"""
    cnt = 0
    prev_c: float | None = None
    for i, k in enumerate(klines):
        try:
            c = float(k[2])
            if prev_c and prev_c > 0 and (c - prev_c) / prev_c * 100 >= 9.8:
                cnt += 1
            if str(k[0]) == target_date:
                open_price = float(k[1]) if len(k) > 1 else None
                prev_close = float(klines[i - 1][2]) if i > 0 else None
                prev_vol = float(klines[i - 1][5]) if i > 0 else None
                result: dict = {
                    'limit_up_cnt_1y': cnt,
                    'close_price': c,
                    'open_price': open_price,
                    'prev_close': prev_close,
                    'prev_vol': prev_vol,
                }
                if c and open_price and open_price > 0:
                    result['auction_to_close_pct'] = round((c - open_price) / open_price * 100, 2)
                return result
            prev_c = c
        except Exception:
            pass
    # target_date 不在 K 线（竞价期间等），用最后一根作 prev
    result = {'limit_up_cnt_1y': cnt}
    if klines:
        try:
            result['prev_close'] = float(klines[-1][2])
            result['prev_vol'] = float(klines[-1][5])
        except Exception:
            pass
    return result


def _get_mktcap_batch_chunked(codes: list[str], chunk: int = 80) -> dict[str, float]:
    """分批查流通市值，避免 URL 过长"""
    result: dict[str, float] = {}
    for i in range(0, len(codes), chunk):
        result.update(_get_mktcap_batch(codes[i: i + chunk]))
    return result


def run_backtest(n_days: int = 10, period: int = 0) -> dict:
    """
    对过去 n_days 个交易日运行参数网格回测，返回各组合的日均竞价到收盘涨幅和胜率。
    流程：
      1. 并发拉各日 stockapi 候选池（竞价涨幅≥1% 的主板非ST）
      2. 批量查所有唯一股票的流通市值
      3. 并发拉所有唯一股票的 K 线（每股一次，覆盖多日）
      4. 对每日候选应用不同参数组合，统计 auction_to_close_pct
    """
    from datetime import date as _date, timedelta

    # 生成最近 n_days 个交易日（跳过周末）
    trade_dates: list[str] = []
    d = _date.today()
    while len(trade_dates) < n_days:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            trade_dates.append(d.strftime('%Y-%m-%d'))
    trade_dates = sorted(trade_dates)

    # Phase 1: 逐日拉候选池（历史日期已缓存，不消耗 stockapi 额度）
    date_candidates: dict[str, list[dict]] = {}
    for dt in trade_dates:
        try:
            stocks = get_main_board_top_auction(dt, period, 60)
            date_candidates[dt] = [
                s for s in stocks if s.get('auction_change_pct', 0) >= 1.0
            ]
        except Exception as e:
            logger.warning(f"backtest stockapi {dt}: {e}")
            date_candidates[dt] = []

    all_codes = list({s['code'] for cands in date_candidates.values() for s in cands})
    if not all_codes:
        return {'results': [], 'best_params': None, 'trade_dates': trade_dates, 'total_days': 0}

    # Phase 2: 批量查流通市值
    mktcap_map = _get_mktcap_batch_chunked(all_codes)
    for cands in date_candidates.values():
        for s in cands:
            s['mktcap'] = mktcap_map.get(s['code'], 0)

    # Phase 3: 并发拉 K 线（限制并发数防止 CPU/内存过载）
    kline_store: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        kf = {ex.submit(_fetch_raw_klines, code): code for code in all_codes}
        for future in as_completed(kf):
            code = kf[future]
            try:
                kline_store[code] = future.result()
            except Exception:
                kline_store[code] = []

    # Phase 4: 为每日每股计算指标
    for dt, cands in date_candidates.items():
        for s in cands:
            metrics = _kline_metrics_for_date(kline_store.get(s['code'], []), dt)
            s.update(metrics)
            # vol_ratio（需要 prev_vol + ref_price）
            ref = s.get('close_price') or s.get('prev_close')
            pv = s.get('prev_vol')
            if ref and ref > 0 and pv and pv > 0:
                s['vol_ratio'] = s['auction_order_amt'] * 10000 / ref / 100 / pv
            # 竞价换手率 = 竞价委托金额(万) / 流通市值(亿×10000)
            cap = s.get('mktcap') or 0
            if cap > 0:
                s['auction_turnover_rate'] = s['auction_order_amt'] / (cap * 10000)

    # Phase 5: 参数网格评估
    results = []
    for params in _BACKTEST_PARAM_SETS:
        daily_rows = []
        for dt in sorted(date_candidates):
            cands = date_candidates[dt]
            filtered = [
                s for s in cands
                if params['min_pct'] <= s.get('auction_change_pct', 0) <= params['max_pct']
                and params['min_mkt'] <= s.get('mktcap', 0) <= params['max_mkt']
                and s.get('limit_up_cnt_1y', 0) > params['min_lu']
                and (params['min_vr'] is None or (s.get('vol_ratio') or 0) >= params['min_vr'])
                and (params.get('min_order') is None or s.get('auction_order_amt', 0) >= params['min_order'])
                and s.get('auction_to_close_pct') is not None
            ]
            if not filtered:
                continue
            pcts = [s['auction_to_close_pct'] for s in filtered]
            wins = sum(1 for p in pcts if p > 0)
            daily_rows.append({
                'date': dt,
                'count': len(filtered),
                'avg_pct': round(sum(pcts) / len(pcts), 2),
                'win_rate': round(wins / len(pcts) * 100, 1),
                'picks': [
                    {'code': s['code'], 'name': s['name'],
                     'pct': s['auction_to_close_pct'],
                     'auction_pct': round(s.get('auction_change_pct', 0), 2)}
                    for s in sorted(filtered, key=lambda x: x['auction_to_close_pct'], reverse=True)
                ],
            })
        if not daily_rows:
            continue
        avgs = [r['avg_pct'] for r in daily_rows]
        wrs = [r['win_rate'] for r in daily_rows]
        results.append({
            'params': params,
            'days': len(daily_rows),
            'avg_pct': round(sum(avgs) / len(avgs), 2),
            'win_rate': round(sum(wrs) / len(wrs), 1),
            'daily': daily_rows,
        })

    results.sort(key=lambda x: x['avg_pct'], reverse=True)
    best = results[0] if results else None

    return {
        'results': results,
        'best_params': best['params'] if best else None,
        'trade_dates': sorted(date_candidates.keys()),
        'total_days': sum(1 for c in date_candidates.values() if c),
    }
