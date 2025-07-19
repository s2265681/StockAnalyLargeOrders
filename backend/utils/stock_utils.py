"""
股票工具模块
处理股票代码、名称等通用功能
"""
import logging
from stock_data_manager import stock_data_manager

# 添加缺失的函数
def normalize_stock_code(code):
    """标准化股票代码"""
    if not code:
        return None
    code = str(code).strip()
    # 移除可能的前缀
    if code.startswith(('sh', 'sz', '0.', '1.')):
        code = code[2:] if code.startswith(('sh', 'sz')) else code[2:]
    return code

def validate_stock_code(code):
    """验证股票代码格式"""
    if not code:
        return False
    code = str(code).strip()
    # 检查是否为6位数字
    if not code.isdigit() or len(code) != 6:
        return False
    # 检查股票代码前缀
    valid_prefixes = ['00', '30', '60', '68', '90']
    return any(code.startswith(prefix) for prefix in valid_prefixes)

logger = logging.getLogger(__name__)

def get_stock_name_by_code(code):
    """根据股票代码获取股票名称"""
    try:
        # 常见股票代码对应名称
        stock_names = {
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
            '000166': '申万宏源',
            '002415': '海康威视',
            '000725': '京东方A',
        }
        
        # 先从预定义列表中查找
        if code in stock_names:
            return stock_names[code]
        
        # 尝试从数据源管理器获取
        stock_data = stock_data_manager.get_best_stock_data(code)
        if stock_data and stock_data.name:
            return stock_data.name
        
        # 如果获取失败，返回默认名称
        return f'股票{code}'
        
    except Exception as e:
        logger.error(f"获取股票名称失败: {e}")
        return f'股票{code}'

def classify_order_size(amount):
    """分类订单大小"""
    if amount >= 3000000:
        return 'D300'  # 超大单 ≥300万
    elif amount >= 1000000:
        return 'D100'  # 大单 ≥100万
    elif amount >= 500000:
        return 'D50'   # 中单 ≥50万
    elif amount >= 300000:
        return 'D30'   # 小大单 ≥30万
    else:
        return 'D10'   # 散户 <30万

def format_stock_code_for_market(code, market='tencent'):
    """将股票代码转换为不同市场的格式"""
    if len(code) == 6:
        if market == 'tencent':
            if code.startswith(('60', '68')):  # 上海A股
                return f"sh{code}"
            elif code.startswith(('00', '30')):  # 深圳A股
                return f"sz{code}"
        elif market == 'eastmoney':
            if code.startswith('6'):
                return f"1.{code}"
            else:
                return f"0.{code}"
        elif market == 'sina':
            if code.startswith('6'):
                return f"sh{code}"
            else:
                return f"sz{code}"
    return code

def generate_realistic_mock_data(code):
    """生成备用的模拟股票数据"""
    import random
    
    realistic_prices = {
        '603001': {'base': 8.48, 'name': '奥康国际'},
        '000001': {'base': 12.50, 'name': '平安银行'},
        '000002': {'base': 25.30, 'name': '万科A'},
        '600036': {'base': 35.80, 'name': '招商银行'},
        '600519': {'base': 1680.0, 'name': '贵州茅台'},
        '000858': {'base': 145.60, 'name': '五粮液'},
    }
    
    stock_info = realistic_prices.get(code, {'base': 50.0, 'name': f'股票{code}'})
    base_price = stock_info['base']
    
    current_price = round(base_price + random.uniform(-base_price*0.05, base_price*0.05), 2)
    yesterday_close = round(base_price + random.uniform(-base_price*0.03, base_price*0.03), 2)
    change_amount = round(current_price - yesterday_close, 2)
    change_percent = round((change_amount / yesterday_close * 100), 2) if yesterday_close > 0 else 0
    
    return {
        'code': code,
        'name': stock_info['name'],
        'current_price': current_price,
        'change_percent': change_percent,
        'change_amount': change_amount,
        'volume': random.randint(1000000, 5000000),
        'turnover': random.randint(50000000, 200000000),
        'high': round(current_price * 1.05, 2),
        'low': round(current_price * 0.95, 2),
        'open': round(yesterday_close * 1.02, 2),
        'yesterday_close': yesterday_close,
        'market_cap': round(current_price * 100000000, 2),
        'pe_ratio': round(random.uniform(10, 30), 2),
        'turnover_rate': round(random.uniform(0.5, 8.0), 2),
        'data_source': 'backup_mock'
    } 