"""
竞价抢筹推荐度：综合题材主线、大盘环境、情绪周期与抢筹强度打分。
每日约 1–2 只三星、3–4 只一至三星，其余不标星。
"""
import logging
from typing import Any

from services.theme_service import get_limit_up_stocks_by_date
from utils.date_utils import get_recent_trading_dates

logger = logging.getLogger(__name__)

# 情绪阶段 → 基础分（满分30）
_STAGE_SCORE = {
    "升温期": 28,
    "升温": 28,
    "修复期": 24,
    "修复": 24,
    "高潮期": 16,
    "高潮": 16,
    "退潮期": 8,
    "退潮": 8,
    "冰点期": 5,
    "冰点": 5,
}

_POSITION_BONUS = {
    "龙头": 8,
    "前排核心": 5,
    "中军跟随": 3,
    "补涨": 1,
}

_emotion_records_cache: dict[str, Any] = {}


def _normalize_stage(stage: str) -> str:
    from utils.emotion_stage import normalize_stage

    return normalize_stage(stage)


def _get_emotion_record(trade_date_dash: str):
    """按 YYYY-MM-DD 取情绪周期原始指标"""
    global _emotion_records_cache
    if not _emotion_records_cache.get("records"):
        try:
            from routes.emotion_cycle import _fetch_emotion_records

            _emotion_records_cache["records"] = _fetch_emotion_records()
        except Exception as e:
            logger.warning(f"拉取情绪周期失败: {e}")
            _emotion_records_cache["records"] = []

    for r in _emotion_records_cache.get("records") or []:
        if r.get("date") == trade_date_dash:
            return r
    return None


def _infer_stage_from_metrics(record: dict, context_records=None) -> str:
    """无 AI 研判时，用指标 + 趋势粗判阶段"""
    from utils.emotion_stage import infer_stage_from_metrics

    return infer_stage_from_metrics(record, context_records)


def _get_emotion_context(trade_date_compact: str, trade_date_dash: str) -> dict:
    from routes.emotion_cycle import _get_analysis_from_db, _is_placeholder_analysis

    ctx = {"stage": "", "stage_score": 15, "advice": "", "recommended_names": set()}
    analysis = _get_analysis_from_db(trade_date_compact)
    if analysis and not _is_placeholder_analysis(analysis):
        stage = _normalize_stage(analysis.get("stage") or "")
        ctx["stage"] = stage
        ctx["advice"] = (analysis.get("advice") or "")[:120]
        for rec in analysis.get("recommendations") or []:
            name = (rec.get("stock") or "").strip()
            if name:
                ctx["recommended_names"].add(name)

    record = _get_emotion_record(trade_date_dash)
    if record:
        ctx["metrics"] = record
        if not ctx["stage"]:
            ctx["stage"] = _infer_stage_from_metrics(record)
    else:
        ctx["metrics"] = {}

    stage_key = ctx["stage"]
    for k, v in _STAGE_SCORE.items():
        if k in stage_key:
            ctx["stage_score"] = v
            break
    else:
        ctx["stage_score"] = 15
    return ctx


def _build_hot_themes(trade_date_compact: str) -> dict[str, dict]:
    """近3交易日题材热度：题材名 -> {count, rank, is_mainline}"""
    theme_agg: dict[str, int] = {}
    dates = get_recent_trading_dates(3)
    if trade_date_compact not in dates:
        dates = [trade_date_compact] + [d for d in dates if d != trade_date_compact]

    for dt in dates[:3]:
        try:
            stocks = get_limit_up_stocks_by_date(dt) or []
            weight = 3 if dt == trade_date_compact else 1
            for s in stocks:
                tag = (s.get("tag_name") or "").strip()
                if tag:
                    theme_agg[tag] = theme_agg.get(tag, 0) + weight
        except Exception as e:
            logger.warning(f"题材统计 {dt}: {e}")

    sorted_themes = sorted(theme_agg.items(), key=lambda x: -x[1])
    result = {}
    for idx, (name, count) in enumerate(sorted_themes):
        result[name] = {
            "count": count,
            "rank": idx + 1,
            "is_mainline": idx < 3 and count >= 3,
        }
    return result


