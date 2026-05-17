"""
竞价抢筹数据持久化：日快照入库，供接口缓存与历史回测。
"""
import logging
from typing import Any

from utils.db import execute_many, execute_query, execute_write

logger = logging.getLogger(__name__)

_TABLE = "auction_grab_stocks"


def to_compact_date(dt: str) -> str:
    """YYYY-MM-DD 或 YYYYMMDD -> YYYYMMDD"""
    if not dt:
        return ""
    return dt.replace("-", "")[:8]


def to_dash_date(dt_compact: str) -> str:
    if len(dt_compact) == 8:
        return f"{dt_compact[:4]}-{dt_compact[4:6]}-{dt_compact[6:8]}"
    return dt_compact


def items_from_raw_api(raw_list: list[dict], trade_date_dash: str) -> list[dict]:
    """stockapi 原始行 -> 标准 item"""
    items = []
    for r in raw_list or []:
        items.append(
            {
                "code": str(r.get("code", "")).zfill(6),
                "name": r.get("name", "") or "",
                "open_amount": round(float(r.get("openAmt") or 0) / 10000, 2),
                "grab_change_pct": float(r.get("qczf") or 0),
                "grab_turnover": round(float(r.get("qccje") or 0) / 10000, 2),
                "grab_order_amount": round(float(r.get("qcwtje") or 0) / 10000, 2),
                "date": r.get("time") or trade_date_dash,
                "source_time": str(r.get("time") or ""),
            }
        )
    return items


def sort_items(items: list[dict], sort_by: str) -> list[dict]:
    key_map = {
        "wtje": lambda x: float(x.get("grab_order_amount") or 0),
        "cjje": lambda x: float(x.get("grab_turnover") or 0),
        "kpje": lambda x: float(x.get("open_amount") or 0),
        "zf": lambda x: float(x.get("grab_change_pct") or 0),
    }
    key_fn = key_map.get(sort_by, key_map["wtje"])
    return sorted(items, key=key_fn, reverse=True)


def snapshot_exists(date_compact: str, period: int) -> bool:
    try:
        rows = execute_query(
            f"SELECT 1 FROM {_TABLE} WHERE date = %s AND period = %s LIMIT 1",
            (date_compact, int(period)),
        )
        return bool(rows)
    except Exception as e:
        logger.warning(f"查询竞价抢筹快照失败: {e}")
        return False


def load_items(date_compact: str, period: int) -> list[dict] | None:
    """从库读取日快照；无数据返回 None"""
    try:
        rows = execute_query(
            f"""
            SELECT code, name, open_amount, grab_change_pct, grab_turnover,
                   grab_order_amount, close_change_pct, next_day_change_pct,
                   source_time
            FROM {_TABLE}
            WHERE date = %s AND period = %s
            ORDER BY grab_order_amount DESC
            """,
            (date_compact, int(period)),
        )
    except Exception as e:
        logger.warning(f"读取竞价抢筹快照失败: {e}")
        return None

    if not rows:
        return None

    trade_date_dash = to_dash_date(date_compact)
    items = []
    for r in rows:
        items.append(
            {
                "code": str(r.get("code", "")).zfill(6),
                "name": r.get("name") or "",
                "open_amount": float(r.get("open_amount") or 0),
                "grab_change_pct": float(r.get("grab_change_pct") or 0),
                "grab_turnover": float(r.get("grab_turnover") or 0),
                "grab_order_amount": float(r.get("grab_order_amount") or 0),
                "close_change_pct": _float_or_none(r.get("close_change_pct")),
                "next_day_change_pct": _float_or_none(r.get("next_day_change_pct")),
                "date": trade_date_dash,
                "source_time": r.get("source_time") or "",
            }
        )
    return items


def replace_snapshot(date_compact: str, period: int, items: list[dict]) -> int:
    """全量替换某日某时段快照"""
    if not items:
        return 0
    try:
        execute_write(
            f"DELETE FROM {_TABLE} WHERE date = %s AND period = %s",
            (date_compact, int(period)),
        )
        sql = f"""
            INSERT INTO {_TABLE} (
                date, period, code, name, open_amount, grab_change_pct,
                grab_turnover, grab_order_amount, source_time
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = []
        for item in items:
            params.append(
                (
                    date_compact,
                    int(period),
                    str(item.get("code", "")).zfill(6),
                    item.get("name") or "",
                    float(item.get("open_amount") or 0),
                    float(item.get("grab_change_pct") or 0),
                    float(item.get("grab_turnover") or 0),
                    float(item.get("grab_order_amount") or 0),
                    str(item.get("source_time") or item.get("date") or ""),
                )
            )
        return execute_many(sql, params)
    except Exception as e:
        logger.warning(f"写入竞价抢筹快照失败: {e}")
        return 0


def update_return_fields(date_compact: str, period: int, items: list[dict]) -> int:
    """回写当日/次日涨幅（有值才更新）"""
    updates = []
    for item in items:
        code = str(item.get("code", "")).zfill(6)
        close_pct = item.get("close_change_pct")
        next_pct = item.get("next_day_change_pct")
        if close_pct is None and next_pct is None:
            continue
        updates.append((close_pct, next_pct, date_compact, int(period), code))

    if not updates:
        return 0

    try:
        sql = f"""
            UPDATE {_TABLE}
            SET close_change_pct = COALESCE(%s, close_change_pct),
                next_day_change_pct = COALESCE(%s, next_day_change_pct)
            WHERE date = %s AND period = %s AND code = %s
        """
        return execute_many(sql, updates)
    except Exception as e:
        logger.warning(f"更新竞价抢筹涨幅失败: {e}")
        return 0


def items_need_return_enrich(items: list[dict]) -> bool:
    """是否仍有缺失的收盘/次日涨幅"""
    for item in items:
        if item.get("close_change_pct") is None or item.get("next_day_change_pct") is None:
            return True
    return False


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
