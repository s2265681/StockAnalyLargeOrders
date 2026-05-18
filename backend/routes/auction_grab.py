"""
竞价抢筹 API
数据来源: stockapi.com.cn 竞价抢筹接口；日快照入库 auction_grab_stocks
"""
import logging
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, request
from services.eastmoney_free import EastMoneyFreeSource
from services import auction_grab_service as ag_store
from utils.date_utils import get_valid_trading_date
from utils.response import v1_success_response, v1_error_response

logger = logging.getLogger(__name__)

auction_grab_bp = Blueprint('auction_grab', __name__)

_STOCKAPI_TOKEN = 'c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e'
_STOCKAPI_BASE = 'http://user.stockapi.com.cn/v1/base/jjqcUser'

# 内存热缓存（当日频繁刷新）
_cache = {}
_CACHE_TTL = 120
# 加工后缓存：含收盘/次日涨幅 + 推荐度（避免每次请求重复打 K 线与题材库）
_processed_cache = {}
_PROCESSED_TTL_TODAY = 120
_PROCESSED_TTL_HISTORY = 86400
_kline_cache = {}
_KLINE_CACHE_TTL = 1800

# type 映射：前端排序key -> stockapi type 参数（入库统一按委托金额 type=1 拉全量）
_SORT_TYPE_MAP = {
    'wtje': 1,
    'cjje': 2,
    'kpje': 3,
    'zf': 1,
}
_FETCH_API_TYPE = 1


def _get_last_trading_day():
    d = datetime.now()
    dow = d.weekday()
    if dow == 5:
        d -= timedelta(days=1)
    elif dow == 6:
        d -= timedelta(days=2)
    return d.strftime('%Y%m%d')


def _format_date(dt_str):
    """YYYYMMDD -> YYYY-MM-DD"""
    if len(dt_str) == 8:
        return f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
    return dt_str


def _is_today_trading_date(date_compact: str) -> bool:
    today_compact = get_valid_trading_date().replace('-', '')
    return date_compact == today_compact


def _offset_trading_date(date_str, delta):
    """YYYY-MM-DD 偏移交易日（仅跳过周末）"""
    d = datetime.strptime(date_str, '%Y-%m-%d')
    moved = 0
    step = 1 if delta > 0 else -1
    while moved != delta:
        d += timedelta(days=step)
        if d.weekday() < 5:
            moved += step
    return d.strftime('%Y-%m-%d')


def _get_daily_change_pct(code, trade_date):
    """获取指定交易日涨跌幅（%），带短期缓存"""
    cache_key = f"{code}_{trade_date}"
    now = time.time()
    cached = _kline_cache.get(cache_key)
    if cached and (now - cached['ts']) < _KLINE_CACHE_TTL:
        return cached['value']

    try:
        source = EastMoneyFreeSource()
        kline = source.get_daily_kline(code, trade_date)
        value = kline.get('change_percent') if kline else None
        if value is None:
            value = source.get_daily_change_percent(code, trade_date)
        if value is not None:
            value = round(float(value), 2)
    except Exception as e:
        logger.warning(f"获取日涨幅失败 code={code} date={trade_date}: {e}")
        value = None

    _kline_cache[cache_key] = {'ts': now, 'value': value}
    return value


def _enrich_close_and_next_change(items, trade_date):
    """补充当日收盘涨幅与次日涨幅"""
    if not items:
        return

    next_trade_date = _offset_trading_date(trade_date, 1)
    today_str = datetime.now().strftime('%Y-%m-%d')
    next_day_available = next_trade_date <= today_str

    code_set = {item.get('code') for item in items if item.get('code')}
    if not code_set:
        return

    result_map = {code: {'close': None, 'next': None} for code in code_set}
    futures = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        for code in code_set:
            futures[executor.submit(_get_daily_change_pct, code, trade_date)] = (code, 'close')
            if next_day_available:
                futures[executor.submit(_get_daily_change_pct, code, next_trade_date)] = (code, 'next')

        for future in as_completed(futures):
            code, field = futures[future]
            try:
                result_map[code][field] = future.result()
            except Exception as e:
                logger.warning(f"涨幅并发查询失败 code={code} field={field}: {e}")

    for item in items:
        code = item.get('code')
        if item.get('close_change_pct') is None:
            item['close_change_pct'] = result_map.get(code, {}).get('close')
        if item.get('next_day_change_pct') is None and next_day_available:
            item['next_day_change_pct'] = result_map.get(code, {}).get('next')


