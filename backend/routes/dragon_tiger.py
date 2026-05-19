# backend/routes/dragon_tiger.py
"""
龙虎榜接口模块
- GET  /api/v1/dragon-tiger?date=YYYYMMDD              获取龙虎榜列表（含席位）
- GET  /api/v1/dragon-tiger/ai-analysis-cache?date&code  只读查询已入库 AI 解读
- POST /api/v1/dragon-tiger/ai-analysis                  兼容旧客户端，仅返回缓存
"""
import json
import logging
import os
from datetime import datetime

from flask import Blueprint, request

from utils.response import v1_success_response, v1_error_response
from services.dragon_tiger_service import (
    get_daily_stocks,
    save_daily_stocks,
    save_seats,
    get_ai_analysis,
    save_ai_analysis,
    get_seat_aliases,
    match_seat_alias,
)
from services.theme_service import get_limit_up_stocks_by_date, get_tags_by_date

logger = logging.getLogger(__name__)

dragon_tiger_bp = Blueprint("dragon_tiger", __name__)

from config.ai_prompts import build_dragon_tiger_prompt
from utils.claude_client import call_claude_for_scenario

# 游资席位名称关键词
HOT_MONEY_KEYWORDS = [
    "知春路", "成都", "宁波", "佛山", "拉萨",
    "乐清千帆", "温州", "绍兴", "华鑫证券",
    "财通证券", "游资",
]


def _is_hot_money(seat_name: str) -> bool:
    """根据席位名称关键词识别游资"""
    return any(kw in seat_name for kw in HOT_MONEY_KEYWORDS)


def _fmt_amount(val) -> float:
    """akshare返回的金额可能是 float/NaN，统一处理为 float"""
    try:
        v = float(val)
        return 0.0 if v != v else round(v, 2)  # NaN check
    except (TypeError, ValueError):
        return 0.0


def _fetch_from_akshare(date: str):
    """从akshare拉取龙虎榜数据（列表+席位），返回 (stocks, all_seats) 或 None"""
    import akshare as ak
    from concurrent.futures import ThreadPoolExecutor
    aliases = get_seat_aliases()

    # 1. 拉取当日股票列表
    df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
    if df is None or df.empty:
        return None

    stock_map = {}
    for _, row in df.iterrows():
        code = str(row.get("代码", "")).zfill(6)
        if not code or code == "000000":
            continue
        reason = str(row.get("上榜原因", "") or "").strip()
        interpret = str(row.get("解读", "") or "").strip()
        item = {
            "code": code,
            "name": str(row.get("名称", "")),
            "change_pct": _fmt_amount(row.get("涨跌幅", 0)),
            "close_price": _fmt_amount(row.get("收盘价", 0)),
            "net_buy": _fmt_amount(row.get("龙虎榜净买额", 0)),
            "buy_amount": _fmt_amount(row.get("龙虎榜买入额", 0)),
            "sell_amount": _fmt_amount(row.get("龙虎榜卖出额", 0)),
            "lhb_amount": _fmt_amount(row.get("龙虎榜成交额", 0)),
            "total_amount": _fmt_amount(row.get("市场总成交额", 0)),
            "reason": reason,
            "interpret": interpret,
            "buy_seats": [],
            "sell_seats": [],
        }

        # 同一天同一只股票可能因多个“上榜原因”出现多行，这里聚合成一条
        if code not in stock_map:
            stock_map[code] = item
            stock_map[code]["_reasons"] = [reason] if reason else []
            stock_map[code]["_interprets"] = [interpret] if interpret else []
            continue

        curr = stock_map[code]
        if reason and reason not in curr["_reasons"]:
            curr["_reasons"].append(reason)
        if interpret and interpret not in curr["_interprets"]:
            curr["_interprets"].append(interpret)

        # 金额口径取绝对值更大的那条，避免被较小值覆盖
        if abs(item["net_buy"]) > abs(curr["net_buy"]):
            curr["net_buy"] = item["net_buy"]
            curr["buy_amount"] = item["buy_amount"]
            curr["sell_amount"] = item["sell_amount"]
            curr["lhb_amount"] = item["lhb_amount"]
            curr["total_amount"] = item["total_amount"]
            curr["change_pct"] = item["change_pct"]
            curr["close_price"] = item["close_price"]

    stocks = list(stock_map.values())
    for s in stocks:
        reasons = [r for r in s.pop("_reasons", []) if r]
        interprets = [r for r in s.pop("_interprets", []) if r]
        s["reason"] = "；".join(reasons) if reasons else s.get("reason", "")
        s["interpret"] = "；".join(interprets) if interprets else s.get("interpret", "")

    if not stocks:
        return None

    # 2. 并行拉取每只股票的买卖席位
    def _fetch_seats(stock):
        code = stock["code"]
        all_seats = []
        for direction, flag in [("buy", "买入"), ("sell", "卖出")]:
            try:
                sdf = ak.stock_lhb_stock_detail_em(symbol=code, date=date, flag=flag)
                if sdf is None or sdf.empty:
                    continue
                for i, srow in sdf.iterrows():
                    seat_name = str(srow.get("交易营业部名称", "") or "").strip()
                    all_seats.append({
                        "code": code,
                        "direction": direction,
                        "rank_no": int(srow.get("序号", i + 1)),
                        "seat_name": seat_name,
                        "buy_amount": _fmt_amount(srow.get("买入金额", 0)),
                        "sell_amount": _fmt_amount(srow.get("卖出金额", 0)),
                        "net_amount": _fmt_amount(srow.get("净额", 0)),
                        "is_hot_money": 1 if _is_hot_money(seat_name) else 0,
                        "trader_tag": match_seat_alias(seat_name, aliases).get("trader_tag", ""),
                    })
            except Exception as e:
                logger.warning(f"拉取{code} {flag}席位失败: {e}")
        return all_seats

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(_fetch_seats, stocks))

    all_seats = []
    seat_map = {}
    for seat_list in results:
        for seat in seat_list:
            all_seats.append(seat)
            key = (seat["code"], seat["direction"])
            seat_map.setdefault(key, []).append(seat)

    for stock in stocks:
        code = stock["code"]
        stock["buy_seats"] = seat_map.get((code, "buy"), [])
        stock["sell_seats"] = seat_map.get((code, "sell"), [])

    return stocks, all_seats


