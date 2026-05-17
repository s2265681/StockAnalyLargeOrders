#!/usr/bin/env python3
"""批量强制补全周期研判（分批调用 Claude，适合历史全量）。

用法：
  python jobs/backfill_emotion_cycle_batch.py force   # 强制重跑全部交易日
  python jobs/backfill_emotion_cycle_batch.py         # 仅补缺失日期
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
logger = logging.getLogger("backfill_emotion_cycle_batch")


def main(force_all: bool = False):
    logger.info("===== 开始批量周期研判补全 =====")
    records = _fetch_emotion_records()
    if not records:
        logger.error("未获取到情绪周期数据")
        sys.exit(1)

    force_mode = "all" if force_all else "missing"
    logger.info(f"记录数={len(records)}, force_mode={force_mode}")

    try:
        result = run_batch_emotion_analysis(records, force_mode=force_mode)
    except Exception as e:
        logger.error(f"批量补全失败: {e}")
        sys.exit(1)

    logger.info(f"===== 补全完成: {result} =====")
    if result.get("analyzed", 0) == 0 and force_mode == "all":
        logger.warning("全量强制模式下未写入任何记录，请检查日志")


if __name__ == "__main__":
    force = len(sys.argv) > 1 and sys.argv[1].lower() in ("force", "1", "yes", "true", "all")
    main(force_all=force)
