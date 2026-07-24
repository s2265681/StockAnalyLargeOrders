#!/usr/bin/env python3
"""竞价抢筹日快照同步（早盘 period=0 / 尾盘 period=1）。

用法：
  python jobs/auction_grab_sync.py           # 早盘+尾盘各拉一次
  python jobs/auction_grab_sync.py morning   # 仅早盘
  python jobs/auction_grab_sync.py tail      # 仅尾盘
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.auction_grab import fetch_and_cache_day
from services import auction_grab_service as ag_store
from utils.date_utils import get_valid_trading_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("auction_grab_sync")

_PERIOD = {"morning": 0, "tail": 1, "0": 0, "1": 1}


def _today_dash() -> str:
    return get_valid_trading_date()


def sync_period(trade_date: str, period: int) -> int:
    label = "早盘" if period == 0 else "尾盘"
    items = fetch_and_cache_day(trade_date, period)
    count = len(items) if items else 0
    if count == 0:
        logger.warning("%s period=%s 未取到数据（接口空/超限/异常）", label, period)
        return 0
    # 校验确实落库：DB 故障时 replace_snapshot 会静默返回 0，
    # 仅靠 len(items) 会误报「入库成功」，故此处直查 DB 兜底。
    date_compact = ag_store.to_compact_date(trade_date)
    if not ag_store.snapshot_exists(date_compact, period):
        logger.error("%s period=%s 取到 %s 条但未落库（DB 写入失败？请检查 MySQL）",
                     label, period, count)
        return 0
    logger.info("%s period=%s 入库 %s 条", label, period, count)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="竞价抢筹快照同步")
    parser.add_argument(
        "mode",
        nargs="?",
        default="all",
        choices=["all", "morning", "tail", "0", "1"],
        help="all=早晚盘；morning/tail 或 0/1",
    )
    args = parser.parse_args()
    trade_date = _today_dash()

    if args.mode == "all":
        periods = (0, 1)
    else:
        periods = (_PERIOD[args.mode],)

    total = 0
    for period in periods:
        total += sync_period(trade_date, period)

    if total == 0:
        logger.warning("未拉取到任何竞价抢筹数据 date=%s", trade_date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
