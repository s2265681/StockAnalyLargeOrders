"""
竞价抢筹 API
数据来源: stockapi.com.cn 竞价抢筹接口；日快照入库 auction_grab_stocks

接口设计（两阶段）：
  GET /api/v1/auction-grab        — 立即返回原始抢筹数据，同时后台异步计算涨幅+评分
  GET /api/v1/auction-grab/score  — 返回评分数据（后台就绪后可用）
"""
import logging
import threading
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

# 原始数据内存缓存（当日频繁刷新）
_cache = {}
_CACHE_TTL = 120

# 加工后缓存（含评分），后台线程写入，score 接口优先读此处
_processed_cache = {}
_PROCESSED_TTL_TODAY = 120
_PROCESSED_TTL_LIVE = 45  # 当日盘中：涨幅/推荐度刷新间隔
_PROCESSED_TTL_HISTORY = 86400

_kline_cache = {}
_KLINE_CACHE_TTL = 1800

# 正在进行后台富化的 key 集合，防重复触发
_enrich_in_progress: set = set()

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
    """补充当日收盘涨幅与次日涨幅（并发 HTTP，仅在后台线程调用）"""
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
    """从 stockapi 获取竞价抢筹数据"""
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


def _get_processed_payload(date_compact: str, period_int: int, is_today: bool):
    entry = _processed_cache.get(_processed_cache_key(date_compact, period_int))
    if not entry:
        return None, None
    if (time.time() - entry['ts']) >= _processed_cache_ttl(is_today):
        _processed_cache.pop(_processed_cache_key(date_compact, period_int), None)
        return None, None
    return [dict(x) for x in entry['items']], dict(entry['meta'])


def _set_processed_payload(date_compact: str, period_int: int, items: list, rec_meta: dict) -> None:
    _processed_cache[_processed_cache_key(date_compact, period_int)] = {
        'ts': time.time(),
        'items': [dict(x) for x in items],
        'meta': dict(rec_meta or {}),
    }


def _codes_signature(items):
    return frozenset(str(x.get('code', '')).zfill(6) for x in (items or []) if x.get('code'))


