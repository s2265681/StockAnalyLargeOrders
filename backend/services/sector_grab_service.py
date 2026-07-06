"""
板块抢筹数据持久化：板块列表与板块内个股日快照。
"""
import json
import logging
from typing import Any

from utils.db import execute_many, execute_query, execute_write
from services.auction_unmask import is_valid_stock_code

logger = logging.getLogger(__name__)

_SECTORS_TABLE = "sector_grab_sectors"
_STOCKS_TABLE = "sector_grab_stocks"


def to_compact_date(dt: str) -> str:
    if not dt:
        return ""
    return dt.replace("-", "")[:8]


def to_dash_date(dt_compact: str) -> str:
    if len(dt_compact) == 8:
        return f"{dt_compact[:4]}-{dt_compact[4:6]}-{dt_compact[6:8]}"
    return dt_compact


def normalize_sector(raw: dict, idx: int = 0) -> dict | None:
    """统一板块字段（gnDataAi hotbk / deepSeekGnCodeHis）"""
    gn_code = str(
        raw.get("code") or raw.get("gnCode") or raw.get("gn_code") or raw.get("PlateID") or ""
    ).strip()
    name = str(raw.get("name") or raw.get("gnName") or raw.get("bkName") or "").strip()
    if not gn_code or not name:
        return None
    return {
        "gn_code": gn_code,
        "name": name,
        "strength": _int(raw.get("qiandu") or raw.get("strength") or raw.get("qd") or 0),
        "strength_change": _int(
            raw.get("qianduChange") or raw.get("strength_change") or raw.get("qdChange") or 0
        ),
        "change_pct": _float(raw.get("zf") or raw.get("change_pct") or 0),
        "limit_up_count": _int(raw.get("ztjs") or raw.get("limit_up_count") or raw.get("zt") or 0),
        "is_hot": 1 if raw.get("hot") or raw.get("is_hot") else 0,
        "sort_order": idx,
    }


def normalize_stock(raw: dict, gn_code: str) -> dict | None:
    code = str(raw.get("code", "")).zfill(6)
    if not is_valid_stock_code(code):
        return None
    return {
        "gn_code": gn_code,
        "code": code,
        "name": str(raw.get("name") or "").strip(),
        "change_pct": _float(raw.get("zf") or 0),
        "turnover_pct": _float(raw.get("hsl") or 0),
        "speed": _float(raw.get("zls") or 0),
        "leader_rank": str(raw.get("lz") or "").strip(),
        "main_force": str(raw.get("zl") or "").strip(),
        "board_label": str(raw.get("lb") or "").strip(),
        "sectors": str(raw.get("bk") or "").strip(),
        "popularity": _int(raw.get("rqRank") or 0),
        "price": _float(raw.get("price") or 0),
        "score": _float(raw.get("score") or 0),
        "raw_json": raw,
    }


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _float(v) -> float:
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return 0.0


def load_sectors(date_compact: str) -> list[dict] | None:
    try:
        rows = execute_query(
            f"""
            SELECT gn_code, name, strength, strength_change, change_pct,
                   limit_up_count, is_hot, sort_order
            FROM {_SECTORS_TABLE}
            WHERE date = %s
            ORDER BY sort_order ASC, strength DESC
            """,
            (date_compact,),
        )
    except Exception as e:
        logger.warning("读取板块抢筹板块快照失败: %s", e)
        return None
    if not rows:
        return None
    return [
        {
            "gn_code": r["gn_code"],
            "name": r["name"],
            "strength": int(r.get("strength") or 0),
            "strength_change": int(r.get("strength_change") or 0),
            "change_pct": float(r.get("change_pct") or 0),
            "limit_up_count": int(r.get("limit_up_count") or 0),
            "is_hot": bool(r.get("is_hot")),
            "sort_order": int(r.get("sort_order") or 0),
        }
        for r in rows
    ]


def load_stocks(date_compact: str, gn_code: str) -> list[dict] | None:
    try:
        rows = execute_query(
            f"""
            SELECT code, name, change_pct, turnover_pct, speed, leader_rank,
                   main_force, board_label, sectors, popularity, price, score
            FROM {_STOCKS_TABLE}
            WHERE date = %s AND gn_code = %s
            ORDER BY popularity ASC, score DESC
            """,
            (date_compact, gn_code),
        )
    except Exception as e:
        logger.warning("读取板块抢筹个股快照失败: %s", e)
        return None
    if not rows:
        return None
    return [
        {
            "code": str(r["code"]).zfill(6),
            "name": r.get("name") or "",
            "change_pct": float(r.get("change_pct") or 0),
            "turnover_pct": float(r.get("turnover_pct") or 0),
            "speed": float(r.get("speed") or 0),
            "leader_rank": r.get("leader_rank") or "",
            "main_force": r.get("main_force") or "",
            "board_label": r.get("board_label") or "",
            "sectors": r.get("sectors") or "",
            "popularity": int(r.get("popularity") or 0),
            "price": float(r.get("price") or 0),
            "score": float(r.get("score") or 0),
        }
        for r in rows
    ]


def replace_sectors(date_compact: str, sectors: list[dict]) -> None:
    if not sectors:
        return
    try:
        execute_write(f"DELETE FROM {_SECTORS_TABLE} WHERE date = %s", (date_compact,))
        rows = [
            (
                date_compact,
                s["gn_code"],
                s["name"],
                s["strength"],
                s["strength_change"],
                s["change_pct"],
                s["limit_up_count"],
                1 if s.get("is_hot") else 0,
                s.get("sort_order", i),
            )
            for i, s in enumerate(sectors)
        ]
        execute_many(
            f"""
            INSERT INTO {_SECTORS_TABLE}
              (date, gn_code, name, strength, strength_change, change_pct,
               limit_up_count, is_hot, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    except Exception as e:
        logger.warning("写入板块抢筹板块快照失败: %s", e)


def replace_stocks(date_compact: str, gn_code: str, stocks: list[dict]) -> None:
    if not stocks:
        return
    try:
        execute_write(
            f"DELETE FROM {_STOCKS_TABLE} WHERE date = %s AND gn_code = %s",
            (date_compact, gn_code),
        )
        rows = [
            (
                date_compact,
                gn_code,
                s["code"],
                s["name"],
                s["change_pct"],
                s["turnover_pct"],
                s["speed"],
                s["leader_rank"],
                s["main_force"],
                s["board_label"],
                s["sectors"],
                s["popularity"],
                s["price"],
                s["score"],
                json.dumps(s.get("raw_json") or {}, ensure_ascii=False),
            )
            for s in stocks
        ]
        execute_many(
            f"""
            INSERT INTO {_STOCKS_TABLE}
              (date, gn_code, code, name, change_pct, turnover_pct, speed,
               leader_rank, main_force, board_label, sectors, popularity,
               price, score, raw_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    except Exception as e:
        logger.warning("写入板块抢筹个股快照失败: %s", e)
