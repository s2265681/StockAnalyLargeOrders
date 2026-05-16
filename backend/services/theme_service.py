"""
题材标签和涨停数据的数据库存取服务
"""
import logging
from datetime import datetime, timedelta

from utils.db import execute_query, execute_write, execute_many

logger = logging.getLogger(__name__)


# ========== 题材标签 ==========

def get_recent_tags(days=2):
    """获取最近 N 天的题材标签（去重，用于 AI prompt 参考）"""
    today = datetime.now()
    dates = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]
    placeholders = ",".join(["%s"] * len(dates))
    sql = f"""
        SELECT DISTINCT tag_name, reason
        FROM theme_tags
        WHERE date IN ({placeholders})
        ORDER BY tag_name
    """
    return execute_query(sql, dates)


def get_tags_by_date(date):
    """获取指定日期的所有题材标签"""
    sql = """
        SELECT id, date, tag_name, reason, source, created_at, updated_at
        FROM theme_tags
        WHERE date = %s
        ORDER BY tag_name
    """
    return execute_query(sql, (date,))


def upsert_tag(date, tag_name, reason="", source="ai"):
    """插入或更新题材标签"""
    sql = """
        INSERT INTO theme_tags (date, tag_name, reason, source)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE reason = VALUES(reason), source = VALUES(source)
    """
    return execute_write(sql, (date, tag_name, reason, source))


def upsert_tags_batch(date, tags):
    """批量插入/更新题材标签
    tags: [{"tag_name": "机器人", "reason": "...", "source": "ai"}, ...]
    """
    if not tags:
        return 0
    sql = """
        INSERT INTO theme_tags (date, tag_name, reason, source)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE reason = VALUES(reason), source = VALUES(source)
    """
    params = [(date, t["tag_name"], t.get("reason", ""), t.get("source", "ai")) for t in tags]
    return execute_many(sql, params)


def delete_tag(date, tag_name):
    """删除指定日期的题材标签"""
    sql = "DELETE FROM theme_tags WHERE date = %s AND tag_name = %s"
    return execute_write(sql, (date, tag_name))


def rename_tag(date, old_name, new_name):
    """重命名题材标签（同时更新 limit_up_stocks）"""
    execute_write(
        "UPDATE theme_tags SET tag_name = %s WHERE date = %s AND tag_name = %s",
        (new_name, date, old_name),
    )
    execute_write(
        "UPDATE limit_up_stocks SET tag_name = %s WHERE date = %s AND tag_name = %s",
        (new_name, date, old_name),
    )


# ========== 涨停股票 ==========

def get_limit_up_stocks_by_date(date):
    """获取指定日期的所有涨停股票"""
    sql = """
        SELECT * FROM limit_up_stocks
        WHERE date = %s
        ORDER BY boards DESC, seal_amount DESC
    """
    return execute_query(sql, (date,))


def save_limit_up_stocks(date, stocks):
    """批量保存涨停股票数据（upsert）
    stocks: 后端已有的 stock dict 列表
    """
    if not stocks:
        return 0
    sql = """
        INSERT INTO limit_up_stocks
            (date, code, name, boards, tag_name, price, change_pct,
             seal_amount, turnover, seal_ratio, turnover_rate, float_mv,
             first_time, last_time, break_count, industry, zt_stat,
             ths_rank, ths_analyse, ths_analyse_title,
             is_leader, leader_role, leader_reason)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s,
             %s, %s, %s, %s, %s,
             %s, %s, %s, %s, %s,
             %s, %s, %s,
             %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name=VALUES(name), boards=VALUES(boards), tag_name=VALUES(tag_name),
            price=VALUES(price), change_pct=VALUES(change_pct),
            seal_amount=VALUES(seal_amount), turnover=VALUES(turnover),
            seal_ratio=VALUES(seal_ratio), turnover_rate=VALUES(turnover_rate),
            float_mv=VALUES(float_mv), first_time=VALUES(first_time),
            last_time=VALUES(last_time), break_count=VALUES(break_count),
            industry=VALUES(industry), zt_stat=VALUES(zt_stat),
            ths_rank=VALUES(ths_rank), ths_analyse=VALUES(ths_analyse),
            ths_analyse_title=VALUES(ths_analyse_title),
            is_leader=VALUES(is_leader), leader_role=VALUES(leader_role),
            leader_reason=VALUES(leader_reason)
    """
    params = []
    for s in stocks:
        leaders = s.get("theme_leaders") or []
        current_leader = next((l for l in leaders if l.get("code") == s.get("code")), None)
        params.append((
            date,
            s.get("code", ""),
            s.get("name", ""),
            s.get("boards", 1),
            s.get("group_label") or s.get("theme") or "",
            s.get("price", 0),
            s.get("change_pct", 0),
            s.get("seal_amount", 0),
            s.get("turnover", 0),
            s.get("seal_ratio", 0),
            s.get("turnover_rate", 0),
            s.get("float_mv", 0),
            s.get("first_time", ""),
            s.get("last_time", ""),
            s.get("break_count", 0),
            s.get("industry", ""),
            s.get("zt_stat", ""),
            s.get("ths_rank", 0),
            s.get("ths_analyse", ""),
            s.get("ths_analyse_title", ""),
            1 if s.get("is_theme_leader") else 0,
            current_leader.get("role", "") if current_leader else "",
            current_leader.get("reason", "") if current_leader else "",
        ))
    return execute_many(sql, params)


