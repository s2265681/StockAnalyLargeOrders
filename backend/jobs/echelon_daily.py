#!/usr/bin/env python3
"""
收盘后定时任务：涨停池 + AI 分组 + 写入数据库。

用法：
  python jobs/echelon_daily.py              # 最新交易日，有缓存则跳过
  python jobs/echelon_daily.py 20260515     # 指定日期
  python jobs/echelon_daily.py force        # 最新交易日强制重跑
  python jobs/echelon_daily.py 20260515 force

建议 crontab（工作日 16:00，A 股收盘后）：
  0 16 * * 1-5 /Users/mac/Github/NiuNIuNiu/backend/jobs/run_echelon.sh \
    >> /Users/mac/Github/NiuNIuNiu/echelon_job.log 2>&1
"""
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.limit_up_echelon import build_echelon_one_date, _default_echelon_dt
from utils.date_utils import get_valid_trading_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("echelon_daily")


def _resolve_trading_date(arg: str | None) -> str:
    if arg and arg.isdigit() and len(arg) == 8:
        return arg
    try:
        return get_valid_trading_date().replace("-", "")
    except Exception:
        return _default_echelon_dt()


def main():
    args = [a for a in sys.argv[1:] if a]
    force = any(a.lower() in ("force", "1", "yes", "true") for a in args)
    date_args = [a for a in args if a.isdigit() and len(a) == 8]
    dt = _resolve_trading_date(date_args[0] if date_args else None)

    logger.info("===== 涨停梯队离线任务 date=%s force=%s =====", dt, force)
    result = build_echelon_one_date(dt, force=force)
    logger.info("===== 任务结束 date=%s result=%s =====", dt, result)

    if result == "failed":
        sys.exit(1)
    if result == "empty":
        sys.exit(2)


if __name__ == "__main__":
    main()
