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
        from services.auction_unmask import unmask_stockapi_rows
        return unmask_stockapi_rows(resp.get('data', []))
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


def _fill_auction_to_close(items: list[dict]) -> None:
    """就地计算竞价到收盘涨幅：(close/open-1) = ((1+close_pct%)/(1+grab_pct%)-1)"""
    for item in items:
        if item.get('auction_to_close_pct') is not None:
            continue
        close_pct = item.get('close_change_pct')
        grab_pct = item.get('grab_change_pct')
        if close_pct is None or grab_pct is None:
            continue
        denom = 1 + grab_pct / 100
        if abs(denom) > 0.001:
            item['auction_to_close_pct'] = round(((1 + close_pct / 100) / denom - 1) * 100, 2)


def _enrichment_from_item(item: dict) -> dict:
    """单条 item -> 可合并到前端的富化字段"""
    out = {}
    for key in ('close_change_pct', 'next_day_change_pct', 'today_change_pct', 'prev_day_change_pct'):
        if item.get(key) is not None:
            out[key] = item.get(key)
    # 竞价到收盘涨幅（从 close_change_pct 和 grab_change_pct 推算）
    close_pct = item.get('close_change_pct')
    grab_pct = item.get('grab_change_pct')
    if close_pct is not None and grab_pct is not None:
        denom = 1 + grab_pct / 100
        if abs(denom) > 0.001:
            out['auction_to_close_pct'] = round(((1 + close_pct / 100) / denom - 1) * 100, 2)
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
        if raw_data:
            items = ag_store.items_from_raw_api(raw_data, trade_date)
            if items:
                ag_store.replace_snapshot(date_compact, period_int, items)
                cache_key = f"{date_compact}_{period_int}_{_FETCH_API_TYPE}"
                _cache[cache_key] = {'ts': time.time(), 'items': items}
            source = 'api'

        if not items:
            # API 无数据（超限、空结果、异常）→ 读当日 DB 缓存
            db_items = ag_store.load_items(date_compact, period_int)
            if db_items:
                items = db_items
                source = 'db_fallback'
            elif is_today:
                # 今日无数据，回退到前一交易日 DB
                prev_date = _offset_trading_date(trade_date, -1)
                prev_compact = prev_date.replace('-', '')
                prev_items = ag_store.load_items(prev_compact, period_int)
                if prev_items:
                    items = prev_items
                    date_compact = prev_compact
                    trade_date = prev_date
                    is_today = False
                    source = 'db_prev_day'
                else:
                    return v1_error_response('数据源暂不可用，请稍后重试')
            else:
                return v1_error_response('数据源暂不可用，请稍后重试')

    items = items or []

    # 合并行业/题材（stock_meta 缓存，缺失时后台补全）
    ag_store.merge_stock_meta(items)

    # 对 DB 历史数据就地补全竞价到收盘（有 close_change_pct 就能算）
    _fill_auction_to_close(items)

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


# 高级筛选结果缓存
_screen_cache: dict = {}
_SCREEN_CACHE_TTL_LIVE = 120    # 盘中
_SCREEN_CACHE_TTL_HIST = 3600   # 历史


@auction_grab_bp.route('/api/v1/auction-grab/screen', methods=['GET'])
def get_auction_grab_screen():
    """
    高级筛选：全市场竞价金额前N主板非ST → 竞价涨幅2-7% → 流通市值30-300亿 → 近1年涨停>2次
    返回通过所有条件的股票，含 vol_ratio（竞价委托量/昨日成交量）
    """
    from services.auction_screen_service import run_advanced_screen

    period = request.args.get('period', '0')
    dt = request.args.get('dt', _get_last_trading_day())
    trade_date = _format_date(dt)
    date_compact = ag_store.to_compact_date(dt)
    period_int = int(period)
    is_today = _is_today_trading_date(date_compact)

    cache_key = f'screen_{date_compact}_{period_int}'
    ttl = _SCREEN_CACHE_TTL_LIVE if (is_today and _is_market_hours()) else _SCREEN_CACHE_TTL_HIST
    cached = _screen_cache.get(cache_key)
    if cached and (time.time() - cached['ts']) < ttl:
        return v1_success_response(data=cached['payload'])

    try:
        stocks = run_advanced_screen(trade_date, period_int)
    except Exception as e:
        logger.error(f"高级筛选失败: {e}")
        return v1_error_response('高级筛选暂时不可用，请稍后重试')

    # 同行业涨停数量（来自当日涨停梯队库）
    limit_up_by_industry = {}
    try:
        from services.theme_service import get_limit_up_stocks_by_date
        for s in (get_limit_up_stocks_by_date(date_compact) or []):
            ind = (s.get('industry') or '').strip()
            if ind:
                limit_up_by_industry[ind] = limit_up_by_industry.get(ind, 0) + 1
    except Exception as e:
        logger.warning(f"获取涨停行业数据失败: {e}")

    # 大盘情绪（仅当日实时拉取，历史日期跳过）
    market_sentiment = None
    if is_today:
        try:
            from services.auction_screen_service import get_market_sentiment
            market_sentiment = get_market_sentiment()
        except Exception as e:
            logger.warning(f"获取大盘情绪失败: {e}")

    payload = {
        'items': stocks,
        'total': len(stocks),
        'date': dt,
        'period': period_int,
        'limit_up_by_industry': limit_up_by_industry,
        'market_sentiment': market_sentiment,
    }
    _screen_cache[cache_key] = {'ts': time.time(), 'payload': payload}
    return v1_success_response(data=payload)


