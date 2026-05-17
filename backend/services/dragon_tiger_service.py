# backend/services/dragon_tiger_service.py
"""
龙虎榜数据库存取服务
"""
import logging
from utils.db import execute_query, execute_write, execute_many

logger = logging.getLogger(__name__)


SEAT_NOISE_WORDS = [
    "股份有限公司",
    "有限责任公司",
    "证券股份有限公司",
    "证券有限责任公司",
    "证券有限责任公司",
    "证券营业部",
    "营业部",
    "证券",
    "股份",
    "有限",
    "责任公司",
    "分公司",
]


def _normalize_seat_text(text: str) -> str:
    """营业部名称规范化：去公司后缀、空白和常见符号，增强模糊匹配鲁棒性。"""
    s = (text or "").strip()
    if not s:
        return ""
    for w in SEAT_NOISE_WORDS:
        s = s.replace(w, "")
    for ch in (" ", "\t", "\n", "（", "）", "(", ")", "-", "_", "·", "。", ",", "，", ".", "/"):
        s = s.replace(ch, "")
    return s


def _char_overlap_ratio(keyword: str, target: str) -> float:
    """字符重合率（以 keyword 为分母）。"""
    if not keyword:
        return 0.0
    kw_set = set(keyword)
    if not kw_set:
        return 0.0
    return len(kw_set & set(target)) / len(kw_set)


def get_seat_aliases() -> list:
    """
    获取席位关键词映射（营业部关键词 -> 游资标签）。
    按关键词长度降序，保证更精确关键词优先匹配。
    """
    try:
        rows = execute_query(
            """
            SELECT id, keyword, trader_tag, priority
            FROM dragon_tiger_seat_aliases
            WHERE is_active = 1
            ORDER BY CHAR_LENGTH(keyword) DESC, priority DESC, id ASC
            """
        )
        return rows or []
    except Exception as e:
        logger.warning(f"读取席位映射失败（可能未建表）: {e}")
        return []


def match_seat_alias(seat_name: str, aliases: list) -> dict:
    """
    根据席位名称匹配游资标签，返回：
    {"alias_id": int, "trader_tag": str} 或 {"alias_id": None, "trader_tag": ""}
    """
    name = (seat_name or "").strip()
    if not name or not aliases:
        return {"alias_id": None, "trader_tag": ""}
    name_norm = _normalize_seat_text(name)

    best = None
    best_score = -1
    for a in aliases:
        kw = (a.get("keyword") or "").strip()
        if not kw:
            continue
        priority = int(a.get("priority") or 0)
        kw_norm = _normalize_seat_text(kw)

        score = -1
        # 1) 原文精确包含（最高优先）
        if kw in name:
            score = 5000 + priority
        # 2) 规范化后包含（解决“有限公司/营业部”写法不一）
        elif kw_norm and kw_norm in name_norm:
            score = 4000 + priority + len(kw_norm)
        # 3) 反向包含（库里关键词更完整，实盘名称更短）
        elif kw_norm and name_norm and name_norm in kw_norm and len(name_norm) >= 4:
            score = 3500 + priority + len(name_norm)
        else:
            # 4) 前后几个字模糊：关键词前缀 + 后缀同时命中
            if kw_norm:
                head_len = min(4, len(kw_norm))
                tail_len = min(4, len(kw_norm))
                head = kw_norm[:head_len]
                tail = kw_norm[-tail_len:]
                if head and tail and head in name_norm and tail in name_norm:
                    score = 2500 + priority + len(kw_norm)
                else:
                    # 5) 字符重合兜底（避免漏掉“少字/错字”）
                    overlap = _char_overlap_ratio(kw_norm, name_norm)
                    if overlap >= 0.72 and len(kw_norm) >= 4:
                        score = 1800 + priority + int(overlap * 100)

        if score > best_score:
            best_score = score
            best = a

    # 阈值保护：避免太弱的模糊匹配误命中（1800 对应最弱兜底命中）
    if best and best_score >= 1800:
        return {
            "alias_id": best.get("id"),
            "trader_tag": (best.get("trader_tag") or "").strip(),
        }
    return {"alias_id": None, "trader_tag": ""}


