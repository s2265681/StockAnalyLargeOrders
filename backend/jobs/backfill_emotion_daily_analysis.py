#!/usr/bin/env python3
"""历史当天分析正序回填（从旧到新，便于昨日复盘链）。

用法：
  python jobs/backfill_emotion_daily_analysis.py        # 仅补缺失日期
  python jobs/backfill_emotion_daily_analysis.py force  # 强制重生成全部
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.emotion_cycle import (
    _fetch_emotion_records,
    _get_intraday_from_db,
    _is_empty_daily_analysis,
    _record_date_key,
    analyze_daily_one_date,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_emotion_daily_analysis")

SLEEP_SEC = 2


def _dates_to_process(records: list, force: bool) -> list[str]:
    ordered = sorted(
        {_record_date_key(r) for r in records if _record_date_key(r)}
    )
    if force:
        return ordered
    need = []
    for dt in ordered:
        existing = _get_intraday_from_db(dt)
        if not existing or _is_empty_daily_analysis(existing):
            need.append(dt)
    return need


def main(force: bool = False):
    records = _fetch_emotion_records()
    if not records:
        logger.error("未获取到情绪周期数据")
        sys.exit(1)

    dates_asc = _dates_to_process(records, force)
    if not dates_asc:
        logger.info("所有交易日已有当天分析，无需回填")
        return

    logger.info(
        f"准备正序回填 {len(dates_asc)} 个交易日: "
        f"{dates_asc[0]} → {dates_asc[-1]} (force={force})"
    )

    saved = skipped = failed = 0
    failed_dates: list[str] = []

    for i, dt in enumerate(dates_asc):
        logger.info(f"[{i + 1}/{len(dates_asc)}] 处理 {dt}")
        try:
            status = analyze_daily_one_date(dt, records, force=force)
        except Exception as e:
            logger.error(f"{dt} 异常: {e}")
            status = "failed"

        if status == "saved":
            saved += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1
            failed_dates.append(dt)

        if i < len(dates_asc) - 1 and status == "saved":
            time.sleep(SLEEP_SEC)

    logger.info(
        f"回填完成：保存={saved} 跳过={skipped} 失败={failed}"
        + (f" 失败日期={failed_dates}" if failed_dates else "")
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    force_arg = len(sys.argv) > 1 and sys.argv[1].lower() in (
        "force", "1", "yes", "true", "all"
    )
    main(force=force_arg)
