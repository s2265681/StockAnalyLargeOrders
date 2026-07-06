"""
板块抢筹 API
数据来源: stockapi.com.cn gnDataAi / deepSeekGnCodeHis / gnDataCodeAi
"""
import json
import logging
import subprocess
import time
from datetime import datetime, timedelta

from flask import Blueprint, request

from services import sector_grab_service as sg_store
from utils.date_utils import get_valid_trading_date
from utils.response import v1_success_response, v1_error_response

logger = logging.getLogger(__name__)

sector_grab_bp = Blueprint("sector_grab", __name__)

_STOCKAPI_REFERER = "http://user.stockapi.com.cn/sector"
_STOCKAPI_HEADERS = [
    "-H", "Accept: */*",
    "-H", f"Referer: {_STOCKAPI_REFERER}",
    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "-H", "token: null",
]

_SECTORS_CACHE: dict = {}
_STOCKS_CACHE: dict = {}


def _get_last_trading_day() -> str:
    d = datetime.now()
    dow = d.weekday()
    if dow == 5:
        d -= timedelta(days=1)
    elif dow == 6:
        d -= timedelta(days=2)
    return d.strftime("%Y%m%d")


def _format_date(dt_str: str) -> str:
    if len(dt_str) == 8:
        return f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
    return dt_str


def _is_today(date_compact: str) -> bool:
    today = get_valid_trading_date().replace("-", "")
    return date_compact == today


def _is_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 + 25) <= t <= (15 * 60 + 5)


def _refresh_interval_seconds() -> int | None:
    """09:30-10:00 每5分钟；10:00-15:00 每30分钟"""
    now = datetime.now()
    if now.weekday() >= 5:
        return None
    t = now.hour * 60 + now.minute
    if t < 9 * 60 + 30 or t > 15 * 60:
        return None
    if t < 10 * 60:
        return 300
    return 1800


def _cache_ttl(is_today: bool) -> int:
    interval = _refresh_interval_seconds()
    if is_today and interval:
        return interval
    if is_today:
        return 120
    return 86400


def _curl_json(url: str, timeout: int = 15) -> dict | None:
    cmd = ["curl", "-s", "-k", "--max-time", str(timeout), *_STOCKAPI_HEADERS, url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)
    except Exception as e:
        logger.warning("stockapi 请求失败 %s: %s", url, e)
        return None


def _parse_sectors_payload(body: dict | list | None) -> list[dict]:
    if not body:
        return []
    if isinstance(body, list):
        raw_list = body
    elif isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            raw_list = data.get("hotbk") or data.get("list") or data.get("sectors") or []
        else:
            raw_list = body.get("hotbk") or []
    else:
        return []

    sectors = []
    for i, raw in enumerate(raw_list):
        item = sg_store.normalize_sector(raw, i)
        if item:
            sectors.append(item)
    return sectors


def _fetch_sectors_live(trade_date_compact: str) -> list[dict]:
    """优先 deepSeekGnCodeHis，空则回退 gnDataAi"""
    hist_url = (
        f"http://user.stockapi.com.cn/v1/deepSeekGnCodeHis?tradeDate={trade_date_compact}"
    )
    resp = _curl_json(hist_url)
    if resp and resp.get("code") == 20000:
        sectors = _parse_sectors_payload(resp.get("data"))
        if sectors:
            return sectors

    live_resp = _curl_json("http://user.stockapi.com.cn/v1/gnDataAi")
    if live_resp and live_resp.get("code") == 20000:
        return _parse_sectors_payload(live_resp.get("data"))
    return []


def _fetch_stocks_live(gn_code: str) -> list[dict]:
    url = f"http://user.stockapi.com.cn/v1/gnDataCodeAi?gnCode={gn_code}"
    resp = _curl_json(url)
    if not resp or resp.get("code") != 20000:
        return []
    data = resp.get("data") or {}
    stocks_raw = data.get("stocks") if isinstance(data, dict) else []
    from services.auction_unmask import unmask_stockapi_rows

    unmasked = unmask_stockapi_rows(stocks_raw or [])
    stocks = []
    for raw in unmasked:
        item = sg_store.normalize_stock(raw, gn_code)
        if item:
            stocks.append(item)
    if not stocks and stocks_raw:
        logger.warning(
            "板块个股去脱敏后为空 gnCode=%s raw=%s unmasked=%s",
            gn_code, len(stocks_raw), len(unmasked),
        )
    return stocks


def _get_cached_sectors(date_compact: str, is_today: bool) -> tuple[list[dict] | None, str | None]:
    entry = _SECTORS_CACHE.get(date_compact)
    ttl = _cache_ttl(is_today)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["items"], entry.get("source")
    return None, None


