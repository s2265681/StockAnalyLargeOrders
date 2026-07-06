#!/usr/bin/env python3
"""板块抢筹日快照同步。

早盘 09:30-10:00 每 5 分钟；盘中 10:00-15:00 每 30 分钟（由 crontab 调度）。
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.sector_grab import fetch_and_cache_sectors
from utils.date_utils import get_valid_trading_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sector_grab_sync")


def main() -> int:
    parser = argparse.ArgumentParser(description="板块抢筹快照同步")
    parser.parse_args()
    trade_date = get_valid_trading_date()
    sectors = fetch_and_cache_sectors(trade_date)
    count = len(sectors) if sectors else 0
    logger.info("板块抢筹同步完成 date=%s sectors=%s", trade_date, count)
    if count == 0:
        logger.warning("未拉取到板块数据 date=%s", trade_date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