def _build_stock_theme_map(trade_date_compact: str) -> dict[str, dict]:
    """涨停池内个股题材画像"""
    mapping = {}
    try:
        stocks = get_limit_up_stocks_by_date(trade_date_compact) or []
    except Exception as e:
        logger.warning(f"涨停池查询失败: {e}")
        return mapping

    theme_groups: dict[str, list] = {}
    for s in stocks:
        theme = (s.get("tag_name") or "").strip()
        if theme:
            theme_groups.setdefault(theme, []).append(s)

    for s in stocks:
        code = str(s.get("code", "")).zfill(6)
        theme = (s.get("tag_name") or "").strip()
        industry = (s.get("industry") or "").strip()
        boards = int(s.get("boards") or 1)
        same = theme_groups.get(theme, []) if theme else []
        max_b = max((int(x.get("boards") or 1) for x in same), default=boards)

        if s.get("is_leader"):
            position = s.get("leader_role") or "龙头"
        elif boards >= max_b and boards >= 2:
            position = "前排核心"
        elif boards >= 2:
            position = "中军跟随"
        elif theme:
            position = "补涨"
        else:
            position = "待观察"

        mapping[code] = {
            "theme": theme,
            "industry": industry,
            "position": position,
            "boards": boards,
            "in_pool": True,
            "theme_count": len(same),
            "seal_ratio": s.get("seal_ratio"),
            "first_time": s.get("first_time") or "",
        }
    return mapping


def _market_score(metrics: dict, hot_themes: dict) -> float:
    """大盘/短线生态 0–25"""
    if not metrics:
        mainline = sum(1 for t in hot_themes.values() if t.get("is_mainline"))
        return 12.0 if mainline >= 1 else 8.0

    limit_up = int(metrics.get("limit_up_count") or 0)
    board_hit = float(metrics.get("board_hit_rate") or 0)
    rise_count = int(metrics.get("rise_count") or 0)
    limit_down = int(metrics.get("limit_down_count") or 0)

    score = 8.0
    if limit_up >= 80:
        score += 10
    elif limit_up >= 50:
        score += 7
    elif limit_up >= 30:
        score += 4
    else:
        score += 1

    if board_hit >= 60:
        score += 4
    elif board_hit >= 45:
        score += 2

    if rise_count >= 2800:
        score += 3
    elif rise_count >= 2300:
        score += 1

    if limit_down > 40:
        score -= 4

    return max(0.0, min(25.0, score))


def _theme_score(profile: dict, hot_themes: dict) -> float:
    """题材主线 0–30"""
    theme = profile.get("theme") or ""
    if not theme:
        return 4.0

    hot = hot_themes.get(theme)
    if not hot:
        return 10.0

    rank = hot.get("rank", 99)
    count = hot.get("count", 0)
    score = 12.0
    if hot.get("is_mainline"):
        score = 28.0
    elif rank <= 5:
        score = 22.0
    elif rank <= 8:
        score = 16.0

    if count >= 5:
        score = min(30.0, score + 2)
    score += _POSITION_BONUS.get(profile.get("position", ""), 0)
    if profile.get("theme_count", 0) >= 3:
        score += 2
    return min(30.0, score)


def _auction_strength_score(item: dict, order_amounts: list[float]) -> float:
    """抢筹强度 0–15"""
    pct = float(item.get("grab_change_pct") or 0)
    order = float(item.get("grab_order_amount") or 0)

    pct_score = 0.0
    if 3 <= pct <= 7:
        pct_score = 8.0
    elif 7 < pct <= 9.5:
        pct_score = 6.0
    elif 1 <= pct < 3:
        pct_score = 4.0
    elif pct > 9.5:
        pct_score = 3.0
    else:
        pct_score = 2.0

    if not order_amounts:
        return min(15.0, pct_score)

    max_order = max(order_amounts) or 1
    rank_ratio = order / max_order
    order_score = rank_ratio * 7.0
    return min(15.0, pct_score + order_score)


def _name_in_emotion_recos(name: str, rec_names: set) -> bool:
    if not name or not rec_names:
        return False
    return any(name in n or n in name for n in rec_names)


def _is_at_limit_up(code: str, change_pct) -> bool:
    if change_pct is None:
        return False
    try:
        pct = float(change_pct)
    except (TypeError, ValueError):
        return False
    code = str(code).zfill(6)
    if code.startswith(("30", "68")):
        return pct >= 19.5
    if code.startswith(("4", "8")):
        return pct >= 29.5
    return pct >= 9.5


def _eligible_for_stars(item: dict, live_map: dict | None = None) -> bool:
    return not _is_item_at_limit_up(item, live_map)


def _current_change_pct(item: dict, live_map: dict | None = None) -> float | None:
    """尾盘/盘中涨停判定：取实时行情、今日涨幅、竞价涨幅的最大值"""
    code = str(item.get("code", "")).zfill(6)
    candidates = [
        (live_map or {}).get(code),
        item.get("today_change_pct"),
        item.get("close_change_pct"),
        item.get("grab_change_pct"),
    ]
    values = []
    for pct in candidates:
        if pct is None:
            continue
        try:
            values.append(float(pct))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def _is_item_at_limit_up(item: dict, live_map: dict | None = None) -> bool:
    code = str(item.get("code", "")).zfill(6)
    pct = _current_change_pct(item, live_map)
    return _is_at_limit_up(code, pct)


