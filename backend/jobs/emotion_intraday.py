#!/usr/bin/env python3
"""开盘后先刷新当日情绪周期：周期研判 + 当天买卖指导。

供工作日 09:38 独立 cron 调用。与 intraday 分开跑，避免梯队构建/AI 卡住时
当日情绪数据迟迟出不来；后续 intraday 各时段继续覆盖更新。
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.emotion_cycle import (
    _fetch_emotion_records,
    _record_date_key,
    analyze_daily_one_date,
    analyze_one_date,
    inject_fallback_if_missing,
    save_intraday_snapshot,
)
from utils.date_utils import get_valid_trading_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("emotion_intraday")


def main() -> int:
    dt = get_valid_trading_date().replace("-", "")
    logger.info("===== 情绪周期盘初刷新开始 date=%s =====", dt)

    try:
        records = _fetch_emotion_records()
    except Exception as e:
        logger.error("拉取情绪周期数据失败: %s", e, exc_info=True)
        return 1
    if not records:
        logger.error("未获取到情绪周期数据")
        return 1

    records = inject_fallback_if_missing(records, dt)
    records = sorted(records, key=_record_date_key)
    target = next((r for r in records if _record_date_key(r) == dt), None)
    if target is None:
        logger.error("情绪周期数据中缺少当天 %s", dt)
        return 1

    try:
        save_intraday_snapshot(target)
    except Exception as e:
        logger.warning("保存盘中快照失败: %s", e)

    cycle = analyze_one_date(dt, records, force=True)
    logger.info("情绪周期研判: %s", cycle)
    if cycle == "failed":
        return 1

    daily = analyze_daily_one_date(dt, records, force=True)
    logger.info("盘中买卖指导: %s", daily)
    if daily == "failed":
        return 1

    logger.info("===== 情绪周期盘初刷新完成 date=%s =====", dt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