# 回测结果缓存（计算较重，24h 有效）
_backtest_cache: dict = {}
_BACKTEST_CACHE_TTL = 86400


@auction_grab_bp.route('/api/v1/auction-grab/screen/backtest', methods=['GET'])
def get_auction_grab_screen_backtest():
    """参数网格回测：过去 N 日，评估多组筛选参数的竞价到收盘表现，含 AI 参数推荐"""
    from services.auction_screen_service import run_backtest
    from utils.claude_client import call_claude_for_scenario

    n_days = min(int(request.args.get('days', '10')), 20)
    period_int = int(request.args.get('period', '0'))

    cache_key = f'backtest_{n_days}_{period_int}'
    cached = _backtest_cache.get(cache_key)
    if cached and (time.time() - cached['ts']) < _BACKTEST_CACHE_TTL:
        return v1_success_response(data=cached['payload'])

    try:
        result = run_backtest(n_days=n_days, period=period_int)
    except Exception as e:
        logger.error(f"回测失败: {e}")
        return v1_error_response('回测暂时不可用，请稍后重试')

    # AI 分析：根据回测结果推荐最优参数
    ai_recommend = ''
    try:
        rows = result.get('results', [])
        if rows:
            top5 = rows[:5]
            lines = []
            for r in top5:
                p = r['params']
                vr_str = f"量比≥{p['min_vr']*100:.0f}%" if p.get('min_vr') else '不限量比'
                order_str = f"委托≥{p['min_order']}万" if p.get('min_order') else '不限委托额'
                lines.append(
                    f"  【{p['name']}】 涨幅{p['min_pct']}-{p['max_pct']}% | "
                    f"市值{p['min_mkt']}-{p['max_mkt']}亿 | {vr_str} | {order_str} | "
                    f"有效{r['days']}天 | 日均{r['avg_pct']:+.2f}% | 胜率{r['win_rate']}%"
                )
            worst5 = rows[-3:] if len(rows) > 5 else []
            worst_lines = []
            for r in worst5:
                p = r['params']
                worst_lines.append(f"  【{p['name']}】日均{r['avg_pct']:+.2f}% 胜率{r['win_rate']}%")

            prompt = (
                f"以下是竞价抢筹策略近{n_days}个交易日的参数组合回测结果（{'早盘' if period_int == 0 else '尾盘'}竞价）。\n\n"
                f"表现最好的前5组：\n" + '\n'.join(lines) + '\n\n'
                + (f"表现最差的3组：\n" + '\n'.join(worst_lines) + '\n\n' if worst_lines else '')
                + "请给出（200字以内，语言专业简洁）：\n"
                "1. 推荐哪组参数作为主策略（最优解），理由是什么\n"
                "2. 哪些条件对提升收益最关键（竞价涨幅区间/市值/量比/委托额/涨停次数）\n"
                "3. 如何避免大面（市场普跌日）的误伤，有无辅助判断建议\n"
                "4. 一句话总结当前参数优化方向"
            )
            ai_recommend = call_claude_for_scenario('limit_up_split', prompt, max_tokens=600)
    except Exception as e:
        logger.warning(f"backtest AI推荐失败: {e}")
        ai_recommend = ''

    result['ai_recommend'] = ai_recommend
    _backtest_cache[cache_key] = {'ts': time.time(), 'payload': result}
    return v1_success_response(data=result)


# 分析结果缓存
_analyze_cache: dict = {}
_ANALYZE_CACHE_TTL_LIVE = 300   # 盘中 5min
_ANALYZE_CACHE_TTL_HIST = 86400  # 历史 24h


