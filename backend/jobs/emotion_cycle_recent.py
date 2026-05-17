#!/usr/bin/env python3
"""收盘后任务：强制重跑最近 3 个交易日的周期研判。

用法：
  python jobs/emotion_cycle_recent.py

建议 crontab（工作日 16:00，A 股收盘后）：
  0 16 * * 1-5 /Users/mac/Github/NiuNIuNiu/backend/jobs/run_emotion_cycle.sh recent \
    >> /Users/mac/Github/NiuNIuNiu/emotion_cycle_job.log 2>&1
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.emotion_cycle import _fetch_emotion_records, run_batch_emotion_analysis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("emotion_cycle_recent")


def main():
    logger.info("===== 开始重跑最近 3 个交易日周期研判 =====")
    records = _fetch_emotion_records()
    if not records:
        logger.error("未获取到情绪周期数据")
        sys.exit(1)

    try:
        result = run_batch_emotion_analysis(records, force_mode="recent")
    except Exception as e:
        logger.error(f"最近 3 日研判失败: {e}")
        sys.exit(1)

    logger.info(f"===== 完成: {result} =====")


if __name__ == "__main__":
    main()
