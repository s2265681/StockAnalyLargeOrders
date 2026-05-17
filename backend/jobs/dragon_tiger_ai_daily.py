#!/usr/bin/env python3
"""
收盘后定时任务：为龙虎榜上榜股批量生成 AI 资金解读并入库。

用法：
  python jobs/dragon_tiger_ai_daily.py              # 最新交易日，有缓存则跳过
  python jobs/dragon_tiger_ai_daily.py 20260515     # 指定日期
  python jobs/dragon_tiger_ai_daily.py force        # 最新交易日强制重跑
  python jobs/dragon_tiger_ai_daily.py 20260515 force

建议 crontab（工作日 18:00，补全当日并清理 7 天前数据）：
  0 18 * * 1-5 /Users/mac/Github/NiuNIuNiu/backend/jobs/run_dragon_tiger.sh \
    >> /Users/mac/Github/NiuNIuNiu/dragon_tiger_job.log 2>&1
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.dragon_tiger import run_dragon_tiger_ai_for_date
from services.dragon_tiger_service import cleanup_dragon_tiger_older_than
from utils.date_utils import get_valid_trading_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dragon_tiger_ai_daily")


def _resolve_trading_date(arg: str | None) -> str:
    if arg and arg.isdigit() and len(arg) == 8:
        return arg
    try:
        return get_valid_trading_date().replace("-", "")
    except Exception:
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d")


def main():
    args = [a for a in sys.argv[1:] if a]
    force = any(a.lower() in ("force", "1", "yes", "true") for a in args)
    date_args = [a for a in args if a.isdigit() and len(a) == 8]
    dt = _resolve_trading_date(date_args[0] if date_args else None)

    logger.info("===== 龙虎榜 AI 离线任务 date=%s force=%s =====", dt, force)
    result = run_dragon_tiger_ai_for_date(dt, force=force)
    logger.info("当日补全结果: %s", result)

    cleanup = cleanup_dragon_tiger_older_than()
    logger.info("===== 任务结束 cleanup=%s =====", cleanup)

    if result.get("failed", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
