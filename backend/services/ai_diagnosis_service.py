"""
AI 诊股：数据聚合、缓存、Claude 调用
"""
import json
import logging
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from services.data_source_adapter import DataSourceAdapter
from services.dragon_tiger_service import get_ai_analysis, get_daily_stocks
from services.theme_service import get_limit_up_stocks_by_date, get_tags_by_date
from services.ths_moneyflow import get_moneyflow
from utils.date_utils import get_next_trading_date, get_recent_trading_dates, get_valid_trading_date
from utils.db import execute_query, execute_write
from utils.json_safe import dumps_json, json_safe

logger = logging.getLogger(__name__)

_adapter = DataSourceAdapter(use_l2=False)

from utils.claude_client import CLAUDE_API_KEY, call_claude

_STOCKAPI_TOKEN = "c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e"
_STOCKAPI_JJQC = "http://user.stockapi.com.cn/v1/base/jjqcUser"


def _init_cache_table():
    sql = """
    CREATE TABLE IF NOT EXISTS ai_diagnosis_cache (
        id INT PRIMARY KEY AUTO_INCREMENT,
        date VARCHAR(8) NOT NULL,
        code VARCHAR(6) NOT NULL,
        snapshot_json LONGTEXT NOT NULL,
        report_json LONGTEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_date_code (date, code)
    )
    """
    try:
        execute_write(sql)
    except Exception as e:
        logger.warning(f"ai_diagnosis_cache 表初始化: {e}")


_init_cache_table()


def _is_after_market_open(now: datetime) -> bool:
    """当日 9:30 及之后视为新交易日会话（含午休、收盘后）。"""
    if now.weekday() >= 5:
        return False
    return now.hour * 60 + now.minute >= 9 * 60 + 30


def get_diagnosis_session_date(now: datetime | None = None) -> str:
    """
    诊股缓存所属交易日（YYYYMMDD）。
    - 盘中/收盘后：当日
    - 次日 9:30 前：上一交易日（沿用上日缓存）
    - 周末/节假日：最近一个交易日
    """
    now = now or datetime.now()
    valid = get_valid_trading_date(now)
    valid_compact = valid.replace("-", "")
    calendar_today = now.strftime("%Y-%m-%d")

    if calendar_today != valid:
        return valid_compact

    if _is_after_market_open(now):
        return valid_compact

    prev = get_next_trading_date(valid, forward=False)
    return prev["date"].replace("-", "")


def get_trading_date_str() -> str:
    """兼容旧调用，等同 get_diagnosis_session_date。"""
    return get_diagnosis_session_date()


def purge_stale_cache(code: str, session_date: str) -> None:
    """清除该股票非当前会话日的诊股缓存。"""
    code = normalize_code(code)
    dt = session_date.replace("-", "")
    try:
        execute_write(
            "DELETE FROM ai_diagnosis_cache WHERE code=%s AND date<>%s",
            (code, dt),
        )
    except Exception as e:
        logger.warning(f"清理诊股旧缓存失败 code={code}: {e}")


def normalize_code(code: str) -> str:
    c = (code or "").strip()
    digits = re.sub(r"\D", "", c)
    if len(digits) >= 6:
        return digits[-6:].zfill(6)
    return digits.zfill(6) if digits else ""


def _get_emotion_summary(trade_date: str) -> dict:
    from routes.emotion_cycle import _get_analysis_from_db

    dt_key = trade_date.replace("-", "")
    row = _get_analysis_from_db(dt_key)
    if not row:
        return {"available": False}
    recs = row.get("recommendations") or []
    rec_text = ""
    if isinstance(recs, list) and recs:
        rec_text = "；".join(
            f"{r.get('name', '')}({r.get('code', '')})" for r in recs[:3] if isinstance(r, dict)
        )
    return {
        "available": True,
        "stage": row.get("stage", ""),
        "analysis": (row.get("analysis") or "")[:600],
        "advice": (row.get("advice") or "")[:400],
        "recommendations": rec_text,
    }


