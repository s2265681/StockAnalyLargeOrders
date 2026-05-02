"""
日期工具模块
用东方财富日K接口校验交易日，避免 akshare 慢查询
"""
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 简单内存缓存：date_str → bool（是否为交易日）
_trading_day_cache: dict = {}


def _is_trading_day_eastmoney(date_str: str) -> bool:
    """通过东方财富日K接口验证某日是否为交易日"""
    if date_str in _trading_day_cache:
        return _trading_day_cache[date_str]

    date_compact = date_str.replace('-', '')
    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    params = {
        'secid': '0.000001',
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52',
        'klt': 101,
        'fqt': 1,
        'beg': date_compact,
        'end': date_compact,
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        klines = data.get('data', {})
        if klines:
            klines = klines.get('klines', [])
        result = bool(klines)
    except Exception:
        # 接口不可达时，退化为工作日判断
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        result = dt.weekday() < 5

    _trading_day_cache[date_str] = result
    return result


def get_valid_trading_date(target_date=None, max_days_back=30):
    """
    获取最近的有效交易日
    - target_date: 'YYYY-MM-DD' 字符串或 datetime，默认今天
    - 先排除周末，再用东方财富 K 线接口验证节假日
    """
    try:
        if target_date is None:
            current_date = datetime.now()
        elif isinstance(target_date, str):
            current_date = datetime.strptime(target_date, '%Y-%m-%d')
        else:
            current_date = target_date

        for i in range(max_days_back):
            check_date = current_date - timedelta(days=i)
            if check_date.weekday() >= 5:
                continue
            date_str = check_date.strftime('%Y-%m-%d')
            if _is_trading_day_eastmoney(date_str):
                return date_str

        # 兜底：返回最近工作日
        fallback = current_date
        while fallback.weekday() >= 5:
            fallback -= timedelta(days=1)
        return fallback.strftime('%Y-%m-%d')

    except Exception as e:
        logger.error(f"获取有效交易日失败: {e}")
        return datetime.now().strftime('%Y-%m-%d')


def get_next_trading_date(current_date: str, forward: bool = True) -> dict:
    """获取下一个或上一个交易日"""
    try:
        current_dt = datetime.strptime(current_date, '%Y-%m-%d')
        today = datetime.now().date()

        if forward:
            next_dt = current_dt + timedelta(days=1)
            if next_dt.date() > today:
                return {'date': current_date, 'is_latest': True, 'message': '已经是最新的交易日'}
            valid = get_valid_trading_date(next_dt)
            if datetime.strptime(valid, '%Y-%m-%d').date() > today:
                return {'date': current_date, 'is_latest': True, 'message': '已经是最新的交易日'}
            return {'date': valid, 'is_latest': False, 'message': f'切换到交易日: {valid}'}
        else:
            prev_dt = current_dt - timedelta(days=1)
            valid = get_valid_trading_date(prev_dt)
            return {'date': valid, 'is_latest': False, 'message': f'切换到交易日: {valid}'}

    except Exception as e:
        logger.error(f"交易日导航失败: {e}")
        return {'date': current_date, 'is_latest': False, 'message': str(e)}


def validate_and_get_trading_date(date_param: str | None) -> str:
    """验证并返回有效交易日（不传则返回最近交易日）"""
    if not date_param:
        return get_valid_trading_date()
    try:
        datetime.strptime(date_param, '%Y-%m-%d')
        return get_valid_trading_date(date_param)
    except ValueError:
        logger.warning(f"无效日期格式: {date_param}")
        return get_valid_trading_date()
