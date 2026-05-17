"""
股票工具模块
处理股票代码、名称等通用功能
"""
import logging

logger = logging.getLogger(__name__)

# 常用股票代码名称映射（离线兜底）
_STOCK_NAMES = {
    '603001': '奥康国际',
    '000001': '平安银行',
    '000002': '万科A',
    '600036': '招商银行',
    '600519': '贵州茅台',
    '000858': '五粮液',
    '000300': '沪深300',
    '399001': '深证成指',
    '399006': '创业板指',
    '000016': '上证50',
    '600000': '浦发银行',
    '002415': '海康威视',
    '000725': '京东方A',
}

# 解析成功的名称缓存，避免重复查库/调接口
_NAME_CACHE = {}


def normalize_stock_code(code):
    """标准化股票代码为6位纯数字"""
    if not code:
        return None
    code = str(code).strip()
    if code.startswith(('sh', 'sz')):
        code = code[2:]
    elif code.startswith(('0.', '1.')):
        code = code[2:]
    return code.zfill(6) if code.isdigit() else code


def validate_stock_code(code):
    """验证股票代码格式（6位数字，合法前缀）"""
    if not code:
        return False
    code = str(code).strip()
    if not code.isdigit() or len(code) != 6:
        return False
    valid_prefixes = ['00', '30', '60', '68', '90']
    return any(code.startswith(p) for p in valid_prefixes)


def _is_placeholder_name(name, code):
    """是否为「股票XXXXXX」占位名"""
    if not name:
        return True
    normalized = normalize_stock_code(code) or str(code)
    text = str(name).strip()
    return text in (f'股票{normalized}', normalized, f'股票 {normalized}')


def _lookup_name_from_db(code):
    """从业务库（龙虎榜/涨停池）取最近一条有效中文名"""
    try:
        from utils.db import execute_query

        rows = execute_query(
            """
            SELECT name FROM (
                SELECT name, date AS sort_date FROM dragon_tiger_daily
                WHERE code = %s AND name IS NOT NULL AND name != ''
                UNION ALL
                SELECT name, date AS sort_date FROM limit_up_stocks
                WHERE code = %s AND name IS NOT NULL AND name != ''
            ) t
            WHERE name NOT LIKE '股票%%'
            ORDER BY sort_date DESC
            LIMIT 1
            """,
            (code, code),
        )
        if rows:
            name = (rows[0].get('name') or '').strip()
            if name and not _is_placeholder_name(name, code):
                return name
    except Exception as e:
        logger.debug(f"数据库查股票名称失败 {code}: {e}")
    return None


def _lookup_name_from_akshare(code):
    """akshare 个股资料（东方财富不可达时的兜底）"""
    try:
        import akshare as ak

        df = ak.stock_individual_info_em(symbol=code)
        if df is None or df.empty:
            return None
        info = dict(zip(df['item'], df['value']))
        name = (info.get('股票简称') or info.get('简称') or '').strip()
        if name and not _is_placeholder_name(name, code):
            return name
    except Exception as e:
        logger.debug(f"akshare 查股票名称失败 {code}: {e}")
    return None


def get_stock_name_by_code(code):
    """根据股票代码获取股票名称，优先本地/库，再东方财富，最后 akshare"""
    normalized = normalize_stock_code(code)
    if not normalized:
        return ''

    if normalized in _NAME_CACHE:
        return _NAME_CACHE[normalized]

    if normalized in _STOCK_NAMES:
        _NAME_CACHE[normalized] = _STOCK_NAMES[normalized]
        return _STOCK_NAMES[normalized]

    db_name = _lookup_name_from_db(normalized)
    if db_name:
        _NAME_CACHE[normalized] = db_name
        return db_name

    try:
        from services.eastmoney_free import EastMoneyFreeSource
        quote = EastMoneyFreeSource().get_realtime_quote(normalized)
        em_name = (quote or {}).get('name', '').strip()
        if em_name and not _is_placeholder_name(em_name, normalized):
            _NAME_CACHE[normalized] = em_name
            return em_name
    except Exception as e:
        logger.warning(f"通过东方财富获取股票名称失败 {normalized}: {e}")

    ak_name = _lookup_name_from_akshare(normalized)
    if ak_name:
        _NAME_CACHE[normalized] = ak_name
        return ak_name

    return f'股票{normalized}'


def classify_order_size(amount):
    """分类订单大小"""
    if amount >= 3_000_000:
        return 'D300'
    elif amount >= 1_000_000:
        return 'D100'
    elif amount >= 500_000:
        return 'D50'
    elif amount >= 300_000:
        return 'D30'
    else:
        return 'D10'


def format_stock_code_for_market(code, market='eastmoney'):
    """将股票代码转换为指定市场格式"""
    if len(code) != 6:
        return code
    if market == 'eastmoney':
        return f"1.{code}" if code.startswith('6') else f"0.{code}"
    if market in ('tencent', 'sina'):
        return f"sh{code}" if code.startswith('6') else f"sz{code}"
    return code


def generate_realistic_mock_data(code):
    """东方财富不可达时的离线兜底数据（仅基础字段）"""
    import random
    normalized = normalize_stock_code(code) or code
    preset = {
        '603001': {'base': 8.48, 'name': '奥康国际'},
        '000001': {'base': 12.50, 'name': '平安银行'},
        '600519': {'base': 1680.0, 'name': '贵州茅台'},
    }
    info = preset.get(normalized, {'base': 50.0, 'name': get_stock_name_by_code(normalized)})
    base = info['base']
    current = round(base * (1 + random.uniform(-0.05, 0.05)), 2)
    prev_close = round(base * (1 + random.uniform(-0.03, 0.03)), 2)
    change = round(current - prev_close, 2)
    return {
        'code': normalized,
        'name': info['name'],
        'current_price': current,
        'change_percent': round(change / prev_close * 100, 2) if prev_close else 0,
        'change_amount': change,
        'volume': random.randint(1_000_000, 5_000_000),
        'turnover': random.randint(50_000_000, 200_000_000),
        'high': round(current * 1.05, 2),
        'low': round(current * 0.95, 2),
        'open': round(prev_close * 1.02, 2),
        'yesterday_close': prev_close,
        'data_source': 'offline_mock',
    }
