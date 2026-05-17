#!/usr/bin/env python3
"""盘中刷新：涨停梯队 + 情绪周期研判 + 当天买卖指导（均强制覆盖当日）。

供工作日盘中 cron 调用：
  python jobs/intraday_refresh.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.emotion_cycle import (
    _fetch_emotion_records,
    analyze_daily_one_date,
    analyze_one_date,
)
from routes.limit_up_echelon import build_echelon_one_date
from utils.date_utils import get_valid_trading_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("intraday_refresh")


def _today_compact() -> str:
    return get_valid_trading_date().replace("-", "")


def main() -> int:
    dt = _today_compact()
    logger.info("===== 盘中刷新开始 date=%s =====", dt)

    echelon = build_echelon_one_date(dt, force=True)
    logger.info("涨停梯队: %s", echelon)
    if echelon == "failed":
        return 1

    records = _fetch_emotion_records()
    if not records:
        logger.error("未获取到情绪周期数据")
        return 1

    cycle = analyze_one_date(dt, records, force=True)
    logger.info("情绪周期研判: %s", cycle)
    if cycle == "failed":
        return 1

    daily = analyze_daily_one_date(dt, records, force=True)
    logger.info("盘中买卖指导: %s", daily)
    if daily == "failed":
        return 1

    logger.info("===== 盘中刷新完成 date=%s =====", dt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
