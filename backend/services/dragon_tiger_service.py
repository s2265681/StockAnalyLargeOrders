# backend/services/dragon_tiger_service.py
"""
龙虎榜数据库存取服务
"""
import logging
from utils.db import execute_query, execute_write, execute_many

logger = logging.getLogger(__name__)


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
    seat_map = {}
    for seat in seats:
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