def _fetch_from_stockapi(trade_date, period, api_type):
    """
    从 stockapi 获取竞价抢筹数据
    trade_date: YYYY-MM-DD
    period: 0=早盘 1=尾盘
    api_type: 1=委托金额排 2=成交金额排 3=开盘金额排
    """
    import subprocess
    import json as _json

    url = (
        f"{_STOCKAPI_BASE}?tradeDate={trade_date}"
        f"&period={period}&type={api_type}&token={_STOCKAPI_TOKEN}"
    )
    cmd = [
        'curl', '-s', '--max-time', '15', '--insecure',
        '-H', 'Referer: http://user.stockapi.com.cn/bidding',
        '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0 or not result.stdout.strip():
            logger.error(f"stockapi curl 失败: rc={result.returncode}")
            return None
        resp = _json.loads(result.stdout)
        if resp.get('code') != 20000:
            logger.warning(f"stockapi 返回错误: {resp.get('msg')}")
            return None
        return resp.get('data', [])
    except Exception as e:
        logger.error(f"stockapi 请求异常: {type(e).__name__}: {e}")
        return None


def _processed_cache_key(date_compact: str, period_int: int) -> str:
    return f"{date_compact}_{period_int}"


def _processed_cache_ttl(is_today: bool) -> int:
    return _PROCESSED_TTL_TODAY if is_today else _PROCESSED_TTL_HISTORY


def _invalidate_processed_cache(date_compact: str, period_int: int) -> None:
    _processed_cache.pop(_processed_cache_key(date_compact, period_int), None)


def _codes_signature(items: list[dict]) -> frozenset:
    return frozenset(str(x.get('code', '')).zfill(6) for x in (items or []) if x.get('code'))


def _invalidate_processed_if_codes_changed(
    date_compact: str, period_int: int, new_items: list[dict],
) -> None:
    """仅当股票列表变化时清空加工缓存，避免每 120s 刷新原始数据就重算推荐度"""
    entry = _processed_cache.get(_processed_cache_key(date_compact, period_int))
    if not entry:
        return
    if _codes_signature(entry.get('items')) != _codes_signature(new_items):
        _invalidate_processed_cache(date_compact, period_int)


def _clone_items(items: list[dict]) -> list[dict]:
    return [dict(x) for x in (items or [])]


def _get_processed_payload(date_compact: str, period_int: int, is_today: bool):
    entry = _processed_cache.get(_processed_cache_key(date_compact, period_int))
    if not entry:
        return None, None
    if (time.time() - entry['ts']) >= _processed_cache_ttl(is_today):
        _processed_cache.pop(_processed_cache_key(date_compact, period_int), None)
        return None, None
    return _clone_items(entry['items']), dict(entry['meta'])


def _set_processed_payload(
    date_compact: str,
    period_int: int,
    items: list[dict],
    rec_meta: dict,
) -> None:
    _processed_cache[_processed_cache_key(date_compact, period_int)] = {
        'ts': time.time(),
        'items': _clone_items(items),
        'meta': dict(rec_meta or {}),
    }


def _load_items_for_request(date_compact, period_int, trade_date, is_today):
    """
    加载竞价列表：
    - 当日：内存(120s) -> stockapi -> 入库
    - 历史：内存 -> 数据库（有则不再打外部接口）
    """
    cache_key = f"{date_compact}_{period_int}_{_FETCH_API_TYPE}"
    now = time.time()

    cached = _cache.get(cache_key)
    if cached and (now - cached['ts']) < _CACHE_TTL:
        return cached['items'], 'memory'

    if not is_today:
        db_items = ag_store.load_items(date_compact, period_int)
        if db_items:
            _cache[cache_key] = {'ts': now, 'items': db_items}
            return db_items, 'db'
        return None, 'miss'

    return None, 'miss'


def fetch_and_cache_day(trade_date_dash: str, period: int = 0) -> list[dict]:
    """供回测/任务：优先读库，否则拉接口并入库"""
    date_compact = ag_store.to_compact_date(trade_date_dash)
    is_today = _is_today_trading_date(date_compact)

    items, source = _load_items_for_request(
        date_compact, period, trade_date_dash, is_today
    )
    if items is not None:
        return items

    raw_data = _fetch_from_stockapi(trade_date_dash, period, _FETCH_API_TYPE)
    if not raw_data:
        return []

    items = ag_store.items_from_raw_api(raw_data, trade_date_dash)
    if items:
        ag_store.replace_snapshot(date_compact, period, items)
    return items


@auction_grab_bp.route('/api/v1/auction-grab', methods=['GET'])
def get_auction_grab():
    """
    获取竞价抢筹数据
    参数:
        period: 0=早盘竞价抢筹(默认) 1=尾盘抢筹
        sort: wtje=委托金额(默认) cjje=成交金额 kpje=开盘金额 zf=涨幅
        dt: 日期(YYYYMMDD)，默认当天
    """
    period = request.args.get('period', '0')
    sort_by = request.args.get('sort', 'wtje')
    dt = request.args.get('dt', _get_last_trading_day())
    trade_date = _format_date(dt)
    date_compact = ag_store.to_compact_date(dt)
    period_int = int(period)
    is_today = _is_today_trading_date(date_compact)

    # 优先返回已加工缓存，避免重复打 stockapi / K 线
    processed_items, rec_meta = _get_processed_payload(date_compact, period_int, is_today)
    if processed_items is not None:
        items = ag_store.sort_items(processed_items, sort_by)
        return v1_success_response(data={
            'items': items,
            'total': len(items),
            'date': dt,
            'period': period_int,
            'sort': sort_by,
            'emotion_stage': rec_meta.get('stage', ''),
            'recommend_hint': rec_meta.get('hint', ''),
        })

    items, source = _load_items_for_request(
        date_compact, period_int, trade_date, is_today
    )

    if items is None:
        raw_data = _fetch_from_stockapi(trade_date, period_int, _FETCH_API_TYPE)
        if raw_data is None:
            return v1_error_response('数据源暂不可用，请稍后重试')
        items = ag_store.items_from_raw_api(raw_data, trade_date)
        if items:
            ag_store.replace_snapshot(date_compact, period_int, items)
            cache_key = f"{date_compact}_{period_int}_{_FETCH_API_TYPE}"
            _cache[cache_key] = {'ts': time.time(), 'items': items}
            _invalidate_processed_if_codes_changed(date_compact, period_int, items)
        source = 'api'

    items = items or []
    if ag_store.items_need_return_enrich(items):
        _enrich_close_and_next_change(items, trade_date)
        ag_store.update_return_fields(date_compact, period_int, items)

    from services.auction_grab_recommendation import enrich_auction_recommendations
    rec_meta = enrich_auction_recommendations(items, trade_date, period_int)
    _set_processed_payload(date_compact, period_int, items, rec_meta)

    items = ag_store.sort_items(list(items), sort_by)

    return v1_success_response(data={
        'items': items,
        'total': len(items),
        'date': dt,
        'period': period_int,
        'sort': sort_by,
        'emotion_stage': rec_meta.get('stage', ''),
        'recommend_hint': rec_meta.get('hint', ''),
    })
