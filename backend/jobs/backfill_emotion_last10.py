#!/usr/bin/env python3
"""一次性补全最近 N 个交易日的情绪周期分析（周期研判 + 当天分析）。

用法：
  python jobs/backfill_emotion_last10.py           # 补最近 10 个交易日缺失的两类分析
  python jobs/backfill_emotion_last10.py 10 force   # 强制重生成最近 10 天
  python jobs/backfill_emotion_last10.py 5          # 只补最近 5 天

说明：
- 周期研判走 analyze_one_date；当天分析走 analyze_daily_one_date。
- 两者均幂等：force=False 时已存在则跳过，只补空缺。
- 当天分析依赖前一日做「昨日复盘」，故按从旧到新顺序生成。
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.emotion_cycle import (
    _fetch_emotion_records,
    _record_date_key,
    analyze_one_date,
    analyze_daily_one_date,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_emotion_last10")

SLEEP_SEC = 2


def main(days: int = 10, force: bool = False):
    records = _fetch_emotion_records()
    if not records:
        logger.error("未获取到情绪周期数据")
        sys.exit(1)

    ordered_dates = sorted(
        {_record_date_key(r) for r in records if isinstance(r, dict) and _record_date_key(r)}
    )
    targets = ordered_dates[-days:]
    if not targets:
        logger.error("无可处理的交易日")
        sys.exit(1)
    logger.info(f"目标 {len(targets)} 个交易日: {targets[0]} → {targets[-1]} (force={force})")

    # 1) 周期研判（顺序无依赖，从旧到新即可）
    c_saved = c_skip = c_fail = 0
    for i, dt in enumerate(targets):
        try:
            status = analyze_one_date(dt, records, force=force)
        except Exception as e:
            logger.error(f"[周期] {dt} 异常: {e}")
            c_fail += 1
            time.sleep(SLEEP_SEC)
            continue
        if status == "saved":
            c_saved += 1
        elif status == "skipped":
            c_skip += 1
        else:
            c_fail += 1
        if i < len(targets) - 1:
            time.sleep(SLEEP_SEC)
    logger.info(f"周期研判完成: saved={c_saved} skipped={c_skip} failed={c_fail}")

    # 2) 当天分析（依赖前一日复盘，从旧到新）
    d_saved = d_skip = d_fail = 0
    for i, dt in enumerate(targets):
        try:
            status = analyze_daily_one_date(dt, records, force=force)
        except Exception as e:
            logger.error(f"[当天] {dt} 异常: {e}")
            d_fail += 1
            time.sleep(SLEEP_SEC)
            continue
        if status == "saved":
            d_saved += 1
        elif status == "skipped":
            d_skip += 1
        else:
            d_fail += 1
        if i < len(targets) - 1:
            time.sleep(SLEEP_SEC)
    logger.info(f"当天分析完成: saved={d_saved} skipped={d_skip} failed={d_fail}")

    logger.info(
        f"===== 全部完成 周期(saved={c_saved},skip={c_skip},fail={c_fail}) "
        f"当天(saved={d_saved},skip={d_skip},fail={d_fail}) ====="
    )
    if c_fail or d_fail:
        sys.exit(1)


if __name__ == "__main__":
    argv = sys.argv[1:]
    n = 10
    frc = False
    for a in argv:
        if a.isdigit():
            n = int(a)
        elif a.lower() in ("force", "1", "true", "yes"):
            frc = True
    main(days=n, force=frc)
