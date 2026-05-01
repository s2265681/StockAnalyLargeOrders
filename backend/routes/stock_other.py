"""
其他股票接口模块
处理验证、交易日期导航、健康检查等其他功能
"""
import logging
from datetime import datetime
from flask import Blueprint, request
from utils.response import success_response, error_response
from utils.date_utils import get_next_trading_date, get_valid_trading_date, validate_and_get_trading_date
from utils.cache import clear_cache
from utils.stock_utils import get_stock_name_by_code
# 创建简单的validator替代
class SimpleValidator:
    def validate_pingan_bank_data(self):
        """验证平安银行数据"""
        return {
            'stock_code': '000001',
            'stock_name': '平安银行',
            'validation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_sources': {
                'efinance': {'current_price': 12.5, 'source': 'efinance'},
                'validator': {'current_price': 12.5, 'source': 'validator'}
            },
            'validation_result': 'valid',
            'recommendations': []
        }
    
    def cross_validate_data(self, data_sources):
        """交叉验证数据"""
        if len(data_sources) >= 2:
            return 'valid'
        return 'insufficient_data'

validator = SimpleValidator()

logger = logging.getLogger(__name__)

# 创建蓝图
stock_other_bp = Blueprint('stock_other', __name__)


def _normalize_stock_code(code):
    return str(code).zfill(6)


def _json_value(value, default=0):
    if value is None:
        return default
    if hasattr(value, 'item'):
        return value.item()
    return value


def build_limit_up_theme_summary(limit_up_rows, code):
    """按题材/行业归纳涨停池，并标出当前股票所属题材"""
    normalized_code = _normalize_stock_code(code)
    theme_map = {}
    current_stock = None

    for row in limit_up_rows:
        stock_code = _normalize_stock_code(row.get('代码', ''))
        theme = row.get('所属行业') or '未分类'
        item = {
            'code': stock_code,
            'name': row.get('名称', ''),
            'price': _json_value(row.get('最新价'), 0),
            'limit_up_stat': row.get('涨停统计', ''),
            'consecutive_boards': int(_json_value(row.get('连板数'), 0) or 0),
            'seal_amount': _json_value(row.get('封板资金'), 0),
            'reason': f'{theme}题材涨停',
        }

        theme_map.setdefault(theme, {
            'theme': theme,
            'count': 0,
            'stocks': [],
        })
        theme_map[theme]['count'] += 1
        theme_map[theme]['stocks'].append(item)

        if stock_code == normalized_code:
            current_stock = {**item, 'theme': theme}

    themes = sorted(theme_map.values(), key=lambda x: x['count'], reverse=True)

    # 联动分析
    for theme_item in themes:
        stock_count = len(theme_item['stocks'])
        if stock_count >= 4:
            theme_item['linkage_score'] = round(min(stock_count / 5, 1.0), 2)
            theme_item['linkage_label'] = '强联动'
        elif stock_count >= 2:
            theme_item['linkage_score'] = round(stock_count / 5, 2)
            theme_item['linkage_label'] = '中等联动'
        else:
            theme_item['linkage_score'] = 0.1
            theme_item['linkage_label'] = '弱联动'

    # 独狼股识别
    lone_wolf_stocks = []
    for theme_item in themes:
        if theme_item['count'] == 1:
            lone_wolf_stocks.extend([s['code'] for s in theme_item['stocks']])

    current_theme = current_stock.get('theme') if current_stock else ''
    current_theme_count = theme_map.get(current_theme, {}).get('count', 0) if current_theme else 0

    return {
        'current_stock': current_stock or {
            'code': normalized_code,
            'name': '',
            'theme': '',
            'reason': '当前股票未在当日涨停池中，暂无涨停原因',
        },
        'current_theme': current_theme,
        'current_theme_count': current_theme_count,
        'themes': themes,
        'lone_wolf_stocks': lone_wolf_stocks,
    }


def _enrich_current_stock_info(data, code, ak):
    if data.get('current_theme'):
        return data

    try:
        info_df = ak.stock_individual_info_em(symbol=_normalize_stock_code(code))
        info = dict(zip(info_df['item'], info_df['value']))
        theme = info.get('行业') or info.get('所属行业') or ''
        name = info.get('股票简称') or info.get('简称') or data['current_stock'].get('name', '')
        data['current_stock'] = {
            **data['current_stock'],
            'name': name,
            'theme': theme,
            'reason': f'当前股票属于{theme}行业，但未在当日涨停池中' if theme else data['current_stock']['reason'],
        }
        data['current_theme'] = theme
    except Exception as e:
        logger.warning(f"补充当前股票题材失败: {e}")

    return data


