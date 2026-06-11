"""
竞价筛选条件服务
从全市场竞价金额排行中筛选沪深A股主板票（排除ST）

stockapi 扫全市场，每种排序返回前50条；三种排序（委托额/成交额/开盘额）取并集，
可覆盖全市场竞价金额约前55-60支；过滤主板后通常得到40+支主板候选池。
"""
import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

_STOCKAPI_TOKEN = 'c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e'
_STOCKAPI_BASE = 'http://user.stockapi.com.cn/v1/base/jjqcUser'
_STOCKAPI_TYPES = [1, 2, 3]  # 1=委托额 2=成交额 3=开盘额

# 主板代码前缀（沪深A股主板，排除科创/创业/北交）
_MAIN_BOARD_PREFIXES = ('000', '001', '002', '003', '600', '601', '603', '605', '606')


def _fetch_stockapi_raw(trade_date: str, period: int = 0, api_type: int = 1) -> list[dict]:
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


def _is_main_board(code: str) -> bool:
    return code.startswith(_MAIN_BOARD_PREFIXES)


def _board_label(code: str) -> str:
    if code.startswith(('688', '689')):
        return '科创'
    if code.startswith(('300', '301', '302')):
        return '创业'
    if code.startswith(('8', '4')):
        return '北交'
    return '主板'


def get_main_board_top_auction(
    trade_date: str,
    period: int = 0,
    top_n: int = 60,
) -> list[dict]:
    """
    从全市场竞价金额前 N 支中，筛选沪深A股主板票（排除ST），按委托额降序返回。

    参数：
        trade_date  — YYYY-MM-DD 或 YYYYMMDD
        period      — 0=早盘竞价 1=尾盘
        top_n       — 目标主板股票数量（实际数量受数据源限制，通常40-45支）

    返回列表字段：
        code, name, board, auction_order_amt(万元), auction_trade_amt(万元),
        auction_change_pct(%)
    """
    if len(trade_date) == 8:
        trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

    # 并发拉三种排序，合并去重
    raw_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(_fetch_stockapi_raw, trade_date, period, t): t
            for t in _STOCKAPI_TYPES
        }
        for future in as_completed(futures):
            for r in future.result():
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

    # 按委托额排序后过滤：主板 + 非ST
    all_sorted = sorted(raw_map.values(), key=lambda x: x['auction_order_amt'], reverse=True)
    result = []
    for s in all_sorted:
        code = s['code']
        name = s['name']
        if not _is_main_board(code):
            continue
        if 'ST' in name.upper():
            continue
        s['board'] = _board_label(code)
        result.append(s)
        if len(result) >= top_n:
            break

    return result


def filter_by_auction_change(
    stocks: list[dict], min_pct: float = 2.0, max_pct: float = 7.0
) -> list[dict]:
    """按竞价涨幅区间过滤"""
    return [s for s in stocks if min_pct <= s.get('auction_change_pct', 0) <= max_pct]
