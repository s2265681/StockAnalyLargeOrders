#!/usr/bin/env python3
"""
历史涨停数据补录脚本
用法：
  python jobs/backfill_echelon.py 20260401 20260512   # 补录指定区间（含两端）
  python jobs/backfill_echelon.py 20260501             # 补录单日
"""
import sys
import os
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill")


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5  # 0=Mon, 4=Fri


def date_range(start: str, end: str):
    d = datetime.strptime(start, "%Y%m%d")
    end_d = datetime.strptime(end, "%Y%m%d")
    while d <= end_d:
        if is_weekday(d):
            yield d.strftime("%Y%m%d")
        d += timedelta(days=1)


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python backfill_echelon.py <start_date> [end_date]")
        print("日期格式: YYYYMMDD")
        sys.exit(1)

    start = args[0]
    end = args[1] if len(args) > 1 else start
    dates = list(date_range(start, end))

    logger.info(f"准备补录 {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}")

    from routes.limit_up_echelon import build_echelon_one_date

    success, skip, fail = 0, 0, 0
    for dt in dates:
        logger.info(f"--- 处理 {dt} ---")
        try:
            result = build_echelon_one_date(dt, force=True)
            if result == "saved":
                success += 1
            elif result == "skipped":
                skip += 1
            elif result == "empty":
                logger.warning(f"{dt} 涨停池为空")
                fail += 1
            else:
                logger.error(f"{dt} 失败: {result}")
                fail += 1
        except Exception as e:
            logger.error(f"{dt} 异常: {e}")
            fail += 1
        time.sleep(2)  # 避免请求过快

    logger.info(f"补录完成：成功={success} 跳过={skip} 失败={fail}")


if __name__ == "__main__":
    main()
