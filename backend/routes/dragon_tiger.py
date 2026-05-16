# backend/routes/dragon_tiger.py
"""
龙虎榜接口模块
- GET  /api/v1/dragon-tiger?date=YYYYMMDD   获取龙虎榜列表（含席位）
- POST /api/v1/dragon-tiger/ai-analysis     AI解读（有缓存直接返回）
"""
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime

from flask import Blueprint, request

from utils.response import v1_success_response, v1_error_response
from services.dragon_tiger_service import (
    get_daily_stocks,
    save_daily_stocks,
    save_seats,
    get_ai_analysis,
    save_ai_analysis,
)

logger = logging.getLogger(__name__)

dragon_tiger_bp = Blueprint("dragon_tiger", __name__)

CLAUDE_API_URL = os.environ.get(
    "CLAUDE_API_URL", "https://token.kalowave.com/v1/chat/completions"
)
CLAUDE_API_KEY = os.environ.get(
    "CLAUDE_API_KEY",
    "sk-9bs6AtWPA7p0vs6Rnz0lxP6VOpufoWSQGV8MAS0i3ncqMGB7",
)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

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

    # 1. 拉取当日股票列表
    df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
    if df is None or df.empty:
        return None

    stocks = []
    for _, row in df.iterrows():
        code = str(row.get("代码", "")).zfill(6)
        if not code or code == "000000":
            continue
        stocks.append({
            "code": code,
            "name": str(row.get("名称", "")),
            "change_pct": _fmt_amount(row.get("涨跌幅", 0)),
            "close_price": _fmt_amount(row.get("收盘价", 0)),
            "net_buy": _fmt_amount(row.get("龙虎榜净买额", 0)),
            "buy_amount": _fmt_amount(row.get("龙虎榜买入额", 0)),
            "sell_amount": _fmt_amount(row.get("龙虎榜卖出额", 0)),
            "lhb_amount": _fmt_amount(row.get("龙虎榜成交额", 0)),
            "total_amount": _fmt_amount(row.get("市场总成交额", 0)),
            "reason": str(row.get("上榜原因", "") or ""),
            "interpret": str(row.get("解读", "") or ""),
            "buy_seats": [],
            "sell_seats": [],
        })

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


def _call_claude(prompt: str) -> str:
    """调用 Claude API（复用项目现有模式）"""
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    })
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(payload)
        payload_file = f.name
    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "90", CLAUDE_API_URL,
             "-H", f"Authorization: Bearer {CLAUDE_API_KEY}",
             "-H", "Content-Type: application/json",
             "-d", f"@{payload_file}"],
            capture_output=True, text=True, timeout=95,
        )
        if proc.returncode != 0:
            logger.error(f"Claude API curl失败(code={proc.returncode}): {proc.stderr[:200]}")
            return ""
        body = json.loads(proc.stdout)
        if "error" in body:
            logger.error(f"Claude API 错误: {body['error']}")
            return ""
        return (body.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", ""))
    except Exception as e:
        logger.error(f"Claude API调用失败: {e}")
        return ""
    finally:
        try:
            os.unlink(payload_file)
        except OSError:
            pass


def _build_ai_prompt(stock: dict) -> str:
    """构建AI分析prompt"""
    def fmt(val):
        v = float(val or 0)
        if abs(v) >= 1e8:
            return f"{v/1e8:.2f}亿"
        if abs(v) >= 1e4:
            return f"{v/1e4:.0f}万"
        return f"{v:.0f}元"

    def seat_lines(seats, label):
        if not seats:
            return f"{label}：无数据\n"
        lines = [f"{label}："]
        for s in seats:
            hm = "【游资】" if s.get("is_hot_money") else ""
            lines.append(
                f"  {s['rank_no']}. {s['seat_name']}{hm}"
                f"  买入{fmt(s['buy_amount'])} 卖出{fmt(s['sell_amount'])} 净额{fmt(s['net_amount'])}"
            )
        return "\n".join(lines) + "\n"

    return f"""你是A股龙虎榜资深分析师，请对以下龙虎榜数据进行专业解读。

股票：{stock['name']}（{stock['code']}）
涨跌幅：{stock['change_pct']}%
上榜原因：{stock['reason']}
龙虎榜净买额：{fmt(stock['net_buy'])}
龙虎榜买入额：{fmt(stock['buy_amount'])}
龙虎榜卖出额：{fmt(stock['sell_amount'])}

{seat_lines(stock.get('buy_seats', []), '买入席位')}
{seat_lines(stock.get('sell_seats', []), '卖出席位')}

请从以下角度分析（300字以内，简洁明了）：
1. 资金性质：各席位属于游资/机构/北向，主要资金属性是什么
2. 操作意图：主力是净买入还是净卖出，对倒可能性如何
3. 游资行为：游资席位的操作特征和意图
4. 综合判断：当前筹码结构和后市参考

直接输出分析内容，不要分点列表，用自然段落。"""


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


@dragon_tiger_bp.route("/api/v1/dragon-tiger/ai-analysis", methods=["POST"])
def ai_analysis():
    """AI解读龙虎榜资金意图（有DB缓存则直接返回，不重复分析）"""
    body = request.get_json(silent=True) or {}
    date = (body.get("date", "") or "").replace("-", "")
    code = (body.get("code", "") or "").zfill(6)

    if not date or not code:
        return v1_error_response(message="请提供date和code")

    try:
        # 1. 检查DB缓存
        cached = get_ai_analysis(date, code)
        if cached:
            return v1_success_response(data={"analysis": cached, "cached": True})

        # 2. 加载股票数据构建prompt
        stocks = get_daily_stocks(date)
        stock = next((s for s in stocks if s["code"] == code), None)
        if not stock:
            return v1_error_response(message=f"未找到{date}日{code}的龙虎榜数据")

        prompt = _build_ai_prompt(stock)
        analysis = _call_claude(prompt)
        if not analysis:
            return v1_error_response(message="AI分析失败，请稍后重试")

        # 3. 写入DB
        save_ai_analysis(date, code, analysis)

        return v1_success_response(data={"analysis": analysis, "cached": False})

    except Exception as e:
        logger.error(f"AI分析失败: {e}", exc_info=True)
        return v1_error_response(message=f"AI分析失败: {str(e)}")