def update_stock_tag(date, code, tag_name):
    """修改单只股票的题材标签"""
    sql = "UPDATE limit_up_stocks SET tag_name = %s WHERE date = %s AND code = %s"
    return execute_write(sql, (tag_name, date, code))


# ========== 综合：保存完整 AI 分组结果 ==========

def save_ai_grouping_result(date, stocks, group_result):
    """保存完整的 AI 分组结果到数据库
    - 更新 theme_tags
    - 更新 limit_up_stocks（含 tag_name、龙头信息）
    """
    labels = group_result.get("labels") or {}
    reasons = group_result.get("reasons") or {}

    # 1. 保存题材标签
    tags = [
        {"tag_name": tag, "reason": reasons.get(tag, ""), "source": "ai"}
        for tag in set(labels.values())
        if tag
    ]
    if tags:
        upsert_tags_batch(date, tags)
        logger.info(f"保存 {len(tags)} 个题材标签到数据库 (date={date})")

    # 2. 保存涨停股票（龙头信息已在 stocks 的 is_theme_leader/theme_leaders 字段里）
    if stocks:
        save_limit_up_stocks(date, stocks)
        logger.info(f"保存 {len(stocks)} 只涨停股票到数据库 (date={date})")


def load_echelon_from_db(date):
    """从数据库加载完整的涨停梯队数据（用于历史查询）
    返回格式与 API 响应一致
    """
    stocks = get_limit_up_stocks_by_date(date)
    if not stocks:
        return None

    tags = get_tags_by_date(date)

    # 从 limit_up_stocks 构建 leaders_by_tag
    leaders_by_tag = {}
    for s in stocks:
        if s.get("is_leader") and s.get("tag_name"):
            tag = s["tag_name"]
            if tag not in leaders_by_tag:
                leaders_by_tag[tag] = []
            leaders_by_tag[tag].append({
                "code": s["code"],
                "name": s["name"],
                "role": s.get("leader_role", ""),
                "reason": s.get("leader_reason", ""),
            })

    # 构建 theme_ranking
    from collections import Counter
    tag_counter = Counter(s["tag_name"] for s in stocks if s.get("tag_name"))
    reason_map = {t["tag_name"]: t["reason"] for t in tags}
    theme_ranking = [
        {
            "theme": tag,
            "count": count,
            "reason": reason_map.get(tag, ""),
            "leaders": leaders_by_tag.get(tag, []),
            "leader": (leaders_by_tag.get(tag, [{}]) or [{}])[0],
        }
        for tag, count in tag_counter.most_common()
    ]

    # 为每只股票补充展示字段
    for s in stocks:
        tag = s.get("tag_name", "")
        s["group_label"] = tag
        s["theme"] = tag
        s["theme_count"] = tag_counter.get(tag, 0)
        s["group_count"] = tag_counter.get(tag, 0)
        s["theme_reason"] = reason_map.get(tag, "")
        tag_leaders = leaders_by_tag.get(tag, [])
        s["theme_leaders"] = tag_leaders
        primary = tag_leaders[0] if tag_leaders else {}
        s["theme_leader_code"] = primary.get("code", "")
        s["theme_leader_name"] = primary.get("name", "")
        s["theme_leader_reason"] = primary.get("reason", "")
        s["is_theme_leader"] = bool(s.get("is_leader"))
        # 格式化金额文本
        s["seal_amount_text"] = _format_amount(s.get("seal_amount", 0))
        s["turnover_text"] = _format_amount(s.get("turnover", 0))
        s["float_mv_text"] = _format_amount(s.get("float_mv", 0))
        # 补充默认字段
        s["ths_hot_tag"] = ""
        s["ths_concept_tags"] = []
        s["ths_popularity"] = ""

    return {
        "stocks": stocks,
        "theme_ranking": theme_ranking,
        "tags": tags,
    }


def _format_amount(val):
    if not val:
        return "--"
    v = float(val)
    if v >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if v >= 1e4:
        return f"{v / 1e4:.0f}万"
    return f"{v:.0f}"
