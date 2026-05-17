"""
竞价抢筹推荐度回测：对比 v1（现行）与 v2（纯竞价 T-1）胜率。
不对外 API 暴露，由 jobs/auction_grab_backtest.py 或单测调用。
"""
import copy
import logging
from typing import Any

from services.auction_grab_recommendation import (
    enrich_auction_recommendations,
    score_items_v2,
)

logger = logging.getLogger(__name__)


def _winrate(rows: list[dict], field: str, min_stars: int = 1) -> dict[str, Any]:
    """按星级筛选后统计 field 为正的比例及平均收益"""
    picks = [r for r in rows if r.get("stars", 0) >= min_stars]
    valid = [p for p in picks if p.get(field) is not None]
    if not valid:
        return {
            "count": 0,
            "wins": 0,
            "winrate": None,
            "avg_return": None,
        }
    wins = sum(1 for p in valid if float(p[field]) > 0)
    avg = sum(float(p[field]) for p in valid) / len(valid)
    return {
        "count": len(valid),
        "wins": wins,
        "winrate": round(wins / len(valid), 4),
        "avg_return": round(avg, 2),
    }


def _collect_day_rows(
    items: list[dict],
    stars_v1: dict[str, int],
    stars_v2: dict[str, int],
) -> list[dict]:
    rows = []
    for item in items:
        code = str(item.get("code", "")).zfill(6)
        close_pct = item.get("close_change_pct")
        next_pct = item.get("next_day_change_pct")
        for version, star_map in (("v1", stars_v1), ("v2", stars_v2)):
            rows.append(
                {
                    "version": version,
                    "code": code,
                    "stars": star_map.get(code, 0),
                    "close_change_pct": close_pct,
                    "next_day_change_pct": next_pct,
                }
            )
    return rows


def summarize_winrates(all_rows: list[dict]) -> dict[str, Any]:
    """汇总 v1 / v2 各星级胜率"""
    result: dict[str, Any] = {"v1": {}, "v2": {}}
    for version in ("v1", "v2"):
        subset = [r for r in all_rows if r["version"] == version]
        result[version] = {
            "star3": {
                "close": _winrate(subset, "close_change_pct", min_stars=3),
                "next": _winrate(subset, "next_day_change_pct", min_stars=3),
            },
            "star2plus": {
                "close": _winrate(subset, "close_change_pct", min_stars=2),
                "next": _winrate(subset, "next_day_change_pct", min_stars=2),
            },
            "star1plus": {
                "close": _winrate(subset, "close_change_pct", min_stars=1),
                "next": _winrate(subset, "next_day_change_pct", min_stars=1),
            },
        }
    return result


def run_recommendation_backtest(
    dates_dash: list[str],
    period: int = 0,
    fetch_items_fn=None,
    enrich_returns_fn=None,
) -> dict[str, Any]:
    """
    对多个交易日回测 v1 vs v2 胜率。

    fetch_items_fn(trade_date_dash) -> list[dict]  需含 code/name/grab_* 字段
    enrich_returns_fn(items, trade_date_dash) -> None  写入 close/next 涨幅
    """
    if not dates_dash:
        return {"days": 0, "summary": {}, "by_date": []}

    all_rows: list[dict] = []
    by_date: list[dict] = []
    skipped: list[str] = []

    for trade_date in dates_dash:
        try:
            items = fetch_items_fn(trade_date) if fetch_items_fn else []
        except Exception as e:
            logger.warning(f"拉取 {trade_date} 失败: {e}")
            skipped.append(trade_date)
            continue

        if not items:
            skipped.append(trade_date)
            continue

        items = copy.deepcopy(items)
        if enrich_returns_fn:
            enrich_returns_fn(items, trade_date)

        batch_v1 = copy.deepcopy(items)
        enrich_auction_recommendations(batch_v1, trade_date, period)
        stars_v1 = {
            str(x.get("code", "")).zfill(6): int(x.get("recommend_stars") or 0)
            for x in batch_v1
        }

        scored_v2 = score_items_v2(items, trade_date, period)
        stars_v2 = {r["code"]: int(r.get("recommend_stars") or 0) for r in scored_v2}

        day_rows = _collect_day_rows(items, stars_v1, stars_v2)
        all_rows.extend(day_rows)

        day_summary = summarize_winrates(day_rows)
        by_date.append(
            {
                "date": trade_date,
                "item_count": len(items),
                "summary": day_summary,
            }
        )

    summary = summarize_winrates(all_rows)
    return {
        "days": len(by_date),
        "skipped": skipped,
        "summary": summary,
        "by_date": by_date,
    }


def format_backtest_report(result: dict[str, Any]) -> str:
    """人类可读的胜率对比报告"""
    lines = [
        "===== 竞价抢筹推荐度回测 (v1 vs v2) =====",
        f"有效交易日: {result.get('days', 0)}",
    ]
    if result.get("skipped"):
        lines.append(f"跳过: {', '.join(result['skipped'])}")

    summary = result.get("summary") or {}
    for version, label in (("v1", "现行(当日情绪+题材)"), ("v2", "纯竞价(T-1情绪+题材)")):
        s = summary.get(version) or {}
        lines.append(f"\n--- {label} ---")
        for bucket, name in (
            ("star3", "三星"),
            ("star2plus", "二星及以上"),
            ("star1plus", "一星及以上"),
        ):
            b = s.get(bucket) or {}
            close = b.get("close") or {}
            nxt = b.get("next") or {}
            c_wr = close.get("winrate")
            n_wr = nxt.get("winrate")
            c_str = f"{c_wr * 100:.1f}%" if c_wr is not None else "N/A"
            n_str = f"{n_wr * 100:.1f}%" if n_wr is not None else "N/A"
            lines.append(
                f"  {name}: 当日胜率 {c_str} ({close.get('wins', 0)}/{close.get('count', 0)}) "
                f"均收 {close.get('avg_return', 'N/A')}% | "
                f"次日胜率 {n_str} ({nxt.get('wins', 0)}/{nxt.get('count', 0)}) "
                f"均收 {nxt.get('avg_return', 'N/A')}%"
            )

    return "\n".join(lines)
