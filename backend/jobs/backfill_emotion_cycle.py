#!/usr/bin/env python3
"""历史周期研判倒序回填（逐日 analyze_one_date，质量更稳、耗时更长）。

用法：
  python jobs/backfill_emotion_cycle.py        # 回填全部历史，从新到旧，跳过已有
  python jobs/backfill_emotion_cycle.py force  # 强制重生成全部
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.emotion_cycle import (
    _fetch_emotion_records,
    _record_date_key,
    analyze_one_date,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_emotion_cycle")


def main(force: bool = False):
    records = _fetch_emotion_records()
    if not records:
        logger.error("未获取到情绪周期数据")
        sys.exit(1)

    ordered = sorted(
        (r for r in records if isinstance(r, dict) and _record_date_key(r)),
        key=_record_date_key,
    )
    dates_desc = [_record_date_key(r) for r in reversed(ordered)]
    logger.info(
        f"准备倒序回填 {len(dates_desc)} 个交易日: {dates_desc[0]} → {dates_desc[-1]}"
    )

    saved = skipped = failed = 0
    for i, dt in enumerate(dates_desc):
        try:
            status = analyze_one_date(dt, records, force=force)
        except Exception as e:
            logger.error(f"{dt} 异常: {e}")
            failed += 1
            time.sleep(2)
            continue
        if status == "saved":
            saved += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1
        if i < len(dates_desc) - 1:
            time.sleep(2)

    logger.info(f"回填完成：保存={saved} 跳过={skipped} 失败={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    force_arg = len(sys.argv) > 1 and sys.argv[1].lower() in ("force", "1", "yes", "true")
    main(force=force_arg)