def _set_cached_sectors(date_compact: str, items: list[dict], source: str) -> None:
    _SECTORS_CACHE[date_compact] = {"ts": time.time(), "items": items, "source": source}


def _get_cached_stocks(date_compact: str, gn_code: str, is_today: bool) -> list[dict] | None:
    key = f"{date_compact}_{gn_code}"
    entry = _STOCKS_CACHE.get(key)
    ttl = _cache_ttl(is_today)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["items"]
    return None


def _set_cached_stocks(date_compact: str, gn_code: str, items: list[dict]) -> None:
    key = f"{date_compact}_{gn_code}"
    _STOCKS_CACHE[key] = {"ts": time.time(), "items": items}


def fetch_and_cache_sectors(trade_date_dash: str) -> list[dict]:
    """供定时任务：拉取板块列表并入库"""
    date_compact = sg_store.to_compact_date(trade_date_dash)
    sectors = _fetch_sectors_live(date_compact)
    if sectors:
        sg_store.replace_sectors(date_compact, sectors)
        _set_cached_sectors(date_compact, sectors, "api")
    return sectors


def fetch_and_cache_stocks(trade_date_dash: str, gn_code: str) -> list[dict]:
    date_compact = sg_store.to_compact_date(trade_date_dash)
    stocks = _fetch_stocks_live(gn_code)
    if stocks:
        sg_store.replace_stocks(date_compact, gn_code, stocks)
        _set_cached_stocks(date_compact, gn_code, stocks)
    return stocks


@sector_grab_bp.route("/api/v1/sector-grab/sectors", methods=["GET"])
def get_sector_grab_sectors():
    """
    板块列表
    参数: dt=YYYYMMDD，默认当天
    """
    dt = request.args.get("dt", _get_last_trading_day())
    date_compact = sg_store.to_compact_date(dt)
    trade_date = _format_date(dt)
    is_today = _is_today(date_compact)
    force = request.args.get("force") == "1"

    items, source = _get_cached_sectors(date_compact, is_today)
    if items is None or force:
        db_items = None if force else sg_store.load_sectors(date_compact)
        if db_items and not (is_today and _is_market_hours()):
            items = db_items
            source = "db"
            _set_cached_sectors(date_compact, items, source)
        else:
            live = _fetch_sectors_live(date_compact)
            if live:
                items = live
                source = "api"
                sg_store.replace_sectors(date_compact, items)
                _set_cached_sectors(date_compact, items, source)
            elif db_items:
                items = db_items
                source = "db_fallback"
                _set_cached_sectors(date_compact, items, source)
            else:
                return v1_error_response("板块数据暂不可用，请稍后重试")

    interval = _refresh_interval_seconds() if is_today else None
    return v1_success_response(data={
        "sectors": items,
        "total": len(items),
        "date": dt,
        "source": source,
        "live_refresh": bool(is_today and interval),
        "refresh_interval_sec": interval,
    })


@sector_grab_bp.route("/api/v1/sector-grab/stocks", methods=["GET"])
def get_sector_grab_stocks():
    """
    板块内个股
    参数: gnCode=801807, dt=YYYYMMDD
    """
    gn_code = request.args.get("gnCode") or request.args.get("gn_code")
    if not gn_code:
        return v1_error_response("请提供 gnCode 参数")

    dt = request.args.get("dt", _get_last_trading_day())
    date_compact = sg_store.to_compact_date(dt)
    is_today = _is_today(date_compact)
    force = request.args.get("force") == "1"

    items = None if force else _get_cached_stocks(date_compact, gn_code, is_today)
    source = "cache"
    if items is None:
        db_items = None if force else sg_store.load_stocks(date_compact, gn_code)
        if db_items and not (is_today and _is_market_hours()):
            items = db_items
            source = "db"
        else:
            live = _fetch_stocks_live(gn_code)
            if live:
                items = live
                source = "api"
                sg_store.replace_stocks(date_compact, gn_code, items)
                _set_cached_stocks(date_compact, gn_code, items)
            elif db_items:
                items = db_items
                source = "db_fallback"
                _set_cached_stocks(date_compact, gn_code, items)
            else:
                return v1_error_response(
                    "个股数据暂不可用（接口返回脱敏数据且反查失败，请稍后重试）"
                )

    sector_name = ""
    for s in (_SECTORS_CACHE.get(date_compact) or {}).get("items") or []:
        if s.get("gn_code") == gn_code:
            sector_name = s.get("name") or ""
            break
    if not sector_name:
        db_sectors = sg_store.load_sectors(date_compact) or []
        for s in db_sectors:
            if s.get("gn_code") == gn_code:
                sector_name = s.get("name") or ""
                break

    return v1_success_response(data={
        "stocks": items,
        "total": len(items),
        "gn_code": gn_code,
        "sector_name": sector_name,
        "date": dt,
        "source": source,
    })
