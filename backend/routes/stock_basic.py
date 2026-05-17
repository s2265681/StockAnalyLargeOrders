"""
股票基本信息接口模块
"""
import logging
from datetime import datetime
from flask import Blueprint, request
from utils.cache import cache_with_timeout
from utils.response import success_response, error_response, v1_success_response, v1_error_response
from utils.stock_utils import (
    normalize_stock_code,
    validate_stock_code,
    generate_realistic_mock_data,
    get_stock_name_by_code,
)

logger = logging.getLogger(__name__)

stock_basic_bp = Blueprint('stock_basic', __name__)


@cache_with_timeout(30)
def get_stock_basic_data(code):
    """获取股票基本数据 - 东方财富数据源"""
    try:
        normalized_code = normalize_stock_code(code)
        if not normalized_code or not validate_stock_code(normalized_code):
            logger.warning(f"股票代码无效: {code}，使用默认代码 000001")
            normalized_code = '000001'

        from services.eastmoney_free import EastMoneyFreeSource
        quote = EastMoneyFreeSource().get_realtime_quote(normalized_code)

        if quote:
            current_price = quote.get('price', 0)
            yesterday_close = quote.get('yesterday_close', 0)
            change_amount = round(current_price - yesterday_close, 2)
            return {
                'code': normalized_code,
                'name': quote.get('name', ''),
                'current_price': current_price,
                'change_percent': quote.get('change_percent', 0),
                'change_amount': change_amount,
                'volume': quote.get('volume', 0),
                'turnover': quote.get('turnover', 0),
                'high': quote.get('high', 0),
                'low': quote.get('low', 0),
                'open': quote.get('open', 0),
                'yesterday_close': yesterday_close,
                'data_source': 'eastmoney_free',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }

        logger.warning(f"东方财富行情接口无数据: {normalized_code}，使用离线兜底")
        return generate_realistic_mock_data(normalized_code)

    except Exception as e:
        logger.error(f"获取股票基本数据异常: {e}")
        code_to_use = normalized_code if 'normalized_code' in locals() else code
        return generate_realistic_mock_data(code_to_use)


@stock_basic_bp.route('/api/stock/basic', methods=['GET'])
def get_stock_basic():
    """获取股票基本信息"""
    code = request.args.get('code', '000001')
    try:
        return success_response(data=get_stock_basic_data(code))
    except Exception as e:
        logger.error(f"获取股票基本信息失败: {e}")
        return error_response(message=f'获取股票基本信息失败: {str(e)}')


@stock_basic_bp.route('/api/v1/base_info', methods=['GET'])
def get_base_info():
    """竞品格式 - 基本信息接口"""
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))
    today = datetime.now().strftime('%Y-%m-%d')

    try:
        if dt != today:
            from services.data_source_adapter import DataSourceAdapter
            ts_resp = DataSourceAdapter().get_timeshare_data(code, dt)
            if ts_resp.get('success') and ts_resp.get('data', {}).get('stock_info'):
                info = ts_resp['data']['stock_info']
                yesterday_close = info.get('yesterday_close') or info.get('pre_close') or 0
                current_price = info.get('price') or info.get('current_price') or 0
                change_percent = info.get('change_percent')
                if change_percent is None and yesterday_close:
                    change_percent = round((current_price - yesterday_close) / yesterday_close * 100, 2)
                volume = info.get('volume') or 0
                turnover = info.get('turnover') or 0
                result = {
                    'code': info.get('code') or code,
                    'name': info.get('name') or get_stock_name_by_code(code),
                    'current_price': current_price,
                    'change_amount': round(current_price - yesterday_close, 2) if yesterday_close else 0,
                    'change_percent': change_percent or 0,
                    'open': info.get('open', 0),
                    'high': info.get('high', 0),
                    'low': info.get('low', 0),
                    'yesterday_close': yesterday_close,
                    'volume': round(volume / 10000, 2) if volume > 100000 else round(volume, 2),
                    'turnover': round(turnover / 1e8, 2) if turnover > 1e6 else round(turnover, 2),
                    'limit_up': info.get('limit_up') or (round(yesterday_close * 1.1, 2) if yesterday_close else 0),
                    'limit_down': info.get('limit_down') or (round(yesterday_close * 0.9, 2) if yesterday_close else 0),
                    'date': dt,
                    'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
                return v1_success_response(data=result)

        stock_data = get_stock_basic_data(code)
        yesterday_close = stock_data.get('yesterday_close', 0)

        result = {
            'code': code,
            'name': stock_data.get('name') or get_stock_name_by_code(code),
            'current_price': stock_data.get('current_price', 0),
            'change_amount': stock_data.get('change_amount', 0),
            'change_percent': stock_data.get('change_percent', 0),
            'open': stock_data.get('open', 0),
            'high': stock_data.get('high', 0),
            'low': stock_data.get('low', 0),
            'yesterday_close': yesterday_close,
            'volume': round(stock_data.get('volume', 0) / 10000, 2),   # 万手
            'turnover': round(stock_data.get('turnover', 0) / 1e8, 2), # 亿元
            'limit_up': round(yesterday_close * 1.1, 2) if yesterday_close else 0,
            'limit_down': round(yesterday_close * 0.9, 2) if yesterday_close else 0,
            'date': dt,
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        return v1_success_response(data=result)
    except Exception as e:
        logger.error(f"获取基本信息失败: {e}")
        return v1_error_response(message=f'获取基本信息失败: {str(e)}')
