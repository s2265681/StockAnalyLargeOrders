#!/usr/bin/env python3
"""
盘前资讯定时任务：拉取海外指数 + AI 摘要并写库。

用法：
  python jobs/market_brief_daily.py          # 今日
  python jobs/market_brief_daily.py force    # 强制重跑（同一天再跑一次）

建议 crontab（工作日 8:30）：
  30 8 * * 1-5 /path/to/run_market_brief.sh >> /path/to/logs/market_brief_job.log 2>&1
"""
import logging
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.market_brief_service import (
    fetch_overseas_indices,
    generate_ai_summary,
    save_brief,
    get_today_brief,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('market_brief_daily')


def main():
    force = len(sys.argv) > 1 and sys.argv[1].lower() in ('force', '1', 'yes')
    today = date.today().isoformat()

    if not force and get_today_brief() is not None:
        logger.info('今日 %s 已有摘要，跳过（传 force 强制重跑）', today)
        return

    logger.info('===== 盘前资讯任务 date=%s force=%s =====', today, force)

    logger.info('拉取海外指数...')
    overseas = fetch_overseas_indices()
    summary_parts = [f"{i['name']} {'+' if i['change_pct'] >= 0 else ''}{i['change_pct']}%" for i in overseas]
    logger.info('指数: %s', ', '.join(summary_parts))

    logger.info('生成 AI 摘要...')
    summary = generate_ai_summary(overseas)
    logger.info('摘要（前50字）: %s', summary[:50])

    save_brief(today, overseas, summary)
    logger.info('===== 任务完成 date=%s =====', today)


if __name__ == '__main__':
    main()