def _build_theme_profile(date: str, code: str) -> dict:
    """
    读取题材标签分析结果，补充：
    - 所属题材
    - 所属行业
    - 题材地位（龙头/前排核心/中军跟随/补涨）
    - 同题材涨停家数
    - 题材驱动描述
    """
    profile = {
        "theme": "暂无明确题材",
        "industry": "未知",
        "position": "待观察",
        "theme_count": 0,
        "theme_reason": "暂无题材驱动描述",
    }
    try:
        tagged_stocks = get_limit_up_stocks_by_date(date)
        if not tagged_stocks:
            return profile

        target = next((s for s in tagged_stocks if s.get("code") == code), None)
        if not target:
            return profile

        profile["industry"] = target.get("industry") or "未知"
        theme = (target.get("tag_name") or "").strip()
        if not theme:
            return profile

        same_theme = [s for s in tagged_stocks if (s.get("tag_name") or "").strip() == theme]
        profile["theme"] = theme
        profile["theme_count"] = len(same_theme)

        tags = get_tags_by_date(date)
        reason_map = {t.get("tag_name"): (t.get("reason") or "") for t in tags}
        profile["theme_reason"] = reason_map.get(theme) or "暂无题材驱动描述"

        if target.get("is_leader"):
            profile["position"] = target.get("leader_role") or "龙头"
            return profile

        boards = int(target.get("boards") or 1)
        max_boards = max((int(s.get("boards") or 1) for s in same_theme), default=boards)
        if boards >= max_boards and boards >= 2:
            profile["position"] = "前排核心"
        elif boards >= 2:
            profile["position"] = "中军跟随"
        else:
            profile["position"] = "补涨跟风"
    except Exception as e:
        logger.warning(f"读取题材画像失败({date}-{code}): {e}")

    return profile


@dragon_tiger_bp.route("/api/v1/dragon-tiger", methods=["GET"])
def get_dragon_tiger():
    """获取龙虎榜列表（含席位），有DB缓存则直接返回"""
    date = request.args.get("date", datetime.now().strftime("%Y%m%d"))
    date = date.replace("-", "")

    try:
        # 1. 优先从DB加载
        stocks = get_daily_stocks(date)
        if stocks:
            return v1_success_response(data={"date": date, "stocks": stocks, "source": "db"})

        # 2. 无DB数据，调akshare
        result = _fetch_from_akshare(date)
        if not result:
            return v1_success_response(data={"date": date, "stocks": [], "source": "api"})

        stocks, all_seats = result

        # 3. 写入DB
        save_daily_stocks(date, stocks)
        save_seats(date, all_seats)

        return v1_success_response(data={"date": date, "stocks": stocks, "source": "api"})

    except Exception as e:
        logger.error(f"获取龙虎榜失败: {e}", exc_info=True)
        return v1_error_response(message=f"获取龙虎榜失败: {str(e)}")


def _has_valid_ai_cache(analysis: str | None) -> bool:
    """有非空且足够长度的入库内容即视为有效（AI 输出为自然段，不含固定字段名）。"""
    text = (analysis or "").strip()
    return len(text) >= 20


