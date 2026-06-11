"""
竞价筛选条件服务
按竞价金额 Top-N 筛选 + 多维过滤条件
"""
import json
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

logger = logging.getLogger(__name__)

_STOCKAPI_TOKEN = 'c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e'
_STOCKAPI_BASE = 'http://user.stockapi.com.cn/v1/base/jjqcUser'

# 用三种排序合并，最大化覆盖竞价金额前60
_STOCKAPI_TYPES = [1, 2, 3]  # 1=委托额 2=成交额 3=开盘额


def _fetch_stockapi_raw(trade_date: str, period: int = 0, api_type: int = 1) -> list[dict]:
    """从 stockapi 拉单种排序竞价数据（原始行）"""
    url = (
        f"{_STOCKAPI_BASE}?tradeDate={trade_date}"
        f"&period={period}&type={api_type}&token={_STOCKAPI_TOKEN}"
    )
    cmd = ['curl', '-s', '--max-time', '15', '--insecure',
           '-H', 'Referer: http://user.stockapi.com.cn/bidding',
           '-H', 'User-Agent: Mozilla/5.0', url]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20)
        d = json.loads(r.stdout)
        if d.get('code') == 20000:
            return d.get('data') or []
    except Exception as e:
        logger.warning(f"stockapi type={api_type} 失败: {e}")
    return []


def fetch_top_auction_stocks(
    trade_date: str,
    period: int = 0,
    top_n: int = 60,
    exclude_st: bool = True,
) -> list[dict]:
    """
    拉取竞价金额前 top_n 的股票（三种排序合并取并集，再按委托额排序）。

    返回列表，每个元素：
        code, name, auction_order_amt(万元), auction_trade_amt(万元),
        auction_change_pct(%), is_st, board
    """
    # 并发拉三种排序
    raw_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(_fetch_stockapi_raw, trade_date, period, t): t
            for t in _STOCKAPI_TYPES
        }
        for future in as_completed(futures):
            rows = future.result()
            for r in rows:
                code = str(r.get('code', '')).zfill(6)
                if not code:
                    continue
                cur = raw_map.get(code, {})
                raw_map[code] = {
                    'code': code,
                    'name': r.get('name') or cur.get('name', ''),
                    'auction_order_amt': max(
                        float(r.get('qcwtje') or 0) / 10000,
                        cur.get('auction_order_amt', 0),
                    ),
                    'auction_trade_amt': max(
                        float(r.get('qccje') or 0) / 10000,
                        cur.get('auction_trade_amt', 0),
                    ),
                    'auction_change_pct': float(r.get('qczf') or 0),
                }

    if not raw_map:
        return []

    stocks = sorted(raw_map.values(), key=lambda x: x['auction_order_amt'], reverse=True)

    # 补充辅助字段
    for s in stocks:
        code = s['code']
        name = s['name']
        s['is_st'] = 'ST' in name.upper()
        # 板块：科创 68/688, 创业 30/300/301, 北交 8/4, 主板其余
        if code.startswith(('688', '68')):
            s['board'] = '科创'
        elif code.startswith(('300', '301', '30')):
            s['board'] = '创业'
        elif code.startswith(('8', '4')):
            s['board'] = '北交'
        else:
            s['board'] = '主板'

    if exclude_st:
        stocks = [s for s in stocks if not s['is_st']]

    return stocks[:top_n]


def filter_by_board(stocks: list[dict], boards: list[str]) -> list[dict]:
    """按板块过滤，boards=['主板','创业','科创']"""
    board_set = set(boards)
    return [s for s in stocks if s.get('board') in board_set]


def filter_by_auction_change(
    stocks: list[dict], min_pct: float = 2.0, max_pct: float = 7.0
) -> list[dict]:
    """按竞价涨幅区间过滤"""
    return [s for s in stocks if min_pct <= s.get('auction_change_pct', 0) <= max_pct]