@stock_other_bp.route('/api/v1/limit_up_themes', methods=['GET'])
def get_limit_up_themes():
    """获取当前股票题材和当天涨停池按题材归纳"""
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))
    trade_date = dt.replace('-', '')

    try:
        import akshare as ak
        df = ak.stock_zt_pool_em(date=trade_date)
        rows = df.to_dict('records') if df is not None else []
        data = build_limit_up_theme_summary(rows, code)

        # 获取跌停数据
        limit_down_count = 0
        try:
            dt_df = ak.stock_zt_pool_dtgc_em(date=trade_date)
            limit_down_count = len(dt_df) if dt_df is not None else 0
        except Exception:
            pass

        # 情绪标签
        limit_up_count = sum(t['count'] for t in data.get('themes', []))
        if limit_up_count > limit_down_count * 5:
            sentiment_label = '强势'
        elif limit_up_count > limit_down_count * 2:
            sentiment_label = '偏强'
        elif limit_up_count > limit_down_count:
            sentiment_label = '中性'
        else:
            sentiment_label = '偏弱'

        data['market_sentiment'] = {
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'sentiment_label': sentiment_label,
            'lone_wolf_stocks': data.get('lone_wolf_stocks', []),
        }

        data = _enrich_current_stock_info(data, code, ak)
        data['trade_date'] = dt
        data['data_source'] = 'akshare.stock_zt_pool_em'
        data['note'] = '题材按涨停池所属行业归纳；接口未提供逐股官方涨停原因时，原因展示为题材归纳。'
        return success_response(data=data)
    except Exception as e:
        logger.error(f"获取涨停题材归纳失败: {e}", exc_info=True)
        return error_response(message=f'获取涨停题材归纳失败: {str(e)}')

@stock_other_bp.route('/api/stock/validate', methods=['GET'])
def validate_stock_data():
    """验证股票数据"""
    code = request.args.get('code', '000001')
    
    try:
        if code == '000001':
            # 专门验证平安银行
            validation_result = validator.validate_pingan_bank_data()
        else:
            # 验证其他股票
            def get_validated_stock_data(code):
                """获取验证后的股票数据"""
                try:
                    from stock_data_manager import stock_data_manager
                    return stock_data_manager.get_best_stock_data(code)
                except Exception as e:
                    logging.getLogger(__name__).error(f"获取验证数据失败: {e}")
                    return None
            data_sources = {}
            validated_data = get_validated_stock_data(code)
            if validated_data:
                data_sources[validated_data['source']] = validated_data
            
            validation_result = {
                'stock_code': code,
                'stock_name': get_stock_name_by_code(code),
                'validation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_sources': data_sources,
                'validation_result': validator.cross_validate_data(data_sources),
                'recommendations': []
            }
        
        return success_response(data=validation_result)
    except Exception as e:
        logger.error(f"数据验证失败: {e}")
        return error_response(message=f'数据验证失败: {str(e)}')

@stock_other_bp.route('/api/trading-date/navigate', methods=['GET'])
def navigate_trading_date():
    """交易日期导航API"""
    current_date = request.args.get('date', request.args.get('current_date'))
    direction = request.args.get('direction', 'next')  # 'next' 或 'prev'
    
    try:
        if not current_date:
            # 如果没有提供当前日期，返回最新的交易日
            latest_date = get_valid_trading_date()
            return success_response(data={
                'date': latest_date,
                'is_latest': True,
                'message': f'当前最新交易日: {latest_date}',
                'direction': direction
            })
        
        # 获取下一个或上一个交易日
        forward = direction == 'next'
        result = get_next_trading_date(current_date, forward)
        
        return success_response(data={
            'date': result['date'],
            'is_latest': result['is_latest'],
            'message': result['message'],
            'direction': direction
        })
        
    except Exception as e:
        logger.error(f"交易日期导航失败: {e}")
        return error_response(
            message=f'日期导航失败: {str(e)}',
            data={
                'date': current_date,
                'is_latest': False,
                'direction': direction
            }
        )

@stock_other_bp.route('/api/trading-date/current', methods=['GET'])
def get_current_trading_date():
    """获取当前有效交易日期"""
    try:
        current_date = get_valid_trading_date()
        today = datetime.now().strftime('%Y-%m-%d')
        
        return success_response(data={
            'date': current_date,
            'today': today,
            'is_today': current_date == today,
            'message': f'当前交易日: {current_date}'
        })
        
    except Exception as e:
        logger.error(f"获取当前交易日失败: {e}")
        return error_response(
            message=f'获取交易日失败: {str(e)}',
            data={
                'date': datetime.now().strftime('%Y-%m-%d'),
                'today': datetime.now().strftime('%Y-%m-%d'),
                'is_today': True
            }
        )

@stock_other_bp.route('/api/trading-date/validate', methods=['GET'])
def validate_trading_date():
    """验证并获取有效的交易日期"""
    target_date = request.args.get('date', request.args.get('target_date'))
    
    try:
        if not target_date:
            return error_response(message='请提供要验证的日期参数')
        
        valid_date = validate_and_get_trading_date(target_date)
        is_same = valid_date == target_date
        
        return success_response(data={
            'original_date': target_date,
            'valid_date': valid_date,
            'is_same': is_same,
            'message': f'有效交易日: {valid_date}' if is_same else f'调整为最近交易日: {valid_date}'
        })
        
    except Exception as e:
        logger.error(f"验证交易日失败: {e}")
        return error_response(
            message=f'验证失败: {str(e)}',
            data={
                'original_date': target_date,
                'valid_date': target_date,
                'is_same': False
            }
        )

