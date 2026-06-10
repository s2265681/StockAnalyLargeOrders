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
    def _f(v):
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    key_map = {
        "wtje": lambda x: _f(x.get("grab_order_amount")),
        "cjje": lambda x: _f(x.get("grab_turnover")),
        "kpje": lambda x: _f(x.get("open_amount")),
        "zf":   lambda x: _f(x.get("grab_change_pct")),
        "score": lambda x: _f(x.get("recommend_score")),
        "jrzf": lambda x: _f(x.get("close_change_pct") or x.get("today_change_pct")),
        "zrzf": lambda x: _f(x.get("prev_day_change_pct")),
        "crzf": lambda x: _f(x.get("next_day_change_pct")),
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
    """全量替换某日某时段快照，保留已有的富化字段（涨幅/推荐度）"""
    if not items:
        return 0
    try:
        # 先读取已持久化的富化字段，避免重新入库时丢失
        existing = load_enrichment_fields(date_compact, period)

        execute_write(
            f"DELETE FROM {_TABLE} WHERE date = %s AND period = %s",
            (date_compact, int(period)),
        )
        sql = f"""
            INSERT INTO {_TABLE} (
                date, period, code, name, open_amount, grab_change_pct,
                grab_turnover, grab_order_amount, source_time,
                close_change_pct, next_day_change_pct, prev_day_change_pct,
                recommend_stars, recommend_reason, recommend_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = []
        for item in items:
            code = str(item.get("code", "")).zfill(6)
            ex = existing.get(code, {})
            params.append((
                date_compact,
                int(period),
                code,
                item.get("name") or "",
                float(item.get("open_amount") or 0),
                float(item.get("grab_change_pct") or 0),
                float(item.get("grab_turnover") or 0),
                float(item.get("grab_order_amount") or 0),
                str(item.get("source_time") or item.get("date") or ""),
                ex.get("close_change_pct"),
                ex.get("next_day_change_pct"),
                ex.get("prev_day_change_pct"),
                ex.get("recommend_stars"),
                ex.get("recommend_reason"),
                ex.get("recommend_score"),
            ))
        return execute_many(sql, params)
    except Exception as e:
        logger.warning(f"写入竞价抢筹快照失败: {e}")
        return 0


def update_return_fields(date_compact: str, period: int, items: list[dict]) -> int:
    """回写当日/昨日/次日涨幅（有值才更新）"""
    updates = []
    for item in items:
        code = str(item.get("code", "")).zfill(6)
        close_pct = item.get("close_change_pct")
        next_pct = item.get("next_day_change_pct")
        prev_pct = item.get("prev_day_change_pct")
        if close_pct is None and next_pct is None and prev_pct is None:
            continue
        updates.append((close_pct, next_pct, prev_pct, date_compact, int(period), code))

    if not updates:
        return 0

    try:
        sql = f"""
            UPDATE {_TABLE}
            SET close_change_pct = COALESCE(%s, close_change_pct),
                next_day_change_pct = COALESCE(%s, next_day_change_pct),
                prev_day_change_pct = COALESCE(%s, prev_day_change_pct)
            WHERE date = %s AND period = %s AND code = %s
        """
        return execute_many(sql, updates)
    except Exception as e:
        logger.warning(f"更新竞价抢筹涨幅失败: {e}")
        return 0


def items_need_return_enrich(items: list[dict]) -> bool:
    """是否仍有缺失的收盘/昨日/次日涨幅"""
    for item in items:
        if (item.get("close_change_pct") is None
                or item.get("next_day_change_pct") is None
                or item.get("prev_day_change_pct") is None):
            return True
    return False


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_META_TABLE = "auction_grab_score_meta"


def update_score_fields(date_compact: str, period: int, items: list[dict]) -> int:
    """批量回写推荐评分字段（recommend_score 非 None 才更新）"""
    updates = []
    for item in items:
        if item.get("recommend_score") is None:
            continue
        updates.append((
            int(item.get("recommend_stars") or 0),
            str(item.get("recommend_reason") or "")[:100],
            float(item.get("recommend_score") or 0),
            date_compact,
            int(period),
            str(item.get("code", "")).zfill(6),
        ))
    if not updates:
        return 0
    try:
        sql = f"""
            UPDATE {_TABLE}
            SET recommend_stars = %s, recommend_reason = %s, recommend_score = %s
            WHERE date = %s AND period = %s AND code = %s
        """
        return execute_many(sql, updates)
    except Exception as e:
        logger.warning(f"更新竞价抢筹评分失败: {e}")
        return 0


def save_score_meta(date_compact: str, period: int, rec_meta: dict) -> int:
    """保存/更新情绪阶段与推荐提示，标记评分就绪"""
    try:
        sql = f"""
            INSERT INTO {_META_TABLE} (date, period, emotion_stage, recommend_hint, score_ready)
            VALUES (%s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                emotion_stage = VALUES(emotion_stage),
                recommend_hint = VALUES(recommend_hint),
                score_ready = 1
        """
        return execute_write(sql, (
            date_compact,
            int(period),
            str(rec_meta.get("stage") or "")[:20],
            str(rec_meta.get("hint") or "")[:200],
        ))
    except Exception as e:
        logger.warning(f"保存评分元数据失败: {e}")
        return 0


def _row_to_enrichment(row: dict) -> dict:
    """单行快照 -> 前端可合并的富化字段（有值才包含）"""
    out: dict[str, Any] = {}
    close_pct = _float_or_none(row.get("close_change_pct"))
    next_pct = _float_or_none(row.get("next_day_change_pct"))
    prev_pct = _float_or_none(row.get("prev_day_change_pct"))
    if close_pct is not None:
        out["close_change_pct"] = close_pct
    if next_pct is not None:
        out["next_day_change_pct"] = next_pct
    if prev_pct is not None:
        out["prev_day_change_pct"] = prev_pct
    if row.get("recommend_score") is not None:
        out["recommend_stars"] = int(row.get("recommend_stars") or 0)
        out["recommend_reason"] = row.get("recommend_reason") or ""
        out["recommend_score"] = float(row.get("recommend_score") or 0)
    return out


def load_enrichment_fields(date_compact: str, period: int) -> dict:
    """读取涨幅+推荐度，返回 {code: enrichment}"""
    try:
        rows = execute_query(
            f"""
            SELECT code, close_change_pct, next_day_change_pct, prev_day_change_pct,
                   recommend_stars, recommend_reason, recommend_score
            FROM {_TABLE}
            WHERE date = %s AND period = %s
            """,
            (date_compact, int(period)),
        )
    except Exception as e:
        logger.warning(f"读取竞价抢筹富化字段失败: {e}")
        return {}
    result = {}
    for r in rows or []:
        code = str(r.get("code", "")).zfill(6)
        enrichment = _row_to_enrichment(r)
        if enrichment:
            result[code] = enrichment
    return result


def load_score_fields(date_compact: str, period: int) -> dict:
    """读取个股评分字段，返回 {code: {recommend_stars, recommend_reason, recommend_score}}"""
    all_fields = load_enrichment_fields(date_compact, period)
    return {
        code: {
            "recommend_stars": fields.get("recommend_stars", 0),
            "recommend_reason": fields.get("recommend_reason", ""),
            "recommend_score": fields.get("recommend_score", 0),
        }
        for code, fields in all_fields.items()
        if fields.get("recommend_score") is not None
    }


def load_score_meta(date_compact: str, period: int) -> dict:
    """读取情绪阶段与推荐提示"""
    try:
        rows = execute_query(
            f"SELECT emotion_stage, recommend_hint, score_ready FROM {_META_TABLE} "
            f"WHERE date = %s AND period = %s LIMIT 1",
            (date_compact, int(period)),
        )
    except Exception as e:
        logger.warning(f"读取评分元数据失败: {e}")
        return {}
    if not rows:
        return {}
    r = rows[0]
    return {
        "stage": r.get("emotion_stage") or "",
        "hint": r.get("recommend_hint") or "",
        "ready": bool(r.get("score_ready")),
    }


def scores_exist(date_compact: str, period: int) -> bool:
    """检查指定日期/时段是否已有评分数据"""
    try:
        rows = execute_query(
            f"SELECT 1 FROM {_META_TABLE} WHERE date = %s AND period = %s AND score_ready = 1 LIMIT 1",
            (date_compact, int(period)),
        )
        return bool(rows)
    except Exception as e:
        logger.warning(f"查询评分就绪状态失败: {e}")
        return False


# ── stock_meta：行业/题材缓存 ──────────────────────────────────────

_STOCK_META_TABLE = "stock_meta"


def load_stock_meta(codes: list[str]) -> dict[str, dict]:
    """批量读取 stock_meta，返回 {code: {industry, concepts}}"""
    if not codes:
        return {}
    codes_padded = [str(c).zfill(6) for c in codes]
    placeholders = ",".join(["%s"] * len(codes_padded))
    try:
        rows = execute_query(
            f"SELECT code, industry, concepts FROM {_STOCK_META_TABLE} WHERE code IN ({placeholders})",
            codes_padded,
        )
    except Exception as e:
        logger.warning(f"读取 stock_meta 失败: {e}")
        return {}
    return {
        r["code"]: {"industry": r.get("industry") or "", "concepts": r.get("concepts") or ""}
        for r in (rows or [])
    }


def upsert_stock_meta(code: str, industry: str = "", concepts: str = "", name: str = "") -> None:
    try:
        sql = f"""
            INSERT INTO {_STOCK_META_TABLE} (code, name, industry, concepts)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name       = IF(%s != '', VALUES(name), name),
                industry   = IF(%s != '', VALUES(industry), industry),
                concepts   = IF(%s != '', VALUES(concepts), concepts),
                updated_at = CURRENT_TIMESTAMP
        """
        execute_write(sql, (code, name, industry, concepts, name, industry, concepts))
    except Exception as e:
        logger.warning(f"保存 stock_meta 失败 code={code}: {e}")


def populate_stock_meta_from_pool(codes: list[str]) -> None:
    """从涨停池（limit_up_stocks）查最近一次 industry/tag_name，写入 stock_meta"""
    if not codes:
        return
    codes_padded = [str(c).zfill(6) for c in codes]
    placeholders = ",".join(["%s"] * len(codes_padded))
    try:
        rows = execute_query(
            f"""
            SELECT l.code, l.name, l.industry, l.tag_name
            FROM limit_up_stocks l
            INNER JOIN (
                SELECT code, MAX(date) AS max_date
                FROM limit_up_stocks
                WHERE code IN ({placeholders})
                GROUP BY code
            ) recent ON l.code = recent.code AND l.date = recent.max_date
            """,
            codes_padded,
        )
    except Exception as e:
        logger.warning(f"从涨停池查 stock_meta 失败: {e}")
        return
    for r in (rows or []):
        code = str(r.get("code", "")).zfill(6)
        upsert_stock_meta(
            code,
            industry=(r.get("industry") or "").strip(),
            concepts=(r.get("tag_name") or "").strip(),
            name=(r.get("name") or "").strip(),
        )


def merge_stock_meta(items: list[dict]) -> None:
    """就地将行业/题材合并到 items（stock_meta 缓存中无记录则为空字符串）"""
    if not items:
        return
    codes = [item.get("code", "") for item in items]
    meta = load_stock_meta(codes)
    for item in items:
        m = meta.get(item.get("code", ""), {})
        item.setdefault("industry", m.get("industry", ""))
        item.setdefault("concepts", m.get("concepts", ""))