def _get_basic_info(code: str) -> dict:
    try:
        from routes.stock_basic import get_stock_basic_data

        data = get_stock_basic_data(code) or {}
        return {
            "name": data.get("name", ""),
            "current_price": data.get("current_price") or data.get("price"),
            "change_percent": data.get("change_percent"),
            "open": data.get("open"),
            "high": data.get("high"),
            "low": data.get("low"),
            "yesterday_close": data.get("yesterday_close"),
            "volume": data.get("volume"),
            "turnover": data.get("turnover"),
        }
    except Exception as e:
        logger.warning(f"基础行情失败: {e}")
        return {}


def _summarize_timeshare(code: str, dt_dash: str) -> dict:
    try:
        from services.eastmoney_free import EastMoneyFreeSource

        rows = EastMoneyFreeSource().get_timeshare(code, dt_dash) or []
        if len(rows) < 20:
            return {"available": False}
        prices = [float(r.get("price") or 0) for r in rows if r.get("price")]
        volumes = [float(r.get("volume") or 0) for r in rows]
        if not prices:
            return {"available": False}

        open_p = prices[0]
        close_p = prices[-1]
        high_p = max(prices)
        low_p = min(prices)
        mid = len(prices) // 2
        morning = prices[:mid] if mid else prices
        afternoon = prices[mid:] if mid else prices

        def _trend(seg):
            if len(seg) < 2:
                return "震荡"
            diff = seg[-1] - seg[0]
            pct = (diff / seg[0] * 100) if seg[0] else 0
            if pct > 0.8:
                return "上行"
            if pct < -0.8:
                return "下行"
            return "震荡"

        vol_first = sum(volumes[:mid]) if mid else 0
        vol_second = sum(volumes[mid:]) if mid else 0
        vol_label = "午后放量" if vol_second > vol_first * 1.15 else (
            "上午放量" if vol_first > vol_second * 1.15 else "量能均衡"
        )
        pct_open = round((close_p - open_p) / open_p * 100, 2) if open_p else 0

        return {
            "available": True,
            "open": open_p,
            "close": close_p,
            "high": high_p,
            "low": low_p,
            "pct_from_open": pct_open,
            "morning_trend": _trend(morning),
            "afternoon_trend": _trend(afternoon),
            "volume_pattern": vol_label,
            "intraday_range_pct": round((high_p - low_p) / open_p * 100, 2) if open_p else 0,
        }
    except Exception as e:
        logger.warning(f"分时摘要失败: {e}")
        return {"available": False}


def _get_limit_up_detail(trade_date: str, code: str) -> dict:
    profile = _build_theme_profile(trade_date, code)
    detail = {
        "in_pool": profile.get("in_limit_up_pool", False),
        "boards": 0,
        "zt_stat": "",
        "seal_ratio": None,
        "first_time": "",
        "break_count": 0,
        "theme": profile.get("theme", ""),
        "position": profile.get("position", "待观察"),
        "theme_count": profile.get("theme_count", 0),
    }
    try:
        stocks = get_limit_up_stocks_by_date(trade_date) or []
        target = next((s for s in stocks if str(s.get("code", "")).zfill(6) == code), None)
        if target:
            detail.update({
                "in_pool": True,
                "boards": int(target.get("boards") or 1),
                "zt_stat": target.get("zt_stat") or "",
                "seal_ratio": target.get("seal_ratio"),
                "first_time": target.get("first_time") or "",
                "break_count": int(target.get("break_count") or 0),
                "change_pct": target.get("change_pct"),
                "turnover_rate": target.get("turnover_rate"),
            })
    except Exception as e:
        logger.warning(f"涨停详情失败: {e}")
    return detail


def _get_market_ecology(trade_date: str) -> dict:
    try:
        stocks = get_limit_up_stocks_by_date(trade_date) or []
        if not stocks:
            return {"available": False}
        theme_counts = {}
        for s in stocks:
            tag = (s.get("tag_name") or s.get("industry") or "其他").strip()
            theme_counts[tag] = theme_counts.get(tag, 0) + 1
        top_themes = sorted(theme_counts.items(), key=lambda x: -x[1])[:8]
        boards_list = [int(s.get("boards") or 1) for s in stocks]
        first_board = sum(1 for b in boards_list if b == 1)
        return {
            "available": True,
            "limit_up_total": len(stocks),
            "max_boards": max(boards_list) if boards_list else 0,
            "first_board_count": first_board,
            "consec_board_count": len(stocks) - first_board,
            "top_themes": [{"name": n, "count": c} for n, c in top_themes],
        }
    except Exception as e:
        logger.warning(f"短线生态失败: {e}")
        return {"available": False}


