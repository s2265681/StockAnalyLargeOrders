#!/usr/bin/env python3
"""收盘后任务：强制重跑最近 3 个交易日的当天分析（含买卖点、昨日复盘）。

用法：
  python jobs/emotion_daily_analysis_recent.py

建议与周期研判一并调度：
  run_emotion_cycle.sh recent && run_emotion_cycle.sh daily-recent
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.emotion_cycle import _fetch_emotion_records, run_batch_daily_analysis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("emotion_daily_analysis_recent")


def main():
    logger.info("===== 开始重跑最近 3 个交易日当天分析 =====")
    records = _fetch_emotion_records()
    if not records:
        logger.error("未获取到情绪周期数据")
        sys.exit(1)

    try:
        result = run_batch_daily_analysis(records, force_mode="recent")
    except Exception as e:
        logger.error(f"最近 3 日当天分析失败: {e}")
        sys.exit(1)

    logger.info(f"===== 完成: {result} =====")
    if result.get("failed", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