@auction_grab_bp.route('/api/v1/auction-grab/screen/analyze', methods=['GET'])
def get_auction_grab_screen_analyze():
    """高级筛选复盘分析：P&L 汇总 + AI 建议（独立接口，异步加载）"""
    from services.auction_screen_service import run_advanced_screen
    from utils.claude_client import call_claude_for_scenario

    dt = request.args.get('dt', _get_last_trading_day())
    period = request.args.get('period', '0')
    trade_date = _format_date(dt)
    date_compact = ag_store.to_compact_date(dt)
    period_int = int(period)
    is_today = _is_today_trading_date(date_compact)

    analyze_key = f'analyze_{date_compact}_{period_int}'
    analyze_ttl = _ANALYZE_CACHE_TTL_LIVE if (is_today and _is_market_hours()) else _ANALYZE_CACHE_TTL_HIST
    cached = _analyze_cache.get(analyze_key)
    if cached and (time.time() - cached['ts']) < analyze_ttl:
        return v1_success_response(data=cached['payload'])

    # 复用 screen 缓存，避免重复拉取
    screen_key = f'screen_{date_compact}_{period_int}'
    screen_ttl = _SCREEN_CACHE_TTL_LIVE if (is_today and _is_market_hours()) else _SCREEN_CACHE_TTL_HIST
    sc = _screen_cache.get(screen_key)
    if sc and (time.time() - sc['ts']) < screen_ttl:
        stocks = sc['payload']['items']
    else:
        try:
            stocks = run_advanced_screen(trade_date, period_int)
        except Exception as e:
            logger.error(f"analyze: 筛选失败: {e}")
            stocks = []

    if not stocks:
        return v1_success_response(data={'ai_analysis': '暂无筛选结果。', 'pnl_summary': None})

    # P&L 汇总
    close_pcts = [s['auction_to_close_pct'] for s in stocks if s.get('auction_to_close_pct') is not None]
    pnl_summary = None
    if close_pcts:
        avg = round(sum(close_pcts) / len(close_pcts), 2)
        wins = [p for p in close_pcts if p > 0]
        pnl_summary = {
            'avg_pct': avg,
            'win_count': len(wins),
            'loss_count': len(close_pcts) - len(wins),
            'total_count': len(close_pcts),
            'win_rate': round(len(wins) / len(close_pcts) * 100, 1),
            'best': round(max(close_pcts), 2),
            'worst': round(min(close_pcts), 2),
        }

    # 情绪周期
    emotion_stage = ''
    try:
        meta = ag_store.load_score_meta(date_compact, period_int)
        emotion_stage = (meta or {}).get('stage', '')
    except Exception:
        pass

    # 构建提示词
    lines = []
    for s in stocks:
        a2c = f"{s['auction_to_close_pct']:+.2f}%" if s.get('auction_to_close_pct') is not None else 'N/A'
        close = f"{s['close_change_pct']:+.2f}%" if s.get('close_change_pct') is not None else 'N/A'
        lines.append(
            f"  {s['name']}({s['code']}) [{s.get('industry','')}] "
            f"竞价{s.get('auction_change_pct',0):+.2f}%→收盘{close} 竞价到收盘{a2c} "
            f"市值{s.get('mktcap',0):.0f}亿 近1年涨停{s.get('limit_up_cnt',0)}次"
        )
    pnl_text = ''
    if pnl_summary:
        pnl_text = (f"等权买入结果：平均{pnl_summary['avg_pct']:+.2f}%，"
                    f"胜率{pnl_summary['win_rate']}%（{pnl_summary['win_count']}盈/{pnl_summary['loss_count']}亏），"
                    f"最好{pnl_summary['best']:+.2f}% 最差{pnl_summary['worst']:+.2f}%")

    prompt = (
        f"日期：{trade_date}，情绪周期：{emotion_stage or '未知'}\n\n"
        f"当日竞价高级筛选（主板/竞价涨幅2-7%/市值30-300亿/近1年涨停>2次）共{len(stocks)}支：\n"
        + '\n'.join(lines) + '\n\n'
        + pnl_text + '\n\n'
        "请给出（300字以内，语言简洁专业）：\n"
        "1. 竞价到收盘整体表现评价\n"
        "2. 表现最突出的1-2支及特征\n"
        "3. 结合情绪周期，明日竞价参与建议\n"
        "4. 值得关注的行业/题材方向"
    )

    ai_analysis = ''
    try:
        ai_analysis = call_claude_for_scenario('limit_up_split', prompt, max_tokens=800)
    except Exception as e:
        logger.warning(f"AI分析失败: {e}")
        ai_analysis = '分析暂时不可用，请稍后重试。'

    payload = {
        'ai_analysis': ai_analysis,
        'pnl_summary': pnl_summary,
        'stocks_count': len(stocks),
        'date': dt,
    }
    _analyze_cache[analyze_key] = {'ts': time.time(), 'payload': payload}
    return v1_success_response(data=payload)