def _get_hot_themes_recent(days: int = 3) -> list:
    result = []
    for dt in get_recent_trading_dates(days):
        try:
            tags = get_tags_by_date(dt) or []
            stocks = get_limit_up_stocks_by_date(dt) or []
            theme_counts = {}
            for s in stocks:
                tag = (s.get("tag_name") or "").strip()
                if tag:
                    theme_counts[tag] = theme_counts.get(tag, 0) + 1
            themes = []
            for t in tags[:12]:
                name = (t.get("tag_name") or "").strip()
                if not name:
                    continue
                themes.append({
                    "name": name,
                    "count": theme_counts.get(name, 0),
                    "reason": (t.get("reason") or "")[:80],
                })
            themes.sort(key=lambda x: -x["count"])
            result.append({"date": dt, "themes": themes[:10]})
        except Exception as e:
            logger.warning(f"近{days}日题材 {dt}: {e}")
    return result


def _get_dragon_tiger_profile(code: str, trade_date: str) -> dict:
    dates = list(reversed(get_recent_trading_dates(5)))
    if trade_date.replace("-", "") not in dates:
        dates.append(trade_date.replace("-", ""))
    for dt in reversed(dates):
        try:
            stocks = get_daily_stocks(dt) or []
            target = next((s for s in stocks if str(s.get("code", "")).zfill(6) == code), None)
            if not target:
                continue
            buy_seats = target.get("buy_seats") or []
            sell_seats = target.get("sell_seats") or []
            hot_buy = [
                {
                    "seat": s.get("seat_name", ""),
                    "trader": s.get("trader_tag", ""),
                    "net": s.get("net_amount"),
                }
                for s in buy_seats[:5]
                if s.get("is_hot_money") or s.get("trader_tag")
            ]
            ai_text = get_ai_analysis(dt, code) or ""
            return {
                "on_list": True,
                "date": dt,
                "net_buy": target.get("net_buy"),
                "change_pct": target.get("change_pct"),
                "reason": (target.get("reason") or "")[:120],
                "interpret": (target.get("interpret") or "")[:200],
                "hot_money_buy": hot_buy,
                "sell_pressure": len(sell_seats),
                "ai_summary": ai_text[:500] if ai_text else "",
            }
        except Exception as e:
            logger.warning(f"龙虎榜 {dt}: {e}")
    return {"on_list": False}


