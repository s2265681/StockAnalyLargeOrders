"""情绪周期阶段推断与 AI 研判校准（规则 + 趋势）。"""
from __future__ import annotations

from typing import Optional

STAGE_RANK = {
    "冰点期": 0,
    "修复期": 1,
    "升温期": 2,
    "高潮期": 3,
    "退潮期": -1,  # 退潮单独处理，优先级高于升温/高潮
}

_PEAK_DROP_RATIO = 0.82  # 较近窗口峰值回落 ≥18% 则不再判高潮


def _safe_int(value, default: int = 0) -> int:
    if value in (None, "-", "--", ""):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default: float = 0.0) -> float:
    if value in (None, "-", "--", ""):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def normalize_stage(stage: str) -> str:
    if not stage:
        return ""
    for key in STAGE_RANK:
        if key in stage or key.rstrip("期") in stage:
            return key if key.endswith("期") else f"{key}期"
    return stage


def _peak_limit_up(records: list) -> int:
    if not records:
        return 0
    return max(_safe_int(r.get("limit_up_count")) for r in records)


def _is_climax_metrics(
    limit_up: int,
    big_profit: float,
    board_hit: float,
    big_loss: float,
    latest_h: int,
    consec: int,
) -> bool:
    """严格高潮期：需满足核心阈值，且连板高度/连板家数/涨停广度至少一项达标。"""
    if limit_up < 100 or big_profit <= 80 or board_hit < 64 or big_loss >= 5:
        return False
    return latest_h >= 7 or consec >= 15 or limit_up >= 120


def infer_stage_from_metrics(
    record: dict,
    context_records: Optional[list] = None,
) -> str:
    """根据单日指标 + 近几日趋势推断情绪阶段。"""
    ctx = context_records or []
    limit_up = _safe_int(record.get("limit_up_count"))
    limit_down = _safe_int(record.get("limit_down_count"))
    big_loss = _safe_float(record.get("big_loss_mood"))
    big_profit = _safe_float(record.get("big_profit_mood"))
    board_hit = _safe_float(record.get("board_hit_rate"))
    latest_h = _safe_int(record.get("latest_height"))
    consec = _safe_int(record.get("consec_limit"))

    prev = ctx[-1] if ctx else None
    prev_limit_up = _safe_int(prev.get("limit_up_count")) if prev else 0
    window = ctx + [record]
    peak_limit_up = _peak_limit_up(window)

    # 退潮：亏钱效应放大 + 涨停骤降
    if big_loss > 15 and limit_up < 50:
        return "退潮期"
    if prev_limit_up > 0:
        drop_pct = (prev_limit_up - limit_up) / prev_limit_up
        if drop_pct >= 0.30 and big_loss > 10:
            return "退潮期"

    # 冰点
    if limit_up < 30 and limit_down > 50:
        return "冰点期"

    # 高潮：指标达标且未从峰值明显回落
    climax_ok = _is_climax_metrics(
        limit_up, big_profit, board_hit, big_loss, latest_h, consec,
    )
    if peak_limit_up > 0 and limit_up < peak_limit_up * _PEAK_DROP_RATIO:
        climax_ok = False
    if climax_ok:
        return "高潮期"

    # 升温
    if (
        (50 <= limit_up and big_profit > 60 and latest_h >= 3)
        or (limit_up >= 80 and big_profit > 70)
        or (consec >= 10 and big_profit > 50)
    ):
        return "升温期"

    # 修复
    if 30 <= limit_up < 55 and limit_down < 30:
        return "修复期"

    return "修复期"


def calibrate_analysis_stage(
    analysis: dict,
    record: dict,
    context_records: Optional[list] = None,
) -> dict:
    """AI 阶段若明显偏热，按规则 + 趋势下调（如连续高潮、涨停从峰值回落）。"""
    if not isinstance(analysis, dict):
        return analysis

    ai_stage = normalize_stage(analysis.get("stage") or "")
    rule_stage = infer_stage_from_metrics(record, context_records)

    if not ai_stage:
        analysis["stage"] = rule_stage
        return analysis

    # 退潮信号优先
    if rule_stage == "退潮期" and ai_stage != "退潮期":
        analysis["stage"] = rule_stage
        return analysis

    ai_rank = STAGE_RANK.get(ai_stage, 1)
    rule_rank = STAGE_RANK.get(rule_stage, 1)

    # 仅下调偏热判断，不强行抬高 AI 阶段
    if ai_stage == "高潮期" and rule_rank < ai_rank:
        analysis["stage"] = rule_stage
    elif ai_rank > rule_rank + 1:
        analysis["stage"] = rule_stage

    return analysis
