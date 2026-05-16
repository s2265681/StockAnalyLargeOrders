#!/usr/bin/env python3
"""
收盘后定时任务：自动获取涨停梯队数据 + AI 分组 + 写入数据库
用法：
  python jobs/echelon_daily.py          # 跑今天
  python jobs/echelon_daily.py 20260515 # 跑指定日期

建议 crontab：
  30 15 * * 1-5 cd /Users/mac/Github/NiuNIuNiu/backend && venv/bin/python jobs/echelon_daily.py >> ../echelon_job.log 2>&1
"""
import json
import logging
import os
import sys
import time
from datetime import datetime
from collections import Counter

# 项目根路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.limit_up_echelon import (
    _fetch_ths_hot_stocks,
    _build_stocks_from_df,
    _claude_group_labels_for_stocks,
    _apply_group_labels,
)
from services.theme_service import save_ai_grouping_result, get_limit_up_stocks_by_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("echelon_daily")


def run(dt: str):
    logger.info(f"===== 开始收盘定时任务 date={dt} =====")

    # 检查是否已有数据
    existing = get_limit_up_stocks_by_date(dt)
    if existing:
        logger.info(f"数据库已有 {len(existing)} 条记录 (date={dt})，跳过")
        return

    # 1. 获取涨停池
    import akshare as ak
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_zt = pool.submit(ak.stock_zt_pool_em, date=dt)
        fut_ths = pool.submit(_fetch_ths_hot_stocks)
        df = fut_zt.result()
        ths_hot_list, ths_hot_map = fut_ths.result()

    if df is None or df.empty:
        logger.warning(f"无涨停数据 (date={dt})")
        return

    stocks = _build_stocks_from_df(df, ths_hot_map)
    logger.info(f"获取到 {len(stocks)} 只涨停股")

    # 2. AI 分组
    t0 = time.time()
    group_result = _claude_group_labels_for_stocks(stocks)
    elapsed = time.time() - t0
    logger.info(f"AI 分组完成，耗时 {elapsed:.1f}s")

    if not group_result.get("labels"):
        logger.error("AI 分组结果为空，任务失败")
        return

    # 3. 应用分组到 stocks
    _apply_group_labels(stocks, group_result)

    # 4. 写入数据库
    save_ai_grouping_result(dt, stocks, group_result)
    logger.info(f"===== 定时任务完成 date={dt} =====")


if __name__ == "__main__":
    dt = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d")
    run(dt)
