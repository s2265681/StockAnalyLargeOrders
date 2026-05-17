#!/usr/bin/env python3
"""定时任务前置检查：今日是否交易日。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.date_utils import is_today_trading_day


def main() -> int:
    if is_today_trading_day():
        return 0
    print("今日非交易日，跳过任务")
    return 2  # 2 = 跳过（非失败）


if __name__ == "__main__":
    sys.exit(main())
