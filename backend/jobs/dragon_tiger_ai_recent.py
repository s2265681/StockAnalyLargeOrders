#!/usr/bin/env python3
"""收盘后任务：补全最近 5 个交易日的龙虎榜 AI 解读（缺失则生成）。

用法：
  python jobs/dragon_tiger_ai_recent.py
  python jobs/dragon_tiger_ai_recent.py force

手动补全近 5 日时使用；日常定时请用 dragon_tiger_ai_daily.py（18:00）。
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.dragon_tiger import run_dragon_tiger_ai_for_date, sync_dragon_tiger_for_date
from utils.date_utils import get_recent_trading_dates

# 仅同步榜单/席位、不跑 AI 的日期（YYYYMMDD）
SYNC_ONLY_DATES = frozenset({"20260513", "20260514"})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dragon_tiger_ai_recent")

VISIBLE_DAYS = 5


def main():
    args = [a.lower() for a in sys.argv[1:] if a]
    force = any(a in ("force", "1", "yes", "true") for a in args)
    dates = get_recent_trading_dates(VISIBLE_DAYS)
    if not dates:
        logger.error("未能解析最近交易日")
        sys.exit(1)

    logger.info("===== 龙虎榜 AI 近 %s 日补全 force=%s dates=%s =====", VISIBLE_DAYS, force, dates)
    total_failed = 0
    for dt in dates:
        if dt in SYNC_ONLY_DATES:
            result = sync_dragon_tiger_for_date(dt, force=force)
            logger.info("date=%s sync_only result=%s", dt, result)
            if result.get("stocks", 0) == 0:
                logger.warning("date=%s 无龙虎榜数据", dt)
            continue
        result = run_dragon_tiger_ai_for_date(dt, force=force)
        logger.info("date=%s result=%s", dt, result)
        total_failed += result.get("failed", 0)
        if result.get("total", 0) == 0:
            logger.warning("date=%s 无龙虎榜数据", dt)

    logger.info("===== 近 %s 日补全结束 failed=%s =====", VISIBLE_DAYS, total_failed)
    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
