#!/usr/bin/env python3
"""竞价抢筹推荐度 v1 vs v2 胜率回测（不写入前端）。

用法:
  cd backend && python jobs/auction_grab_backtest.py
  python jobs/auction_grab_backtest.py --days 15
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.auction_grab import _enrich_close_and_next_change, fetch_and_cache_day
from services.auction_grab_backtest import format_backtest_report, run_recommendation_backtest
from utils.date_utils import get_recent_trading_dates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("auction_grab_backtest")


def _fetch_day(trade_date_dash: str) -> list[dict]:
    return fetch_and_cache_day(trade_date_dash, period=0)


def main():
    parser = argparse.ArgumentParser(description="竞价抢筹推荐度胜率回测")
    parser.add_argument("--days", type=int, default=10, help="回测最近 N 个交易日")
    args = parser.parse_args()

    dates_compact = get_recent_trading_dates(args.days)
    dates_dash = [
        f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in dates_compact
    ]

    logger.info("回测日期: %s", ", ".join(dates_dash))

    result = run_recommendation_backtest(
        dates_dash,
        period=0,
        fetch_items_fn=_fetch_day,
        enrich_returns_fn=_enrich_close_and_next_change,
    )

    report = format_backtest_report(result)
    print(report)
    logger.info("回测完成")


if __name__ == "__main__":
    main()
