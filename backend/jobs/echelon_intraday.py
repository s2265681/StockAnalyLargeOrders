#!/usr/bin/env python3
"""盘中高频任务：只刷新涨停梯队，不跑情绪周期和买卖指导。

供工作日盘中高频 cron 调用（约每 20-30 分钟一次）：
  python jobs/echelon_intraday.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.limit_up_echelon import build_echelon_one_date
from utils.date_utils import get_valid_trading_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("echelon_intraday")


def main() -> int:
    dt = get_valid_trading_date().replace("-", "")
    logger.info("===== 梯队盘中刷新开始 date=%s =====", dt)

    result = build_echelon_one_date(dt, force=True)
    logger.info("涨停梯队: %s", result)

    if result == "failed":
        logger.error("梯队构建失败")
        return 1

    logger.info("===== 梯队盘中刷新完成 date=%s =====", dt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