def _is_market_hours() -> bool:
    """简易 A 股交易时段（含集合竞价后至收盘）"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return (925 <= t <= 1135) or (1300 <= t <= 1505)


def _limit_up_threshold(code: str) -> float:
    code = str(code).zfill(6)
    if code.startswith(('30', '68')):
        return 19.5
    if code.startswith(('4', '8')):
        return 29.5
    return 9.5


def _is_at_limit_up(code: str, change_pct) -> bool:
    if change_pct is None:
        return False
    try:
        return float(change_pct) >= _limit_up_threshold(code)
    except (TypeError, ValueError):
        return False


def _enrich_prev_day_change(items, trade_date: str):
    """补充昨日（上一交易日）涨跌幅"""
    if not items:
        return
    prev_trade_date = _offset_trading_date(trade_date, -1)
    code_set = {item.get('code') for item in items if item.get('code')}
    futures = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        for code in code_set:
            futures[executor.submit(_get_daily_change_pct, code, prev_trade_date)] = code
        for future in as_completed(futures):
            code = futures[future]
            try:
                pct = future.result()
            except Exception:
                pct = None
            if pct is None:
                continue
            for item in items:
                if item.get('code') == code and item.get('prev_day_change_pct') is None:
                    item['prev_day_change_pct'] = pct


def _enrich_live_quotes(items, trade_date: str, is_today: bool):
    """盘中实时：今日涨幅 + 昨日涨幅（并发 EastMoney）"""
    if not items or not is_today:
        return

    prev_trade_date = _offset_trading_date(trade_date, -1)
    code_set = {item.get('code') for item in items if item.get('code')}
    if not code_set:
        return

    live_map = {code: {'today': None, 'prev': None} for code in code_set}
    futures = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        for code in code_set:
            futures[executor.submit(_get_realtime_change_pct, code)] = (code, 'today')
            futures[executor.submit(_get_daily_change_pct, code, prev_trade_date)] = (code, 'prev')
        for future in as_completed(futures):
            code, field = futures[future]
            try:
                live_map[code][field] = future.result()
            except Exception as e:
                logger.warning(f"实时涨幅查询失败 code={code} field={field}: {e}")

    for item in items:
        code = item.get('code')
        live = live_map.get(code, {})
        today_pct = live.get('today')
        prev_pct = live.get('prev')
        if today_pct is not None:
            item['today_change_pct'] = today_pct
            if _is_market_hours():
                item['close_change_pct'] = today_pct
        if prev_pct is not None:
            item['prev_day_change_pct'] = prev_pct


def _get_realtime_change_pct(code: str):
    """EastMoney 实时涨跌幅 %"""
    cache_key = f"rt_{code}"
    now = time.time()
    cached = _kline_cache.get(cache_key)
    if cached and (now - cached['ts']) < 30:
        return cached['value']
    try:
        source = EastMoneyFreeSource()
        quote = source.get_realtime_quote(code)
        value = None
        if quote and quote.get('change_percent') is not None:
            value = round(float(quote['change_percent']), 2)
    except Exception as e:
        logger.warning(f"实时行情失败 code={code}: {e}")
        value = None
    _kline_cache[cache_key] = {'ts': now, 'value': value}
    return value


def _enrichment_from_item(item: dict) -> dict:
    """单条 item -> 可合并到前端的富化字段"""
    out = {}
    for key in ('close_change_pct', 'next_day_change_pct', 'today_change_pct', 'prev_day_change_pct'):
        if item.get(key) is not None:
            out[key] = item.get(key)
    if item.get('recommend_score') is not None:
        out['recommend_stars'] = int(item.get('recommend_stars') or 0)
        out['recommend_reason'] = item.get('recommend_reason') or ''
        out['recommend_score'] = float(item.get('recommend_score') or 0)
    return out


def _build_enrichments_map(items: list) -> dict:
    result = {}
    for item in items or []:
        code = str(item.get('code', '')).zfill(6)
        if not code:
            continue
        enrichment = _enrichment_from_item(item)
        if enrichment:
            result[code] = enrichment
    return result


def _load_items_for_request(date_compact, period_int, trade_date, is_today):
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


def _processed_cache_ttl(is_today: bool) -> int:
    if is_today and _is_market_hours():
        return _PROCESSED_TTL_LIVE
    return _PROCESSED_TTL_TODAY if is_today else _PROCESSED_TTL_HISTORY


def _should_skip_enrich(date_compact: str, period_int: int, is_today: bool) -> bool:
    """是否跳过本次后台富化"""
    key = _processed_cache_key(date_compact, period_int)
    entry = _processed_cache.get(key)
    ttl = _processed_cache_ttl(is_today)
    if entry and (time.time() - entry['ts']) < ttl:
        return True
    # 历史日：DB 已有评分且非盘中实时场景 → 不重算
    if not is_today and ag_store.scores_exist(date_compact, period_int):
        return True
    return False


def _trigger_background_enrich(date_compact: str, period_int: int, items: list, trade_date: str, is_today: bool, *, force: bool = False):
    """触发后台线程：异步计算涨幅+评分，写库并更新内存缓存"""
    key = _processed_cache_key(date_compact, period_int)
    if key in _enrich_in_progress:
        return

    if not force and _should_skip_enrich(date_compact, period_int, is_today):
        return

    _enrich_in_progress.add(key)
    items_copy = [dict(x) for x in items]

    def _do_enrich():
        rec_meta = {"stage": "", "hint": ""}
        try:
            # 1. 昨日/今日实时涨幅
            if is_today:
                _enrich_live_quotes(items_copy, trade_date, is_today)
            else:
                _enrich_prev_day_change(items_copy, trade_date)

            # 昨日涨幅算好后立即落库（COALESCE 保证不覆盖已有值）
            try:
                ag_store.update_return_fields(date_compact, period_int, items_copy)
            except Exception as e:
                logger.warning(f"昨日涨幅写库失败（跳过）{date_compact}: {e}")

            # 2. 收盘/次日涨幅（历史日或收盘后补全）
            if not is_today or not _is_market_hours():
                if ag_store.items_need_return_enrich(items_copy):
                    _enrich_close_and_next_change(items_copy, trade_date)
                    try:
                        ag_store.update_return_fields(date_compact, period_int, items_copy)
                    except Exception as e:
                        logger.warning(f"涨幅写库失败（跳过）{date_compact}: {e}")

            # 3. 行业/题材元数据（补全缺失的 stock_meta 缓存）
            try:
                codes = [str(x.get('code', '')).zfill(6) for x in items_copy if x.get('code')]
                existing_meta = ag_store.load_stock_meta(codes)
                missing_meta = [c for c in codes if c not in existing_meta or not existing_meta[c].get('industry')]
                if missing_meta:
                    ag_store.populate_stock_meta_from_pool(missing_meta)
            except Exception as e:
                logger.warning(f"stock_meta populate 失败（跳过）{date_compact}: {e}")

            # 4. 推荐评分（情绪+题材+抢筹；排除竞价时已涨停）
            try:
                from services.auction_grab_recommendation import enrich_auction_recommendations
                live_changes = {
                    str(x.get('code', '')).zfill(6): x.get('today_change_pct')
                    for x in items_copy if x.get('code')
                }
                # period=0 早盘竞价不用盘中涨幅做涨停判定（用竞价涨幅），此处传 live_changes 仅供尾盘期间使用
                for x in items_copy:
                    c = str(x.get('code', '')).zfill(6)
                    if live_changes.get(c) is None:
                        live_changes[c] = x.get('close_change_pct') or x.get('grab_change_pct')
                rec_meta = enrich_auction_recommendations(
                    items_copy, trade_date, period_int, live_change_by_code=live_changes,
                )
            except Exception as e:
                logger.warning(f"评分计算失败（跳过）{date_compact}: {e}")

            _set_processed_payload(date_compact, period_int, items_copy, rec_meta)

            try:
                ag_store.update_score_fields(date_compact, period_int, items_copy)
                if not is_today or not _is_market_hours():
                    ag_store.update_return_fields(date_compact, period_int, items_copy)
                ag_store.save_score_meta(date_compact, period_int, rec_meta)
            except Exception as e:
                logger.warning(f"评分写库失败（跳过）{date_compact}: {e}")

            logger.info(f"后台富化完成 {date_compact} period={period_int}")
        except Exception as e:
            logger.error(f"后台富化意外失败 {date_compact}/{period_int}: {e}")
        finally:
            _enrich_in_progress.discard(key)

    threading.Thread(target=_do_enrich, daemon=True).start()


def fetch_and_cache_day(trade_date_dash: str, period: int = 0) -> list[dict]:
    """供回测/任务：优先读库，否则拉接口并入库"""
    date_compact = ag_store.to_compact_date(trade_date_dash)
    is_today = _is_today_trading_date(date_compact)

    items, source = _load_items_for_request(date_compact, period, trade_date_dash, is_today)
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
    获取竞价抢筹数据（快速接口，不含评分）
    参数:
        period: 0=早盘竞价抢筹(默认) 1=尾盘抢筹
        sort: wtje=委托金额(默认) cjje=成交金额 kpje=开盘金额 zf=涨幅
        dt: 日期(YYYYMMDD)，默认当天
    评分数据通过 /api/v1/auction-grab/score 单独获取
    """
    period = request.args.get('period', '0')
    sort_by = request.args.get('sort', 'wtje')
    dt = request.args.get('dt', _get_last_trading_day())
    trade_date = _format_date(dt)
    date_compact = ag_store.to_compact_date(dt)
    period_int = int(period)
    is_today = _is_today_trading_date(date_compact)

    items, source = _load_items_for_request(date_compact, period_int, trade_date, is_today)

    if items is None:
        raw_data = _fetch_from_stockapi(trade_date, period_int, _FETCH_API_TYPE)
        if raw_data is None:
            # 数据源不可用时，尝试读取 DB 缓存（今日数据可能已有）
            db_items = ag_store.load_items(date_compact, period_int)
            if db_items:
                items = db_items
                source = 'db_fallback'
            else:
                return v1_error_response('数据源暂不可用，请稍后重试')
        else:
            items = ag_store.items_from_raw_api(raw_data, trade_date)
            if items:
                ag_store.replace_snapshot(date_compact, period_int, items)
                cache_key = f"{date_compact}_{period_int}_{_FETCH_API_TYPE}"
                _cache[cache_key] = {'ts': time.time(), 'items': items}
            source = 'api'

    items = items or []

    # 合并行业/题材（stock_meta 缓存，缺失时后台补全）
    ag_store.merge_stock_meta(items)

    # 非阻塞：后台计算涨幅+评分（含 stock_meta 补全）
    _trigger_background_enrich(date_compact, period_int, items, trade_date, is_today)

    processed_items, rec_meta = _get_processed_payload(date_compact, period_int, is_today)
    score_ready = False
    if processed_items:
        score_ready = any(x.get('recommend_score') is not None for x in processed_items)
    if not score_ready:
        score_ready = ag_store.scores_exist(date_compact, period_int)

    return v1_success_response(data={
        'items': ag_store.sort_items(list(items), sort_by),
        'total': len(items),
        'date': dt,
        'period': period_int,
        'sort': sort_by,
        'score_ready': score_ready,
        'is_today': is_today,
        'live_refresh': is_today and _is_market_hours(),
    })