def _is_auction_eligible(item: dict, live_map: dict, period: int) -> bool:
    """是否可参与竞价推荐（未涨停）。
    period=0 早盘竞价：只看竞价涨幅——盘中涨停不影响竞价时的推荐资格。
    period=1 尾盘：看实时行情。
    """
    code = str(item.get("code", "")).zfill(6)
    if period == 0:
        return not _is_at_limit_up(code, item.get("grab_change_pct"))
    return not _is_item_at_limit_up(item, live_map)


def strip_limit_up_recommendations(
    items: list[dict],
    live_change_by_code: dict | None = None,
    period: int = 0,
) -> None:
    """涨停标的清除推荐星。
    period=0 早盘竞价：仅用竞价涨幅判断，避免因盘中涨停误剥星。
    period=1 尾盘：使用实时行情。
    """
    live_map = live_change_by_code or {}
    for item in items:
        code = str(item.get("code", "")).zfill(6)
        if period == 0:
            at_limit = _is_at_limit_up(code, item.get("grab_change_pct"))
        else:
            at_limit = _is_item_at_limit_up(item, live_map)
        if not at_limit:
            continue
        item["recommend_stars"] = 0
        item["recommend_reason"] = "竞价时已涨停，不参与推荐" if period == 0 else "当日已涨停，不参与推荐"


def _build_reason(
    stars: int,
    stage: str,
    profile: dict,
    market_part: str,
) -> str:
    parts = []
    if stage:
        parts.append(f"情绪{stage}")
    theme = profile.get("theme")
    if theme:
        pos = profile.get("position", "")
        parts.append(f"{theme}" + (f"·{pos}" if pos and pos != "待观察" else ""))
    elif profile.get("industry"):
        parts.append(profile["industry"])
    if market_part:
        parts.append(market_part)
    if stars >= 3:
        parts.append("主线+抢筹共振")
    label = "；".join(parts[:3]) if parts else "综合偏弱"
    return label[:48]


def _prev_trading_date(trade_date_dash: str) -> str:
    from utils.date_utils import get_next_trading_date

    return get_next_trading_date(trade_date_dash, forward=False)["date"]


def _score_items(
    items: list[dict],
    trade_date_dash: str,
    period: int,
    *,
    context_date_dash: str | None = None,
    use_same_day_bonus: bool = True,
    weights: dict | None = None,
    assign_stars: bool = True,
) -> tuple[list[dict], dict]:
    """
    内部打分。context_date_dash 默认等于 trade_date_dash；
    v2 传入 T-1 日期，且 use_same_day_bonus=False。
    weights 键: emotion, theme, auction, market（相对满分缩放系数）。
    返回 (scored_rows, emotion_ctx)
    """
    ctx_date = context_date_dash or trade_date_dash
    ctx_compact = ctx_date.replace("-", "")
    trade_date_compact = trade_date_dash.replace("-", "")

    w = weights or {
        "emotion": 1.0,
        "theme": 1.0,
        "auction": 1.0,
        "market": 1.0,
    }

    emotion = _get_emotion_context(ctx_compact, ctx_date)
    hot_themes = _build_hot_themes(ctx_compact)
    stock_themes = _build_stock_theme_map(ctx_compact)
    metrics = emotion.get("metrics") or {}
    market_base = _market_score(metrics, hot_themes) * w["market"]

    order_amounts = [float(x.get("grab_order_amount") or 0) for x in items]
    period_factor = 0.92 if period == 1 else 1.0

    scored = []
    for item in items:
        code = str(item.get("code", "")).zfill(6)
        name = item.get("name") or ""
        profile = stock_themes.get(
            code,
            {
                "theme": "",
                "industry": "",
                "position": "待观察",
                "in_pool": False,
                "theme_count": 0,
            },
        )

        emotion_part = emotion["stage_score"] * w["emotion"]
        theme_part = _theme_score(profile, hot_themes) * w["theme"]
        auction_part = _auction_strength_score(item, order_amounts) * w["auction"]
        market_part_score = market_base

        bonus = 0.0
        if use_same_day_bonus:
            if _name_in_emotion_recos(name, emotion["recommended_names"]):
                bonus += 6.0
            if profile.get("in_pool") and profile.get("boards", 0) >= 2:
                bonus += 3.0

        composite = (
            emotion_part + theme_part + auction_part + market_part_score + bonus
        ) * period_factor

        scored.append(
            {
                "code": code,
                "composite_score": round(composite, 2),
                "profile": profile,
            }
        )

    if assign_stars:
        _assign_stars(scored)
    return scored, emotion