def _dedupe_seats(seats: list) -> list:
    """
    对席位明细做稳定去重，避免同一席位重复展示。
    以代码/方向/席位名称/买卖净额作为唯一键，保留首次出现记录。
    """
    if not seats:
        return []

    unique = []
    seen = set()
    for s in seats:
        key = (
            s.get("code", ""),
            s.get("direction", ""),
            (s.get("seat_name") or "").strip(),
            float(s.get("buy_amount") or 0),
            float(s.get("sell_amount") or 0),
            float(s.get("net_amount") or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    return unique


def get_daily_stocks(date: str) -> list:
    """获取指定日期的龙虎榜股票列表（含席位数据）"""
    stocks = execute_query(
        "SELECT * FROM dragon_tiger_daily WHERE date = %s ORDER BY ABS(net_buy) DESC",
        (date,),
    )
    if not stocks:
        return []
    codes = [s["code"] for s in stocks]
    placeholders = ",".join(["%s"] * len(codes))
    seats = execute_query(
        f"SELECT * FROM dragon_tiger_seats WHERE date = %s AND code IN ({placeholders})"
        f" ORDER BY direction, rank_no",
        [date] + codes,
    )
    seats = _dedupe_seats(seats)
    aliases = get_seat_aliases()
    seat_map = {}
    for seat in seats:
        matched = match_seat_alias(seat.get("seat_name", ""), aliases)
        seat["alias_id"] = matched["alias_id"]
        seat["trader_tag"] = matched["trader_tag"]
        key = (seat["code"], seat["direction"])
        seat_map.setdefault(key, []).append(seat)
    for stock in stocks:
        code = stock["code"]
        stock["buy_seats"] = seat_map.get((code, "buy"), [])
        stock["sell_seats"] = seat_map.get((code, "sell"), [])
    return stocks


def save_daily_stocks(date: str, stocks: list) -> None:
    """批量写入龙虎榜股票列表（upsert）"""
    if not stocks:
        return
    sql = """
        INSERT INTO dragon_tiger_daily
          (date, code, name, change_pct, close_price, net_buy, buy_amount, sell_amount,
           lhb_amount, total_amount, reason, interpret)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          name=VALUES(name), change_pct=VALUES(change_pct),
          close_price=VALUES(close_price), net_buy=VALUES(net_buy),
          buy_amount=VALUES(buy_amount), sell_amount=VALUES(sell_amount),
          lhb_amount=VALUES(lhb_amount), total_amount=VALUES(total_amount),
          reason=VALUES(reason), interpret=VALUES(interpret)
    """
    params = [
        (date, s.get("code", ""), s.get("name", ""),
         s.get("change_pct", 0), s.get("close_price", 0),
         s.get("net_buy", 0), s.get("buy_amount", 0), s.get("sell_amount", 0),
         s.get("lhb_amount", 0), s.get("total_amount", 0),
         s.get("reason", ""), s.get("interpret", ""))
        for s in stocks
    ]
    execute_many(sql, params)


def save_seats(date: str, seats: list) -> None:
    """批量写入席位明细（先删后插，保证幂等）"""
    if not seats:
        return
    seats = _dedupe_seats(seats)
    if not seats:
        return
    codes = list({s["code"] for s in seats})
    if not codes:
        return
    code_ph = ",".join(["%s"] * len(codes))
    execute_write(
        f"DELETE FROM dragon_tiger_seats WHERE date=%s AND code IN ({code_ph})",
        [date] + codes,
    )
    sql = """
        INSERT INTO dragon_tiger_seats
          (date, code, direction, rank_no, seat_name, buy_amount, sell_amount,
           net_amount, is_hot_money)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    params = [
        (date, s.get("code", ""), s.get("direction", "buy"), s.get("rank_no", 0), s.get("seat_name", ""),
         s.get("buy_amount", 0), s.get("sell_amount", 0), s.get("net_amount", 0), s.get("is_hot_money", 0))
        for s in seats
    ]
    execute_many(sql, params)


def get_ai_analysis(date: str, code: str) -> str | None:
    """获取已有AI分析，无则返回None"""
    rows = execute_query(
        "SELECT analysis FROM dragon_tiger_ai WHERE date=%s AND code=%s",
        (date, code),
    )
    return rows[0]["analysis"] if rows else None


def save_ai_analysis(date: str, code: str, analysis: str) -> None:
    """保存AI分析结果（upsert）"""
    execute_write(
        """
        INSERT INTO dragon_tiger_ai (date, code, analysis)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE analysis=VALUES(analysis), updated_at=CURRENT_TIMESTAMP
        """,
        (date, code, analysis),
    )

