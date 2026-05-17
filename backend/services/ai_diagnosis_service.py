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
from datetime import datetime, timedelta

from services.data_source_adapter import DataSourceAdapter
from services.theme_service import get_limit_up_stocks_by_date, get_tags_by_date
from services.ths_moneyflow import get_moneyflow
from utils.db import execute_query, execute_write

logger = logging.getLogger(__name__)

_adapter = DataSourceAdapter(use_l2=False)

CLAUDE_API_URL = os.environ.get(
    "CLAUDE_API_URL", "https://token.kalowave.com/v1/chat/completions"
)
CLAUDE_API_KEY = os.environ.get(
    "CLAUDE_API_KEY",
    "sk-9bs6AtWPA7p0vs6Rnz0lxP6VOpufoWSQGV8MAS0i3ncqMGB7",
)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

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


def get_trading_date_str() -> str:
    d = datetime.now()
    dow = d.weekday()
    if dow == 5:
        d -= timedelta(days=1)
    elif dow == 6:
        d -= timedelta(days=2)
    return d.strftime("%Y%m%d")


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
    return {
        "available": True,
        "stage": row.get("stage", ""),
        "analysis": row.get("analysis", ""),
        "advice": row.get("advice", ""),
    }


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
        "l2": {},
        "large_orders": {},
        "emotion": {},
        "auction": {},
        "theme": {},
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

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(fetch_l2): "l2",
            pool.submit(fetch_moneyflow): "mf",
            pool.submit(_get_emotion_summary, trade_date): "emotion",
            pool.submit(_get_auction_for_code, code, dt_dash): "auction",
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
    if missing:
        snapshot["partial"] = True
        snapshot["missing_dims"] = missing

    return snapshot


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
            (dt, code, json.dumps(snapshot, ensure_ascii=False), json.dumps(report, ensure_ascii=False)),
        )
        return True
    except Exception as e:
        logger.error(f"保存诊股缓存失败: {e}")
        return False


def _extract_claude_text(body: dict) -> str:
    """兼容 OpenAI chat/completions 与部分代理返回格式"""
    if not isinstance(body, dict):
        return ""

    if "error" in body:
        logger.error(f"Claude API 错误: {body['error']}")
        return ""

    # Anthropic 原生 messages API
    content_blocks = body.get("content")
    if isinstance(content_blocks, list):
        parts = []
        for block in content_blocks:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        joined = "".join(parts).strip()
        if joined:
            return joined

    message = (body.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return ""


def _call_claude(prompt: str, max_tokens: int = 4096) -> str:
    if not CLAUDE_API_KEY:
        logger.error("CLAUDE_API_KEY 未配置")
        return ""

    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
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
            logger.error(f"Claude curl 失败: {proc.stderr[:200]}")
            return ""
        if not (proc.stdout or "").strip():
            logger.error("Claude API 返回空响应")
            return ""
        try:
            body = json.loads(proc.stdout)
        except json.JSONDecodeError:
            logger.error(f"Claude 响应非 JSON: {proc.stdout[:300]}")
            return ""
        text = _extract_claude_text(body)
        if text:
            logger.info(f"Claude 返回长度: {len(text)}")
        return text
    except Exception as e:
        logger.error(f"Claude 调用失败: {e}")
        return ""
    finally:
        try:
            os.unlink(payload_file)
        except OSError:
            pass


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


def _normalize_report(raw: dict, fallback_text: str = "") -> dict:
    """补齐字段，保证前端可渲染"""
    buy = raw.get("buy_points")
    sell = raw.get("sell_points")
    risks = raw.get("risk_warnings")
    if isinstance(buy, str):
        buy = [buy] if buy else []
    if not isinstance(buy, list):
        buy = []
    if isinstance(sell, str):
        sell = [sell] if sell else []
    if not isinstance(sell, list):
        sell = []
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
    detail = raw.get("detail_markdown") or raw.get("detail") or fallback_text or summary

    return {
        "rating": raw.get("rating") or "中性",
        "theme_position": raw.get("theme_position") or "无题材",
        "emotion_fit": raw.get("emotion_fit") or raw.get("emotion") or "",
        "buy_points": [str(x) for x in buy if x],
        "sell_points": [str(x) for x in sell if x],
        "stop_loss": raw.get("stop_loss") or raw.get("stopLoss") or "—",
        "position_advice": raw.get("position_advice") or raw.get("position") or "观望",
        "risk_warnings": [str(x) for x in risks if x],
        "summary": str(summary),
        "detail_markdown": str(detail),
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
    return f"""你是一位 A 股短线交易分析师。请根据以下**真实数据快照**对股票 {snapshot.get('code')} 进行诊股，给出买卖点与风险提示。

要求：
1. 只能基于快照中的数据推理，缺失维度在 risk_warnings 中说明，禁止编造行情数字。
2. 必须只输出一个 JSON 对象，不要 markdown 代码块，不要其他文字。

快照数据：
{json.dumps(snapshot, ensure_ascii=False, indent=2)}

输出 JSON 结构（字段名必须一致）：
{{
  "rating": "偏多|中性|偏空",
  "theme_position": "龙头|前排|跟风|无题材",
  "emotion_fit": "情绪周期适配说明（50字内）",
  "buy_points": ["买点1", "买点2"],
  "sell_points": ["卖点1", "卖点2"],
  "stop_loss": "止损参考",
  "position_advice": "轻仓|观望|可参与",
  "risk_warnings": ["风险1"],
  "summary": "200字内综合结论",
  "detail_markdown": "完整分析，Markdown格式"
}}"""


def run_diagnosis(code: str, force_refresh: bool = False) -> dict:
    code = normalize_code(code)
    trade_date = get_trading_date_str()

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
{json.dumps(report, ensure_ascii=False, indent=2)}

【数据快照】
{json.dumps(snapshot, ensure_ascii=False, indent=2)}

【用户追问】
{message}

请结合以上信息简洁回答（300字内），可操作、有风险提示。使用 Markdown。"""
    reply = _call_claude(prompt, max_tokens=1024)
    if not reply:
        raise RuntimeError("AI 暂时不可用，请稍后重试")
    return {"reply": reply}