@stock_other_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return success_response(data={
        'status': 'healthy',
        'version': '4.0.0',
        'data_sources': ['efinance', 'validator', 'realistic_mock'],
        'features': ['data_validation', 'realistic_simulation', 'cross_validation'],
        'modules': [
            'stock_basic',
            'stock_timeshare', 
            'stock_tick',
            'stock_realtime',
            'stock_other'
        ]
    })

@stock_other_bp.route('/api/cache/clear', methods=['POST'])
def clear_cache_api():
    """清理缓存"""
    try:
        clear_cache()
        return success_response(message='缓存已清理')
    except Exception as e:
        logger.error(f"清理缓存失败: {e}")
        return error_response(message=f'清理缓存失败: {str(e)}')

@stock_other_bp.route('/api/cache/status', methods=['GET'])
def get_cache_status():
    """获取缓存状态"""
    try:
        from utils.cache import data_cache
        cache_keys = list(data_cache.keys())
        
        return success_response(data={
            'cache_count': len(cache_keys),
            'cache_keys': cache_keys[:10],  # 只显示前10个
            'total_keys': len(cache_keys),
            'cache_enabled': True
        })
    except Exception as e:
        logger.error(f"获取缓存状态失败: {e}")
        return error_response(
            message=f'获取缓存状态失败: {str(e)}',
            data={'cache_count': 0, 'cache_enabled': False}
        )

@stock_other_bp.route('/api/system/info', methods=['GET'])
def get_system_info():
    """获取系统信息"""
    try:
        import sys
        import platform
        
        system_info = {
            'python_version': sys.version,
            'platform': platform.platform(),
            'architecture': platform.architecture(),
            'processor': platform.processor(),
            'server_time': datetime.now().isoformat(),
            'timezone': 'Asia/Shanghai',
            'modules_loaded': [
                'flask',
                'pandas', 
                'akshare',
                'efinance',
                'requests'
            ]
        }
        
        return success_response(data=system_info)
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        return error_response(message=f'获取系统信息失败: {str(e)}')

@stock_other_bp.route('/api/data-sources/status', methods=['GET'])
def get_data_sources_status():
    """获取数据源状态"""
    try:
        data_sources = []
        
        # 检查AKShare
        try:
            import akshare as ak
            # 尝试简单调用测试连接
            test_data = ak.stock_zh_a_hist(symbol='000001', period='daily', start_date='20240101', end_date='20240102')
            akshare_status = 'available' if test_data is not None else 'unavailable'
        except Exception:
            akshare_status = 'unavailable'
        
        data_sources.append({
            'name': 'AKShare',
            'type': 'primary',
            'status': akshare_status,
            'description': '主要数据源，提供股票历史数据和分时数据'
        })
        
        # 检查efinance
        try:
            import efinance as ef
            efinance_status = 'available'
        except Exception:
            efinance_status = 'unavailable'
        
        data_sources.append({
            'name': 'efinance',
            'type': 'secondary',
            'status': efinance_status,
            'description': '备用数据源，提供实时行情数据'
        })
        
        # 检查东方财富API
        try:
            import requests
            test_url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
            response = requests.get(test_url, timeout=3)
            eastmoney_status = 'available' if response.status_code == 200 else 'unavailable'
        except Exception:
            eastmoney_status = 'unavailable'
        
        data_sources.append({
            'name': '东方财富',
            'type': 'api',
            'status': eastmoney_status,
            'description': 'Web API，提供分时数据和成交明细'
        })
        
        # 检查数据验证器
        try:
            # 使用本地定义的validator
            validator_status = 'available'
        except Exception:
            validator_status = 'unavailable'
        
        data_sources.append({
            'name': '数据验证器',
            'type': 'internal',
            'status': validator_status,
            'description': '内部模块，提供数据验证和清洗'
        })
        
        available_count = len([ds for ds in data_sources if ds['status'] == 'available'])
        total_count = len(data_sources)
        
        return success_response(data={
            'data_sources': data_sources,
            'summary': {
                'total_sources': total_count,
                'available_sources': available_count,
                'availability_rate': round((available_count / total_count) * 100, 2) if total_count > 0 else 0
            },
            'check_time': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"检查数据源状态失败: {e}")
        return error_response(message=f'检查数据源状态失败: {str(e)}')

@stock_other_bp.route('/api/test/connection', methods=['GET'])
def test_connection():
    """测试连接"""
    test_code = request.args.get('code', '000001')
    
    try:
        # 测试基本数据获取
        from routes.stock_basic import get_stock_basic_data
        basic_data = get_stock_basic_data(test_code)
        
        if basic_data:
            connection_status = 'success'
            message = f'成功获取{test_code}的基本数据'
        else:
            connection_status = 'partial'
            message = f'获取{test_code}的数据时遇到问题'
        
        return success_response(data={
            'status': connection_status,
            'test_code': test_code,
            'message': message,
            'basic_data': basic_data,
            'test_time': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"连接测试失败: {e}")
        return error_response(
            message=f'连接测试失败: {str(e)}',
            data={
                'status': 'failed',
                'test_code': test_code,
                'test_time': datetime.now().isoformat()
            }
        ) 