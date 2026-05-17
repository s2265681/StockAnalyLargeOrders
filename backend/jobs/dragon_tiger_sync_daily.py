#!/usr/bin/env python3
"""仅同步龙虎榜列表与席位（不生成 AI）。

用法：
  python jobs/dragon_tiger_sync_daily.py 20260513 20260514
  python jobs/dragon_tiger_sync_daily.py 20260513 force
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.dragon_tiger import sync_dragon_tiger_for_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dragon_tiger_sync_daily")


def main():
    args = [a for a in sys.argv[1:] if a]
    force = any(a.lower() in ("force", "1", "yes", "true") for a in args)
    dates = [a for a in args if a.isdigit() and len(a) == 8]
    if not dates:
        logger.error("请提供至少一个日期 YYYYMMDD")
        sys.exit(1)

    for dt in dates:
        result = sync_dragon_tiger_for_date(dt, force=force)
        logger.info("sync date=%s result=%s", dt, result)
        if result.get("stocks", 0) == 0:
            sys.exit(2)


if __name__ == "__main__":
    main()
