#!/usr/bin/env python3
"""
NiuNIuNiu 股票数据 MCP Server
提供实时行情、大单、资金流、涨停板块等数据工具
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime

API_BASE = "http://localhost:9001"
TIMEOUT = 30


def api_get(path: str, params: dict = None) -> dict:
    """调用后端API"""
    url = f"{API_BASE}{path}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        if query:
            url += f"?{query}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def format_amount(val):
    """格式化金额（万元）"""
    if val is None:
        return "0"
    if abs(val) >= 10000:
        return f"{val/10000:.2f}亿"
    return f"{val:.2f}万"


# ===== Tool implementations =====

def tool_stock_realtime(code: str) -> str:
    """获取个股实时行情"""
    basic = api_get("/api/stock/basic", {"code": code})
    if "error" in basic:
        return f"获取行情失败: {basic['error']}"

    d = basic.get("data", {})
    name = d.get("name", code)
    price = d.get("current_price", 0)
    change_pct = d.get("change_percent", 0)
    change_amt = d.get("change_amount", 0)
    high = d.get("high", 0)
    low = d.get("low", 0)
    open_price = d.get("open", 0)
    volume = d.get("volume", 0)
    turnover = d.get("turnover", 0)
    yclose = d.get("yesterday_close", 0)
    limit_up = d.get("limit_up_price", yclose * 1.1 if yclose else 0)
    limit_down = d.get("limit_down_price", yclose * 0.9 if yclose else 0)

    arrow = "↑" if change_pct > 0 else ("↓" if change_pct < 0 else "→")
    vol_wan = volume / 100 if volume else 0  # 手
    turnover_yi = turnover / 100000000 if turnover else 0

    return (
        f"【{name}({code})】实时行情\n"
        f"现价: {price} {arrow} {change_pct:+.2f}% ({change_amt:+.2f})\n"
        f"开盘: {open_price} | 最高: {high} | 最低: {low}\n"
        f"昨收: {yclose} | 涨停: {limit_up:.2f} | 跌停: {limit_down:.2f}\n"
        f"成交量: {vol_wan:.0f}手 | 成交额: {turnover_yi:.2f}亿\n"
        f"数据源: {d.get('data_source', 'unknown')}"
    )


def tool_stock_large_orders(code: str, date: str = None) -> str:
    """获取大单统计"""
    params = {"code": code}
    if date:
        params["dt"] = date

    stats = api_get("/api/v1/dadantongji", params)
    if "error" in stats:
        return f"获取大单统计失败: {stats['error']}"

    data = stats.get("data", {})
    statistics = data.get("statistics", [])

    if not statistics:
        return f"暂无{code}的大单数据"

    lines = [f"【{code}】大单资金统计"]
    total_buy = 0
    total_sell = 0

    for item in statistics:
        level = item.get("level", "")
        buy_count = item.get("buy_count", 0)
        sell_count = item.get("sell_count", 0)
        buy_amount = item.get("buy_amount", 0)
        sell_amount = item.get("sell_amount", 0)
        net = buy_amount - sell_amount
        total_buy += buy_amount
        total_sell += sell_amount

        net_sign = "+" if net >= 0 else ""
        lines.append(
            f"\n{level}:\n"
            f"  买入 {buy_count}笔 {format_amount(buy_amount)} | "
            f"卖出 {sell_count}笔 {format_amount(sell_amount)}\n"
            f"  净额: {net_sign}{format_amount(net)}"
        )

    total_net = total_buy - total_sell
    net_sign = "+" if total_net >= 0 else ""
    lines.append(
        f"\n汇总: 买入{format_amount(total_buy)} | 卖出{format_amount(total_sell)}"
        f" | 净额{net_sign}{format_amount(total_net)}"
    )

    return "\n".join(lines)


def tool_stock_timeshare(code: str) -> str:
    """获取分时走势概要"""
    quote = api_get("/api/v1/quote", {"code": code})
    if "error" in quote:
        return f"获取分时失败: {quote['error']}"

    data = quote.get("data", {})
    base = data.get("base_info", {})
    fenshi = data.get("fenshi", [])
    zhuli = data.get("zhuli", [])

    if not fenshi:
        return f"暂无{code}的分时数据"

    prev_close = float(base.get("prevClosePrice", 0) or 0)
    high_price = float(base.get("highPrice", 0) or 0)
    low_price = float(base.get("lowPrice", 0) or 0)

    # 取最新几个点
    latest = fenshi[-1] if fenshi else {}
    cur_price = latest.get("price", 0)
    avg_price = latest.get("avg_price", 0)

    # 资金流
    zhuli_latest = zhuli[-1] if zhuli else {}
    main_in = zhuli_latest.get("main_in", 0)
    main_out = zhuli_latest.get("main_out", 0)
    retail_in = zhuli_latest.get("retail_in", 0)
    retail_out = zhuli_latest.get("retail_out", 0)

    # 分时形态判断
    total_points = len(fenshi)
    above_avg = sum(1 for p in fenshi if p.get("price", 0) >= p.get("avg_price", 0))
    above_ratio = above_avg / total_points * 100 if total_points > 0 else 0

    if above_ratio > 70:
        pattern = "强势（价格持续在均线上方）"
    elif above_ratio > 50:
        pattern = "偏强（价格多数时间在均线上方）"
    elif above_ratio > 30:
        pattern = "偏弱（价格多数时间在均线下方）"
    else:
        pattern = "弱势（价格持续在均线下方）"

    change_pct = (cur_price - prev_close) / prev_close * 100 if prev_close else 0

    main_net = main_in - main_out
    retail_net = retail_in - retail_out

    return (
        f"【{code}】分时走势概要\n"
        f"最新价: {cur_price} ({change_pct:+.2f}%)\n"
        f"均价: {avg_price} | 最高: {high_price} | 最低: {low_price}\n"
        f"分时形态: {pattern}（均线上方占比{above_ratio:.0f}%）\n"
        f"数据点数: {total_points}分钟\n\n"
        f"资金流向:\n"
        f"  主力: 流入{format_amount(main_in)} 流出{format_amount(main_out)} 净额{'+' if main_net>=0 else ''}{format_amount(main_net)}\n"
        f"  散户: 流入{format_amount(retail_in)} 流出{format_amount(retail_out)} 净额{'+' if retail_net>=0 else ''}{format_amount(retail_net)}"
    )


def tool_stock_l2_dashboard(code: str, date: str = None) -> str:
    """获取L2看板完整数据"""
    params = {"code": code}
    if date:
        params["dt"] = date

    result = api_get("/api/v1/l2_dashboard", params)
    if "error" in result:
        return f"获取L2数据失败: {result['error']}"

    data = result.get("data", {})
    stock_info = data.get("stock_info", {})
    session = data.get("session_snapshot", {})
    large_orders = data.get("large_orders", [])
    statistics = data.get("statistics", {})
    big_map = data.get("big_map", {})

    name = stock_info.get("name", code)
    price = stock_info.get("price", 0)
    change_pct = stock_info.get("change_percent", 0)

    lines = [f"【{name}({code})】L2看板"]

    # 基本行情
    lines.append(
        f"现价: {price} ({change_pct:+.2f}%)"
        f" | 开:{stock_info.get('open',0)} 高:{stock_info.get('high',0)} 低:{stock_info.get('low',0)}"
    )

    # 盘口快照
    if session:
        vol_ratio = session.get("volume_vs_yesterday_percent", "")
        seal_ratio = session.get("seal_to_turnover_percent", "")
        auction_chg = session.get("auction_change_percent", "")
        lines.append(
            f"\n量比昨日: {vol_ratio} | 封单占比: {seal_ratio} | 竞价涨幅: {auction_chg}"
        )

    # 大单统计
    if statistics:
        lines.append("\n大单统计:")
        for level, stat in statistics.items():
            if isinstance(stat, dict):
                buy_amt = stat.get("buy_amount", 0)
                sell_amt = stat.get("sell_amount", 0)
                net = buy_amt - sell_amt
                lines.append(
                    f"  {level}: 买{format_amount(buy_amt)} 卖{format_amount(sell_amt)} 净{'+' if net>=0 else ''}{format_amount(net)}"
                )

    # 大单明细（最近10笔）
    if large_orders:
        lines.append(f"\n最近大单（共{len(large_orders)}笔）:")
        for order in large_orders[-10:]:
            direction = order.get("direction", order.get("type", ""))
            amount = order.get("amount", 0)
            time_str = order.get("time", "")
            price_val = order.get("price", 0)
            lines.append(
                f"  {time_str} {direction} {price_val} {format_amount(amount)}"
            )

    # 大单地图摘要（找出大单集中的时间段）
    if big_map:
        hot_minutes = []
        for minute, orders in big_map.items():
            if orders:
                total = sum(abs(o.get("amount", o.get("v", 0))) for o in orders)
                if total > 0:
                    hot_minutes.append((minute, total, orders))
        hot_minutes.sort(key=lambda x: x[1], reverse=True)
        if hot_minutes:
            lines.append("\n大单集中时段（TOP5）:")
            for minute, total, orders in hot_minutes[:5]:
                types = [o.get("type", o.get("t", "")) for o in orders]
                lines.append(f"  {minute} 合计{format_amount(total)} {'/'.join(types)}")

    return "\n".join(lines)


def tool_limit_up_themes(code: str = None) -> str:
    """获取今日涨停板块题材"""
    params = {}
    if code:
        params["code"] = code

    result = api_get("/api/v1/limit_up_themes", params)
    if "error" in result:
        return f"获取涨停板块失败: {result['error']}"

    data = result.get("data", {})
    themes = data.get("themes", [])
    current = data.get("current_stock", {})
    lone_wolves = data.get("lone_wolf_stocks", [])
    total = data.get("total_limit_up_count", 0)

    lines = [f"今日涨停概况（共{total}只）"]

    if current and current.get("theme"):
        lines.append(f"\n当前股票所属题材: {current['theme']}")
        lines.append(f"涨停原因: {current.get('reason', '未知')}")

    if themes:
        lines.append("\n涨停题材排行:")
        for i, theme in enumerate(themes[:15]):
            name = theme.get("theme", "")
            count = theme.get("count", 0)
            stocks = theme.get("stocks", [])
            stock_names = [s.get("name", s.get("code", "")) for s in stocks[:5]]
            lines.append(f"  {i+1}. {name}（{count}只）: {', '.join(stock_names)}")

    if lone_wolves:
        lines.append(f"\n独立涨停股: {len(lone_wolves)}只")

    return "\n".join(lines)


# ===== MCP Protocol =====

TOOLS = [
    {
        "name": "stock_realtime",
        "description": "获取个股实时行情数据，包含现价、涨跌幅、成交量、成交额、涨跌停价等",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码，如 002190、601991"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "stock_large_orders",
        "description": "获取个股大单资金统计，按金额分级（300万以上/100万以上/50万以上/30万以上/30万以下），包含买卖笔数、金额和净额",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码"},
                "date": {"type": "string", "description": "日期，格式YYYYMMDD，不传则为今日"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "stock_timeshare",
        "description": "获取个股分时走势概要，包含分时形态判断（强势/偏强/偏弱/弱势）、资金流向（主力vs散户）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "stock_l2_dashboard",
        "description": "获取个股L2看板完整数据，包含行情、盘口快照（量比、封单占比、竞价涨幅）、大单统计、大单明细、大单集中时段",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码"},
                "date": {"type": "string", "description": "日期，格式YYYYMMDD，可选"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "limit_up_themes",
        "description": "获取今日涨停板块题材汇总，包含题材排行、涨停股票列表、独立涨停股数量。可传入股票代码查看该股所属涨停题材",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "股票代码（可选），传入则额外显示该股所属题材和涨停原因"}
            }
        }
    }
]

TOOL_HANDLERS = {
    "stock_realtime": lambda args: tool_stock_realtime(args["code"]),
    "stock_large_orders": lambda args: tool_stock_large_orders(args["code"], args.get("date")),
    "stock_timeshare": lambda args: tool_stock_timeshare(args["code"]),
    "stock_l2_dashboard": lambda args: tool_stock_l2_dashboard(args["code"], args.get("date")),
    "limit_up_themes": lambda args: tool_limit_up_themes(args.get("code")),
}


def send_response(response: dict):
    msg = json.dumps(response)
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def handle_message(message: dict):
    method = message.get("method", "")
    msg_id = message.get("id")

    if method == "initialize":
        send_response({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "niuniuniu-stock", "version": "1.0.0"}
            }
        })
    elif method == "notifications/initialized":
        pass  # no response needed
    elif method == "tools/list":
        send_response({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS}
        })
    elif method == "tools/call":
        tool_name = message.get("params", {}).get("name", "")
        arguments = message.get("params", {}).get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)

        if handler:
            try:
                result_text = handler(arguments)
                send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": result_text}]
                    }
                })
            except Exception as e:
                send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"工具执行错误: {str(e)}"}],
                        "isError": True
                    }
                })
        else:
            send_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            })
    else:
        if msg_id is not None:
            send_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}
            })


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            handle_message(message)
        except json.JSONDecodeError:
            pass


if __name__ == "__main__":
    main()
