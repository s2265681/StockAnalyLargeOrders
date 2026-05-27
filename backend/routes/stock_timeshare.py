"""
股票分时数据接口模块
数据源：东方财富（统一经 EastMoneyFreeSource）
"""
import logging
from flask import Blueprint, request
from utils.cache import cache_with_timeout
from utils.response import success_response, error_response, v1_success_response, v1_error_response
from utils.date_utils import validate_and_get_trading_date
from utils.stock_utils import normalize_stock_code
from routes.stock_basic import get_stock_basic_data
from services.eastmoney_free import EastMoneyFreeSource

logger = logging.getLogger(__name__)

stock_timeshare_bp = Blueprint('stock_timeshare', __name__)

_em_source = EastMoneyFreeSource()

_AUCTION_SKIP = ('09:15', '09:29')  # 集合竞价时段 [09:15, 09:30)


def _skip_auction(time_key: str) -> bool:
    if len(time_key) < 5:
        return False
    t = time_key[:5]
    return _AUCTION_SKIP[0] <= t < '09:30'


def _filter_timeshare_rows(rows):
    """过滤集合竞价，转为 /api/stock/timeshare 响应字段"""
    out = []
    for item in rows or []:
        time_str = item.get('time', '')
        if _skip_auction(time_str):
            continue
        out.append({
            'time': time_str,
            'price': item['price'],
            'volume': item.get('volume', 0),
            'amount': item.get('amount', 0),
            'avg_price': item.get('avg_price', item['price']),
        })
    return out


def get_eastmoney_timeshare_data(code):
    """分时 + 统计（复用 EastMoneyFreeSource，含 curl/eventlet 兜底）"""
    try:
        normalized = normalize_stock_code(code)
        if not normalized:
            return None

        rows = _filter_timeshare_rows(_em_source.get_timeshare(normalized))
        if len(rows) < 10:
            logger.warning(f"分时数据不足: {normalized} ({len(rows)} 点)")
            return None

        stock_basic = get_stock_basic_data(normalized)
        prices = [d['price'] for d in rows]
        volumes = [d['volume'] for d in rows]

        return {
            'timeshare': rows,
            'statistics': {
                'current_price': stock_basic['current_price'],
                'yesterdayClose': stock_basic['yesterday_close'],
                'change_percent': stock_basic['change_percent'],
                'change_amount': stock_basic['change_amount'],
                'high': max(prices) if prices else stock_basic['high'],
                'low': min(prices) if prices else stock_basic['low'],
                'volume': sum(volumes) if volumes else stock_basic['volume'],
                'turnover': stock_basic['turnover'],
            },
        }
    except Exception as e:
        logger.warning(f"分时数据获取失败 {code}: {e}")
        return None


def get_eastmoney_l2_tick_data(code):
    """当日逐笔大单（≥20 万），复用 get_tick_details"""
    try:
        normalized = normalize_stock_code(code)
        if not normalized:
            return None

        tick_resp = _em_source.get_tick_details(normalized) or {}
        details = tick_resp.get('details') or []
        if len(details) <= 10:
            return None

        tick_data = []
        for detail in details:
            amount_yuan = detail.get('amount') or 0
            if amount_yuan < 200_000:
                continue

            time_key = detail.get('time', '')
            if _skip_auction(time_key):
                continue

            direction = int(detail.get('type', 0))
            trade_type = {1: 1, 2: 3, 4: 4}.get(direction, 3)
            volume_lots = int(detail.get('volume', 0))
            tick_data.append({
                'time': time_key,
                'price': detail['price'],
                'volume': volume_lots * 100,
                'amount': amount_yuan,
                'trade_type': trade_type,
            })

        return tick_data if tick_data else None
    except Exception as e:
        logger.warning(f"逐笔大单获取失败 {code}: {e}")
        return None


def get_eastmoney_money_flow_data(code):
    return _em_source.get_minute_money_flow(normalize_stock_code(code) or code)


@stock_timeshare_bp.route('/api/stock/timeshare', methods=['GET'])
def get_timeshare_data():
    """获取分时数据 - 东方财富数据源"""
    code = normalize_stock_code(request.args.get('code', '000001')) or '000001'
    date_param = request.args.get('date', request.args.get('dt'))

    try:
        trading_date = validate_and_get_trading_date(date_param)
        result = get_eastmoney_timeshare_data(code)
        if result:
            result['trading_date'] = trading_date
            return success_response(data=result, message=f'success ({trading_date})')
        return error_response(message=f'无法获取股票 {code} 的分时数据')
    except Exception as e:
        logger.error(f"获取分时数据异常: {e}")
        return error_response(message=f'获取分时数据失败: {str(e)}')


@cache_with_timeout(15)
def _get_quote_cached(code):
    """缓存版 quote 构建，避免同一时刻多次调用东方财富"""
    ts_data_wrap = get_eastmoney_timeshare_data(code)
    if not ts_data_wrap:
        return None

    ts_data = ts_data_wrap['timeshare']
    stats = ts_data_wrap['statistics']

    money_flow = get_eastmoney_money_flow_data(code)
    l2_tick = get_eastmoney_l2_tick_data(code)

    fenshi = []
    volume = []
    zhuli = []
    sanhu = []
    zhuli_raw = money_flow['zhuli'] if money_flow else []
    sanhu_raw = money_flow['sanhu'] if money_flow else []

    for i, item in enumerate(ts_data):
        fenshi.append(str(item['price']))
        volume.append(item['volume'] * 100)
        zhuli.append(zhuli_raw[i] if i < len(zhuli_raw) else '0.000')
        sanhu.append(sanhu_raw[i] if i < len(sanhu_raw) else '0.000')

    big_map = {}
    if l2_tick:
        for tick in l2_tick:
            time_key = tick['time'][:5]
            big_map.setdefault(time_key, []).append({
                't': tick['trade_type'],
                'v': str(int(tick['amount'] / 10000)),
            })
    else:
        for item in ts_data:
            big_map.setdefault(item['time'][:5], [])

    return {
        'base_info': {
            'd300ave_percent': f"{stats['change_percent']:.2f}%",
            'highPrice': str(stats['high']),
            'lowPrice': str(stats['low']),
            'prevClosePrice': str(stats['yesterdayClose']),
            'yi_dong': '',
        },
        'big_map': big_map,
        'fenshi': fenshi,
        'volume': volume,
        'sanhu': sanhu,
        'zhuli': zhuli,
    }


@stock_timeshare_bp.route('/api/v1/quote', methods=['GET'])
def get_quote():
    """竞品格式 - 行情接口"""
    code = normalize_stock_code(request.args.get('code', '000001')) or '000001'

    try:
        result = _get_quote_cached(code)
        if not result:
            return v1_error_response(message=f'无法获取股票 {code} 的行情数据')
        return v1_success_response(data=result)
    except Exception as e:
        logger.error(f"获取行情数据失败: {e}")
        return v1_error_response(message=f'获取行情数据失败: {str(e)}')