@auction_grab_bp.route('/api/v1/auction-grab/score', methods=['GET'])
def get_auction_grab_score():
    """
    获取竞价抢筹评分（后台异步计算，ready=false 时前端可稍后重试）
    参数同 /api/v1/auction-grab
    """
    period = request.args.get('period', '0')
    dt = request.args.get('dt', _get_last_trading_day())
    trade_date = _format_date(dt)
    date_compact = ag_store.to_compact_date(dt)
    period_int = int(period)
    is_today = _is_today_trading_date(date_compact)
    force_live = request.args.get('live', '0') == '1'

    if force_live and is_today:
        raw_items, _ = _load_items_for_request(date_compact, period_int, trade_date, is_today)
        if raw_items is None:
            raw_data = _fetch_from_stockapi(trade_date, period_int, _FETCH_API_TYPE)
            if raw_data:
                raw_items = ag_store.items_from_raw_api(raw_data, trade_date)
        if raw_items:
            _trigger_background_enrich(
                date_compact, period_int, raw_items, trade_date, is_today, force=True,
            )

    # 优先读内存缓存（后台线程写入，最新鲜）
    processed_items, rec_meta = _get_processed_payload(date_compact, period_int, is_today)
    if processed_items is not None:
        if is_today:
            from services.auction_grab_recommendation import strip_limit_up_recommendations
            strip_limit_up_recommendations(processed_items, period=period_int)
        enrichments = _build_enrichments_map(processed_items)
        has_scores = any(e.get('recommend_score') is not None for e in enrichments.values())
        return v1_success_response(data={
            'enrichments': enrichments,
            'emotion_stage': rec_meta.get('stage', ''),
            'recommend_hint': rec_meta.get('hint', ''),
            'ready': has_scores or bool(enrichments),
            'live_refresh': is_today and _is_market_hours(),
        })

    # 回退读库
    enrichments = ag_store.load_enrichment_fields(date_compact, period_int)
    meta = ag_store.load_score_meta(date_compact, period_int)

    # 若仍无富化数据，尝试用已缓存的原始数据触发后台计算
    if not enrichments:
        raw_items, _ = _load_items_for_request(date_compact, period_int, trade_date, is_today)
        if raw_items:
            _trigger_background_enrich(date_compact, period_int, raw_items, trade_date, is_today)

    has_scores = any(
        e.get('recommend_score') is not None for e in enrichments.values()
    )
    return v1_success_response(data={
        'enrichments': enrichments,
        'emotion_stage': meta.get('stage', ''),
        'recommend_hint': meta.get('hint', ''),
        'ready': has_scores or bool(enrichments),
        'live_refresh': is_today and _is_market_hours(),
    })