def score_items_v2(
    items: list[dict],
    trade_date_dash: str,
    period: int = 0,
) -> list[dict]:
    """
    纯竞价版（T-1 情绪/题材/大盘 + 当日抢筹），仅供回测对比，不写入 API 响应。
    不含当日涨停池加分、当日情绪推荐名单加分。
    """
    if not items:
        return []

    prev_date = _prev_trading_date(trade_date_dash)
    scored, _ = _score_items(
        items,
        trade_date_dash,
        period,
        context_date_dash=prev_date,
        use_same_day_bonus=False,
        weights={
            "emotion": 20.0 / 30.0,
            "theme": 25.0 / 30.0,
            "auction": 40.0 / 15.0,
            "market": 15.0 / 25.0,
        },
    )
    return scored


def _assign_stars(scored: list[dict], eligible_codes: set[str] | None = None) -> None:
    """按分数排序后分配 1–3 星，最多 2 只三星、4 只一星以上（仅对 eligible_codes）"""
    if not scored:
        return

    pool = scored
    if eligible_codes is not None:
        pool = [r for r in scored if r["code"] in eligible_codes]
    if not pool:
        for row in scored:
            row["recommend_stars"] = 0
        return

    pool.sort(key=lambda x: -x["composite_score"])
    for row in scored:
        row["rank"] = 0
        row["recommend_stars"] = 0

    # 三星：前1–2名且分数达标
    top_score = pool[0]["composite_score"]
    min_three_star = max(55.0, top_score * 0.82)
    three_star_count = 0
    for row in pool:
        if three_star_count >= 2:
            break
        if row["composite_score"] >= min_three_star:
            row["recommend_stars"] = 3
            three_star_count += 1

    # 一至三星：第3–6名（尚未标星的靠前标的）
    secondary = [r for r in pool if r["recommend_stars"] == 0][:4]
    if secondary:
        thresholds = [
            top_score * 0.72,
            top_score * 0.58,
            top_score * 0.45,
        ]
        for row in secondary:
            s = row["composite_score"]
            if s >= thresholds[0]:
                row["recommend_stars"] = 3
            elif s >= thresholds[1]:
                row["recommend_stars"] = 2
            elif s >= thresholds[2]:
                row["recommend_stars"] = 1

    # 全表最多 2 只三星
    starred = [r for r in pool if r["recommend_stars"] == 3]
    if len(starred) > 2:
        for row in starred[2:]:
            row["recommend_stars"] = 2

    for i, row in enumerate(sorted(scored, key=lambda x: -x["composite_score"])):
        row["rank"] = i + 1


def enrich_auction_recommendations(
    items: list[dict],
    trade_date_dash: str,
    period: int = 0,
    *,
    live_change_by_code: dict | None = None,
) -> dict:
    """
    为竞价抢筹列表写入 recommend_stars / recommend_reason / recommend_hint
    trade_date_dash: YYYY-MM-DD
    period: 0早盘 1尾盘（尾盘整体降权）
    """
    if not items:
        return {"stage": "", "hint": ""}

    live_map = live_change_by_code or {}
    scored, emotion = _score_items(
        items, trade_date_dash, period, use_same_day_bonus=True, assign_stars=False,
    )
    eligible = {
        str(it.get("code", "")).zfill(6)
        for it in items
        if _is_auction_eligible(it, live_map, period)
    }
    _assign_stars(scored, eligible)

    metrics = emotion.get("metrics") or {}
    limit_up = int(metrics.get("limit_up_count") or 0)
    if limit_up >= 50:
        market_part = f"涨停{limit_up}家偏强"
    elif limit_up >= 30:
        market_part = f"涨停{limit_up}家温和"
    elif limit_up > 0:
        market_part = f"涨停{limit_up}家偏弱"
    else:
        market_part = ""

    score_by_code = {r["code"]: r for r in scored}
    stage = emotion.get("stage") or ""
    for item in items:
        code = str(item.get("code", "")).zfill(6)
        row = score_by_code.get(code, {})
        if not _is_auction_eligible(item, live_map, period):
            item["recommend_stars"] = 0
            item["recommend_reason"] = "竞价时已涨停，不参与推荐" if period == 0 else "当日已涨停，不参与推荐"
            item["recommend_score"] = row.get("composite_score", 0)
            continue
        stars = row.get("recommend_stars", 0)
        profile = row.get("profile", {})
        item["recommend_stars"] = stars
        item["recommend_reason"] = _build_reason(
            stars, stage, profile, market_part
        )
        item["recommend_score"] = row.get("composite_score", 0)

    strip_limit_up_recommendations(items, live_map, period)

    hint = emotion.get("advice") or ""
    if stage and not hint:
        hints = {
            "升温期": "情绪升温，优先主线龙头竞价弱转强",
            "修复期": "情绪修复，轻仓试错主线前排",
            "高潮期": "情绪高潮，竞价追高需谨慎",
            "退潮期": "情绪退潮，竞价标星仅供参考",
            "冰点期": "情绪冰点，仅观察极强共振",
        }
        for k, v in hints.items():
            if k in stage:
                hint = v
                break

    return {"stage": stage, "hint": hint}
