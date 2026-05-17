#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""每日定时任务：生成最新交易日的周期研判分析。

用法：
  python jobs/emotion_cycle_daily.py [YYYYMMDD] [force]

  YYYYMMDD  可选，目标交易日；不指定则使用 StockAPI 返回的最新交易日
  force     可选，若为 1/yes/true 则忽略 DB 缓存强制重新生成

例子：
  python jobs/emotion_cycle_daily.py                  # 生成最新交易日
  python jobs/emotion_cycle_daily.py 20260515         # 生成指定日期
  python jobs/emotion_cycle_daily.py 20260515 force   # 强制重新生成
"""

import sys
import os
import logging
from datetime import datetime

# Add backend to path so we can import routes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

from routes.emotion_cycle import analyze_one_date, _fetch_emotion_records
from utils.date_utils import get_valid_trading_date

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StockAPI:
    """StockAPI 包装器 - 获取情绪周期数据及交易日信息"""

    def get_latest_trading_day(self) -> str:
        """获取最新交易日，格式 YYYYMMDD

        通过 get_valid_trading_date 检查是否为交易日。

        Returns:
            str: 日期字符串，格式 YYYYMMDD

        Raises:
            Exception: 如果无法确定最新交易日
        """
        try:
            valid_date = get_valid_trading_date()  # 返回 'YYYY-MM-DD' 格式
            return valid_date.replace('-', '')  # 转为 YYYYMMDD
        except Exception as e:
            logger.error(f"获取最新交易日失败: {e}")
            raise

    def fetch_all_emotion_records(self) -> list:
        """从 StockAPI 拉取所有情绪周期记录

        Returns:
            list: 情绪周期数据列表，每条记录为 dict

        Raises:
            Exception: 如果 StockAPI 请求失败
        """
        try:
            records = _fetch_emotion_records()
            return records
        except Exception as e:
            logger.error(f"从 StockAPI 获取情绪周期数据失败: {e}")
            raise


def main(target_date=None, force=False):
    """为目标交易日生成周期研判。

    Args:
        target_date: 目标交易日，格式 'YYYYMMDD'；若 None 则使用 StockAPI 最新交易日
        force: 若 True，强制重新生成即使 DB 已有

    Returns:
        None

    Raises:
        SystemExit(1) 若 StockAPI 拉取失败或单日分析失败
    """
    # 1. 确定目标日期
    if target_date is None:
        try:
            api = StockAPI()
            target_date = api.get_latest_trading_day()
            logger.info(f"使用 StockAPI 最新交易日: {target_date}")
        except Exception as e:
            logger.error(f"获取最新交易日失败: {e}")
            sys.exit(1)
    else:
        logger.info(f"使用手动指定的目标日期: {target_date}")

    # 2. 获取全部历史记录（供 analyze_one_date 做趋势上下文）
    try:
        api = StockAPI()
        all_records = api.fetch_all_emotion_records()
        logger.info(f"从 StockAPI 获取到 {len(all_records)} 条情绪周期记录")
    except Exception as e:
        logger.error(f"拉取情绪周期数据失败: {e}")
        sys.exit(1)

    # 3. 调用 analyze_one_date 生成分析
    try:
        result = analyze_one_date(target_date, all_records, force=force)
        logger.info(f"analyze_one_date 返回: {result} (target_date={target_date})")

        if result == 'failed':
            logger.error(f"{target_date} 分析失败")
            sys.exit(1)
        elif result == 'skipped':
            logger.info(f"{target_date} 已存在于数据库，跳过")
        elif result == 'saved':
            logger.info(f"{target_date} 周期研判已保存")

    except Exception as e:
        logger.error(f"analyze_one_date 异常: {e}")
        sys.exit(1)


if __name__ == '__main__':
    target_date = None
    force = False

    # Parse command line arguments
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    if len(sys.argv) > 2:
        force_arg = sys.argv[2].lower()
        force = force_arg in ('1', 'yes', 'true', 'force')

    main(target_date=target_date, force=force)
