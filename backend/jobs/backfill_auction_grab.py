#!/usr/bin/env python3
"""竞价抢筹历史快照补录（早盘 period=0 / 尾盘 period=1）。

日常 cron（auction_grab_sync.py）只同步当天；本脚本用于回补缺失的历史交易日，
让「参数回测（近10日）」和历史列表有 DB 数据兜底。

对每个交易日 × 时段：
  1. fetch_and_cache_day  — DB 无数据则拉 stockapi 并入库（原始抢筹快照）
  2. _run_enrich          — 同步补全 昨日/收盘/次日涨幅 + 推荐评分，写库

用法：
  cd backend
  python jobs/backfill_auction_grab.py                 # 最近 10 个交易日，早盘+尾盘
  python jobs/backfill_auction_grab.py --days 15       # 最近 15 个交易日
  python jobs/backfill_auction_grab.py 20260710 20260724   # 指定区间（含两端）
  python jobs/backfill_auction_grab.py --period 0      # 仅早盘
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.auction_grab import fetch_and_cache_day, _run_enrich, _is_today_trading_date
from services import auction_grab_service as ag_store
from utils.date_utils import get_recent_trading_dates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_auction_grab")

# stockapi 每次调用间隔，避免触发限频（秒级≤10/s，日调用有额度）
_SLEEP_BETWEEN = 1.5


def _weekday_range(start: str, end: str) -> list[str]:
    d = datetime.strptime(start, "%Y%m%d")
    end_d = datetime.strptime(end, "%Y%m%d")
    out = []
    while d <= end_d:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return out


def backfill_one(date_compact: str, period: int) -> str:
    """补录单个 交易日×时段。返回状态字符串。"""
    trade_date_dash = ag_store.to_dash_date(date_compact)
    is_today = _is_today_trading_date(date_compact)

    items = fetch_and_cache_day(trade_date_dash, period)
    if not items:
        return "empty"

    # 同步富化（涨幅 + 评分），写库
    _run_enrich(date_compact, period, [dict(x) for x in items], trade_date_dash, is_today)
    return f"ok({len(items)})"


def main() -> int:
    parser = argparse.ArgumentParser(description="竞价抢筹历史快照补录")
    parser.add_argument("start", nargs="?", help="起始日 YYYYMMDD（省略则用 --days）")
    parser.add_argument("end", nargs="?", help="结束日 YYYYMMDD（默认=起始日）")
    parser.add_argument("--days", type=int, default=10, help="回补最近 N 个交易日（未指定区间时生效）")
    parser.add_argument("--period", type=int, choices=[0, 1], help="仅补某时段：0=早盘 1=尾盘（默认两者）")
    args = parser.parse_args()

    if args.start:
        end = args.end or args.start
        dates = _weekday_range(args.start, end)
    else:
        dates = get_recent_trading_dates(args.days)

    if not dates:
        logger.warning("无可补录的交易日")
        return 0

    periods = (args.period,) if args.period is not None else (0, 1)
    logger.info("补录 %s 个交易日 × 时段%s: %s ~ %s",
                len(dates), list(periods), dates[0], dates[-1])

    ok = empty = fail = 0
    for date_compact in dates:
        for period in periods:
            label = "早盘" if period == 0 else "尾盘"
            try:
                status = backfill_one(date_compact, period)
                if status.startswith("ok"):
                    ok += 1
                    logger.info("%s %s %s", date_compact, label, status)
                else:
                    empty += 1
                    logger.warning("%s %s 无数据", date_compact, label)
            except Exception as e:
                fail += 1
                logger.error("%s %s 异常: %s", date_compact, label, e)
            time.sleep(_SLEEP_BETWEEN)

    logger.info("补录完成：成功=%s 无数据=%s 失败=%s", ok, empty, fail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