def analyze_dragon_tiger_stock(date: str, code: str, force: bool = False) -> str:
    """
    为单只股票生成 AI 解读并入库。
    返回: saved | skipped | failed | no_data
    """
    date = (date or "").replace("-", "")
    code = (code or "").zfill(6)
    if not date or not code:
        return "failed"

    try:
        if not force:
            cached = get_ai_analysis(date, code)
            if _has_valid_ai_cache(cached):
                return "skipped"

        stocks = get_daily_stocks(date)
        stock = next((s for s in stocks if s["code"] == code), None)
        if not stock:
            return "no_data"

        theme_profile = _build_theme_profile(date, code)
        prompt = build_dragon_tiger_prompt(stock, theme_profile)
        analysis = call_claude_for_scenario("dragon_tiger", prompt)
        if not analysis:
            return "failed"

        save_ai_analysis(date, code, analysis)
        return "saved"
    except Exception as e:
        logger.error(f"龙虎榜 AI 分析失败({date}-{code}): {e}", exc_info=True)
        return "failed"


def sync_dragon_tiger_for_date(date: str, force: bool = False) -> dict:
    """仅拉取并入库龙虎榜列表与席位，不生成 AI。"""
    date = (date or "").replace("-", "")
    if not date:
        return {"date": date, "stocks": 0, "seats": 0, "source": "invalid", "skipped": True}

    stocks = get_daily_stocks(date)
    if stocks and not force:
        seats = sum(len(s.get("buy_seats", [])) + len(s.get("sell_seats", [])) for s in stocks)
        return {"date": date, "stocks": len(stocks), "seats": seats, "source": "db", "skipped": True}

    result = _fetch_from_akshare(date)
    if not result:
        return {"date": date, "stocks": 0, "seats": 0, "source": "empty", "skipped": False}

    stocks, all_seats = result
    save_daily_stocks(date, stocks)
    save_seats(date, all_seats)
    return {
        "date": date,
        "stocks": len(stocks),
        "seats": len(all_seats),
        "source": "api",
        "skipped": False,
    }


def is_dragon_tiger_ai_complete(date: str) -> bool:
    """当日上榜股是否均已具备有效 AI 解读。"""
    date = (date or "").replace("-", "")
    stocks = get_daily_stocks(date)
    if not stocks:
        return False
    return all(
        _has_valid_ai_cache(get_ai_analysis(date, s.get("code", "")))
        for s in stocks
    )


def run_dragon_tiger_ai_for_date(date: str, force: bool = False) -> dict:
    """为指定交易日全部上榜股批量生成 AI 解读（离线任务入口）。"""
    date = (date or "").replace("-", "")
    stocks = get_daily_stocks(date)
    if not stocks:
        sync = sync_dragon_tiger_for_date(date, force=True)
        if sync.get("stocks"):
            stocks = get_daily_stocks(date)

    if not stocks:
        return {"date": date, "total": 0, "saved": 0, "skipped": 0, "failed": 0, "no_data": 0}

    saved = skipped = failed = no_data = 0
    for stock in stocks:
        code = stock.get("code", "")
        status = analyze_dragon_tiger_stock(date, code, force=force)
        if status == "saved":
            saved += 1
        elif status == "skipped":
            skipped += 1
        elif status == "no_data":
            no_data += 1
        else:
            failed += 1

    return {
        "date": date,
        "total": len(stocks),
        "saved": saved,
        "skipped": skipped,
        "failed": failed,
        "no_data": no_data,
    }


@dragon_tiger_bp.route("/api/v1/dragon-tiger/ai-analysis-cache", methods=["GET"])
def get_dragon_tiger_ai_cache():
    """只读查询已入库的 AI 解读，不触发新分析。"""
    date = (request.args.get("date", "") or "").replace("-", "")
    code = (request.args.get("code", "") or "").zfill(6)
    if not date or not code:
        return v1_error_response(message="请提供 date 和 code 参数")

    cached = get_ai_analysis(date, code)
    if cached and _has_valid_ai_cache(cached):
        return v1_success_response(data={"analysis": cached, "cached": True})
    return v1_success_response(data=None, message="还未生成")


@dragon_tiger_bp.route("/api/v1/dragon-tiger/ai-analysis", methods=["POST"])
def ai_analysis():
    """兼容旧接口：仅返回已入库结果，不在线生成。"""
    body = request.get_json(silent=True) or {}
    date = (body.get("date", "") or "").replace("-", "")
    code = (body.get("code", "") or "").zfill(6)

    if not date or not code:
        return v1_error_response(message="请提供date和code")

    cached = get_ai_analysis(date, code)
    if cached and _has_valid_ai_cache(cached):
        return v1_success_response(data={"analysis": cached, "cached": True})
    return v1_success_response(data=None, message="还未生成，由每日定时任务生成")
