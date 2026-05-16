"""
竞价抢筹 API
数据来源: stockapi.com.cn 竞价抢筹接口
"""
import logging
import time
from datetime import datetime, timedelta
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response

logger = logging.getLogger(__name__)

auction_grab_bp = Blueprint('auction_grab', __name__)

_STOCKAPI_TOKEN = 'c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e'
_STOCKAPI_BASE = 'http://user.stockapi.com.cn/v1/base/jjqcUser'

# 缓存
_cache = {}
_CACHE_TTL = 120

# type 映射：前端排序key -> stockapi type 参数
_SORT_TYPE_MAP = {
    'wtje': 1,   # 委托金额
    'cjje': 2,   # 成交金额
    'kpje': 3,   # 开盘金额
    'zf': 1,     # 涨幅（API 无涨幅排序，默认用委托金额，前端再排）
}


def _get_last_trading_day():
    d = datetime.now()
    dow = d.weekday()
    if dow == 5:
        d -= timedelta(days=1)
    elif dow == 6:
        d -= timedelta(days=2)
    return d.strftime('%Y%m%d')


def _format_date(dt_str):
    """YYYYMMDD -> YYYY-MM-DD"""
    if len(dt_str) == 8:
        return f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
    return dt_str


def _fetch_from_stockapi(trade_date, period, api_type):
    """
    从 stockapi 获取竞价抢筹数据
    trade_date: YYYY-MM-DD
    period: 0=早盘 1=尾盘
    api_type: 1=委托金额排 2=成交金额排 3=开盘金额排
    """
    import subprocess
    import json as _json

    url = (
        f"{_STOCKAPI_BASE}?tradeDate={trade_date}"
        f"&period={period}&type={api_type}&token={_STOCKAPI_TOKEN}"
    )
    cmd = [
        'curl', '-s', '--max-time', '15', '--insecure',
        '-H', 'Referer: http://user.stockapi.com.cn/bidding',
        '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0 or not result.stdout.strip():
            logger.error(f"stockapi curl 失败: rc={result.returncode}")
            return None
        resp = _json.loads(result.stdout)
        if resp.get('code') != 20000:
            logger.warning(f"stockapi 返回错误: {resp.get('msg')}")
            return None
        return resp.get('data', [])
    except Exception as e:
        logger.error(f"stockapi 请求异常: {type(e).__name__}: {e}")
        return None


@auction_grab_bp.route('/api/v1/auction-grab', methods=['GET'])
def get_auction_grab():
    """
    获取竞价抢筹数据
    参数:
        period: 0=早盘竞价抢筹(默认) 1=尾盘抢筹
        sort: wtje=委托金额(默认) cjje=成交金额 kpje=开盘金额 zf=涨幅
        dt: 日期(YYYYMMDD)，默认当天
    """
    period = request.args.get('period', '0')
    sort_by = request.args.get('sort', 'wtje')
    dt = request.args.get('dt', _get_last_trading_day())
    trade_date = _format_date(dt)

    # 确定 API type 参数
    api_type = _SORT_TYPE_MAP.get(sort_by, 1)

    cache_key = f"{dt}_{period}_{api_type}"
    now = time.time()

    cached = _cache.get(cache_key)
    if cached and (now - cached['ts']) < _CACHE_TTL:
        raw_data = cached['data']
    else:
        raw_data = _fetch_from_stockapi(trade_date, int(period), api_type)
        if raw_data is None:
            return v1_error_response('数据源暂不可用，请稍后重试')
        _cache[cache_key] = {'ts': now, 'data': raw_data}

    # 如果是按涨幅排序，需要前端排
    if sort_by == 'zf':
        raw_data = sorted(raw_data, key=lambda x: x.get('qczf', 0) or 0, reverse=True)

    # 格式化输出
    items = []
    for r in raw_data:
        items.append({
            'code': r.get('code', ''),
            'name': r.get('name', ''),
            'open_amount': round(r.get('openAmt', 0) / 10000, 2),
            'grab_change_pct': r.get('qczf', 0),
            'grab_turnover': round(r.get('qccje', 0) / 10000, 2),
            'grab_order_amount': round(r.get('qcwtje', 0) / 10000, 2),
            'date': r.get('time', trade_date),
        })

    return v1_success_response(data={
        'items': items,
        'total': len(items),
        'date': dt,
        'period': int(period),
        'sort': sort_by,
    })