def _get_auction_for_code(code: str, trade_date_fmt: str) -> dict:
    """从竞价抢筹榜查找该股（早盘委托金额排序）"""
    import subprocess as sp

    dt_api = trade_date_fmt
    url = (
        f"{_STOCKAPI_JJQC}?tradeDate={dt_api}&period=0&type=1"
        f"&token={_STOCKAPI_TOKEN}"
    )
    try:
        proc = sp.run(
            [
                "curl", "-s", "--max-time", "12", "--insecure",
                "-H", "Referer: http://user.stockapi.com.cn/bidding",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {"in_list": False}
        body = json.loads(proc.stdout)
        if body.get("code") != 20000:
            return {"in_list": False}
        for item in body.get("data") or []:
            if str(item.get("code", "")).zfill(6) == code:
                return {
                    "in_list": True,
                    "grab_change_pct": item.get("qczf"),
                    "grab_turnover_wan": round((item.get("qccje") or 0) / 10000, 2),
                    "grab_order_wan": round((item.get("qcwtje") or 0) / 10000, 2),
                    "open_amount_wan": round((item.get("openAmt") or 0) / 10000, 2),
                }
        return {"in_list": False}
    except Exception as e:
        logger.warning(f"竞价抢筹查询失败: {e}")
        return {"in_list": False, "error": str(e)}


def _build_theme_profile(trade_date: str, code: str) -> dict:
    profile = {
        "theme": "",
        "industry": "",
        "position": "待观察",
        "theme_count": 0,
        "theme_reason": "",
        "in_limit_up_pool": False,
    }
    try:
        stocks = get_limit_up_stocks_by_date(trade_date) or []
        target = next((s for s in stocks if str(s.get("code", "")).zfill(6) == code), None)
        if not target:
            return profile

        profile["in_limit_up_pool"] = True
        profile["industry"] = target.get("industry") or ""
        theme = (target.get("tag_name") or "").strip()
        if not theme:
            return profile

        same = [s for s in stocks if (s.get("tag_name") or "").strip() == theme]
        profile["theme"] = theme
        profile["theme_count"] = len(same)
        tags = get_tags_by_date(trade_date) or []
        reason_map = {t.get("tag_name"): (t.get("reason") or "") for t in tags}
        profile["theme_reason"] = reason_map.get(theme, "")

        if target.get("is_leader"):
            profile["position"] = target.get("leader_role") or "龙头"
        else:
            boards = int(target.get("boards") or 1)
            max_b = max((int(s.get("boards") or 1) for s in same), default=boards)
            if boards >= max_b and boards >= 2:
                profile["position"] = "前排核心"
            elif boards >= 2:
                profile["position"] = "中军跟随"
            else:
                profile["position"] = "补涨"
    except Exception as e:
        logger.warning(f"题材画像失败: {e}")
    return profile


def _extract_l2_summary(l2_result: dict) -> dict:
    if not l2_result or not l2_result.get("success"):
        return {}
    data = l2_result.get("data") or {}
    info = data.get("stock_info") or {}
    stats = data.get("statistics") or {}
    ob = data.get("order_book") or {}
    snap = data.get("session_snapshot") or {}
    limit_up = data.get("limit_up_monitor") or {}
    mf = data.get("moneyflow") or {}
    summary = mf.get("summary") if isinstance(mf, dict) else {}

    return {
        "name": info.get("name"),
        "price": info.get("price"),
        "change_percent": info.get("change_percent"),
        "turnover": info.get("turnover"),
        "bid_ask_ratio": ob.get("bid_ask_ratio") if isinstance(ob, dict) else None,
        "large_order_net": stats.get("net_amount") if isinstance(stats, dict) else None,
        "large_buy_count": stats.get("buy_count") if isinstance(stats, dict) else None,
        "large_sell_count": stats.get("sell_count") if isinstance(stats, dict) else None,
        "session_phase": snap.get("phase") if isinstance(snap, dict) else None,
        "limit_up_status": limit_up.get("status") if isinstance(limit_up, dict) else None,
        "seal_amount": limit_up.get("seal_amount") if isinstance(limit_up, dict) else None,
        "main_net_inflow": summary.get("main_net") if isinstance(summary, dict) else None,
    }


def build_snapshot(code: str, trade_date: str = None) -> dict:
    """并行聚合诊股所需数据"""
    code = normalize_code(code)
    if not code or len(code) != 6:
        raise ValueError("无效股票代码")

    if not trade_date:
        trade_date = get_trading_date_str()
    trade_date = trade_date.replace("-", "")
    dt_dash = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

    missing = []
    snapshot = {
        "code": code,
        "date": trade_date,
        "partial": False,
        "quote": {},
        "basic": {},
        "l2": {},
        "large_orders": {},
        "timeshare": {},
        "emotion": {},
        "market_ecology": {},
        "hot_themes_3d": [],
        "auction": {},
        "theme": {},
        "limit_up": {},
        "dragon_tiger": {},
        "assembled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    def fetch_l2():
        return _adapter.get_l2_dashboard(code, dt=dt_dash)

    def fetch_moneyflow():
        try:
            return get_moneyflow(code)
        except Exception as e:
            logger.warning(f"moneyflow: {e}")
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(fetch_l2): "l2",
            pool.submit(fetch_moneyflow): "mf",
            pool.submit(_get_emotion_summary, trade_date): "emotion",
            pool.submit(_get_auction_for_code, code, dt_dash): "auction",
            pool.submit(_get_basic_info, code): "basic",
            pool.submit(_summarize_timeshare, code, dt_dash): "timeshare",
            pool.submit(_get_market_ecology, trade_date): "market_ecology",
            pool.submit(_get_hot_themes_recent, 3): "hot_themes_3d",
        }
        l2_result = None
        mf_result = None
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                val = fut.result(timeout=35)
                if key == "l2":
                    l2_result = val
                elif key == "mf":
                    mf_result = val
                elif key == "emotion":
                    snapshot["emotion"] = val
                elif key == "auction":
                    snapshot["auction"] = val
                elif key == "basic":
                    snapshot["basic"] = val or {}
                elif key == "timeshare":
                    snapshot["timeshare"] = val
                elif key == "market_ecology":
                    snapshot["market_ecology"] = val
                elif key == "hot_themes_3d":
                    snapshot["hot_themes_3d"] = val or []
            except Exception as e:
                missing.append(key)
                logger.warning(f"snapshot {key} 失败: {e}")

    if l2_result:
        snapshot["l2"] = _extract_l2_summary(l2_result)
        info = (l2_result.get("data") or {}).get("stock_info") or {}
        snapshot["quote"] = {
            "name": info.get("name"),
            "price": info.get("price"),
            "change_percent": info.get("change_percent"),
            "turnover": info.get("turnover"),
        }
    else:
        missing.append("l2")

    if mf_result and isinstance(mf_result, dict):
        summary = mf_result.get("summary") or {}
        snapshot["large_orders"] = {
            "source": mf_result.get("source", "ths"),
            "main_net": summary.get("main_net"),
            "super_big_net": summary.get("super_big_net"),
            "big_net": summary.get("big_net"),
        }
    else:
        missing.append("large_orders")

    snapshot["theme"] = _build_theme_profile(trade_date, code)
    snapshot["limit_up"] = _get_limit_up_detail(trade_date, code)
    snapshot["dragon_tiger"] = _get_dragon_tiger_profile(code, trade_date)
    if missing:
        snapshot["partial"] = True
        snapshot["missing_dims"] = missing

    return json_safe(snapshot)


def get_cache(trade_date: str, code: str):
    code = normalize_code(code)
    dt = trade_date.replace("-", "")
    rows = execute_query(
        "SELECT snapshot_json, report_json FROM ai_diagnosis_cache WHERE date=%s AND code=%s",
        (dt, code),
    )
    if not rows:
        return None
    try:
        return {
            "snapshot": json.loads(rows[0]["snapshot_json"]),
            "report": json.loads(rows[0]["report_json"]),
        }
    except (json.JSONDecodeError, KeyError):
        return None


def save_cache(trade_date: str, code: str, snapshot: dict, report: dict) -> bool:
    code = normalize_code(code)
    dt = trade_date.replace("-", "")
    sql = """
    INSERT INTO ai_diagnosis_cache (date, code, snapshot_json, report_json)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        snapshot_json = VALUES(snapshot_json),
        report_json = VALUES(report_json),
        updated_at = CURRENT_TIMESTAMP
    """
    try:
        execute_write(
            sql,
            (dt, code, dumps_json(snapshot), dumps_json(report)),
        )
        return True
    except Exception as e:
        logger.error(f"保存诊股缓存失败: {e}")
        return False


def _call_claude(prompt: str, max_tokens: int = 4096) -> str:
    text = call_claude(prompt, max_tokens=max_tokens)
    if text:
        logger.info(f"Claude 返回长度: {len(text)}")
    return text


def _strip_json_fence(text: str) -> str:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
    return clean.strip()


def _try_parse_json_object(text: str):
    if not text:
        return None
    clean = _strip_json_fence(text)
    candidates = [clean]
    match = re.search(r"\{[\s\S]*\}", clean)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            # 常见尾逗号等问题
            fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                obj = json.loads(fixed)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _normalize_point_items(items) -> list:
    """统一买卖点为 {price, reason} 结构"""
    if isinstance(items, str):
        items = [items] if items else []
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not item:
            continue
        if isinstance(item, dict):
            price = str(item.get("price") or item.get("level") or item.get("point") or "—")
            reason = str(item.get("reason") or item.get("basis") or item.get("desc") or "")
            out.append({"price": price, "reason": reason})
        else:
            text = str(item)
            if "：" in text:
                price, _, reason = text.partition("：")
                out.append({"price": price.strip(), "reason": reason.strip()})
            elif ":" in text:
                price, _, reason = text.partition(":")
                out.append({"price": price.strip(), "reason": reason.strip()})
            else:
                out.append({"price": "—", "reason": text})
    return out


def _normalize_sections(raw: dict, fallback_text: str = "") -> list:
    sections = raw.get("sections")
    if isinstance(sections, list) and sections:
        out = []
        for s in sections:
            if not isinstance(s, dict):
                continue
            title = str(s.get("title") or "").strip()
            content = str(s.get("content") or "").strip()
            if title and content:
                highlights = s.get("highlights")
                if not isinstance(highlights, list):
                    highlights = []
                out.append({
                    "title": title,
                    "content": content,
                    "highlights": [str(h) for h in highlights if h],
                })
        if out:
            return out

    legacy_map = [
        ("情绪周期", raw.get("emotion_fit") or raw.get("emotion_section")),
        ("大盘环境", raw.get("market_env")),
        ("短线生态", raw.get("short_term_ecology")),
        ("龙虎榜资金", raw.get("dragon_tiger_view")),
        ("板块与热点", raw.get("sector_hot_themes") or raw.get("sector_analysis")),
        ("个股技术", raw.get("stock_technical") or raw.get("timeshare_view")),
        ("涨停连板", raw.get("limit_up_view")),
    ]
    out = []
    for title, content in legacy_map:
        if content:
            out.append({"title": title, "content": str(content), "highlights": []})
    if not out and fallback_text:
        out.append({"title": "综合分析", "content": fallback_text[:1200], "highlights": []})
    return out


def _normalize_report(raw: dict, fallback_text: str = "") -> dict:
    """补齐字段，保证前端可渲染"""
    risks = raw.get("risk_warnings")
    if isinstance(risks, str):
        risks = [risks] if risks else []
    if not isinstance(risks, list):
        risks = []

    summary = (
        raw.get("summary")
        or raw.get("analysis")
        or raw.get("conclusion")
        or (fallback_text[:200] if fallback_text else "")
        or "暂无摘要"
    )

    return {
        "rating": raw.get("rating") or "中性",
        "theme_position": raw.get("theme_position") or "无题材",
        "emotion_fit": raw.get("emotion_fit") or raw.get("emotion") or "",
        "market_env": raw.get("market_env") or "",
        "short_term_ecology": raw.get("short_term_ecology") or "",
        "dragon_tiger_view": raw.get("dragon_tiger_view") or "",
        "sector_hot_themes": raw.get("sector_hot_themes") or raw.get("sector_analysis") or "",
        "stock_technical": raw.get("stock_technical") or raw.get("timeshare_view") or "",
        "limit_up_view": raw.get("limit_up_view") or "",
        "buy_points": _normalize_point_items(raw.get("buy_points")),
        "sell_points": _normalize_point_items(raw.get("sell_points")),
        "stop_loss": raw.get("stop_loss") or raw.get("stopLoss") or "—",
        "stop_loss_reason": raw.get("stop_loss_reason") or "",
        "position_advice": raw.get("position_advice") or raw.get("position") or "观望",
        "risk_warnings": [str(x) for x in risks if x],
        "summary": str(summary),
        "sections": _normalize_sections(raw, fallback_text),
    }


def _fallback_report_from_text(text: str) -> dict:
    return _normalize_report({}, fallback_text=text)


def _parse_report_json(text: str):
    if not text or not text.strip():
        return None
    parsed = _try_parse_json_object(text)
    if parsed:
        return _normalize_report(parsed, fallback_text=text)
    return None


def _build_diagnosis_prompt(snapshot: dict) -> str:
    return f"""你是一位 A 股超短线交易分析师。请根据以下**真实数据快照**对股票 {snapshot.get('code')} 做全面诊股。

分析维度（必须覆盖，数据缺失则在 risk_warnings 说明，禁止编造数字）：
1. **情绪周期**：结合 emotion 字段，说明当前阶段及对该股打法适配度
2. **大盘环境**：结合 market_ecology、涨停家数、连板高度，判断短线赚钱效应
3. **短线生态**：首板/连板结构、打板成功率隐含环境、资金风险偏好
4. **龙虎榜**：dragon_tiger 字段，游资态度（进攻/撤退/分歧）
5. **板块与近3日热点**：theme、hot_themes_3d、limit_up，个股题材地位与持续性
6. **个股基本面**：basic、quote、l2、large_orders、timeshare、auction
7. **涨停连板与溢价**：limit_up 连板数、封板质量、题材内地位、次日溢价预期
8. **买卖点位**：给出具体价格区间或技术位 + 依据；sell_points 含止盈/减仓逻辑

输出要求：
- 只输出一个 JSON 对象，不要 markdown 代码块，不要 ``` 包裹，不要任何前后说明
- 正文用纯中文，不要用 **加粗**、# 标题、列表符号等 Markdown 语法
- buy_points/sell_points 每项为 {{"price":"价位或条件","reason":"依据"}}

快照数据：
{dumps_json(snapshot, indent=2)}

JSON 结构（字段名必须一致）：
{{
  "rating": "偏多|中性|偏空",
  "theme_position": "龙头|前排核心|中军跟随|补涨|无题材",
  "position_advice": "重仓|轻仓试错|观望|不参与",
  "summary": "150字内一句话结论",
  "emotion_fit": "情绪周期适配（80字内）",
  "market_env": "大盘与赚钱效应（80字内）",
  "short_term_ecology": "短线生态（80字内）",
  "dragon_tiger_view": "龙虎榜资金态度（80字内，无榜则说明）",
  "sector_hot_themes": "板块及近3日热点（100字内）",
  "stock_technical": "分时走势+大单净额+资金面（100字内）",
  "limit_up_view": "连板数/涨停溢价/封板质量（80字内，非涨停股说明趋势地位）",
  "buy_points": [{{"price":"买点1","reason":"依据"}}],
  "sell_points": [{{"price":"卖点1","reason":"依据"}}],
  "stop_loss": "止损价位或条件",
  "stop_loss_reason": "止损逻辑",
  "risk_warnings": ["风险1","风险2"],
  "sections": [
    {{"title":"情绪周期","content":"...","highlights":["关键词1"]}},
    {{"title":"大盘环境","content":"..."}},
    {{"title":"短线生态","content":"..."}},
    {{"title":"龙虎榜解读","content":"..."}},
    {{"title":"板块热点","content":"..."}},
    {{"title":"个股研判","content":"..."}}
  ]
}}"""


def run_diagnosis(code: str, force_refresh: bool = False) -> dict:
    code = normalize_code(code)
    trade_date = get_diagnosis_session_date()

    if not force_refresh:
        cached = get_cache(trade_date, code)
        if cached:
            return {
                "code": code,
                "date": trade_date,
                "snapshot": cached["snapshot"],
                "report": cached["report"],
                "cached": True,
            }

    purge_stale_cache(code, trade_date)

    snapshot = build_snapshot(code, trade_date)
    prompt = _build_diagnosis_prompt(snapshot)
    raw = _call_claude(prompt)
    if not raw:
        raise RuntimeError("AI 暂时不可用，请检查 Claude 配置或稍后重试")

    report = _parse_report_json(raw)
    if not report:
        logger.warning(f"诊股 JSON 解析失败，重试。原始前500字: {raw[:500]}")
        raw2 = _call_claude(
            prompt + "\n\n上次输出无法解析为 JSON。请只输出一个合法 JSON 对象，"
            "不要用 markdown 代码块，不要有任何前后说明文字。"
        )
        report = _parse_report_json(raw2) if raw2 else None

    if not report and raw.strip():
        logger.warning("诊股 JSON 解析失败，使用文本兜底报告")
        report = _fallback_report_from_text(raw)
    if not report:
        raise RuntimeError("AI 返回格式无效，请稍后重试")

    save_cache(trade_date, code, snapshot, report)
    return {
        "code": code,
        "date": trade_date,
        "snapshot": snapshot,
        "report": report,
        "cached": False,
    }


def run_chat(code: str, message: str, context: dict) -> dict:
    code = normalize_code(code)
    snapshot = (context or {}).get("snapshot") or {}
    report = (context or {}).get("report") or {}
    prompt = f"""你是 A 股诊股助手。用户正在分析股票 {code}。

【已生成的诊股报告】
{dumps_json(report, indent=2)}

【数据快照】
{dumps_json(snapshot, indent=2)}

【用户追问】
{message}

请结合以上信息简洁回答（300字内），可操作、有风险提示。使用纯中文，不要用 Markdown 格式符号。"""
    reply = _call_claude(prompt, max_tokens=1024)
    if not reply:
        raise RuntimeError("AI 暂时不可用，请稍后重试")
    return {"reply": reply}
