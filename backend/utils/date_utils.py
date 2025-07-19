"""
日期工具模块
处理交易日期相关功能
"""
import logging
from datetime import datetime, timedelta
import akshare as ak

logger = logging.getLogger(__name__)

def get_valid_trading_date(target_date=None, max_days_back=30):
    """
    获取有效的交易日期
    
    Args:
        target_date: 目标日期，可以是字符串'YYYY-MM-DD'或datetime对象，默认为今天
        max_days_back: 最多向前查找多少天，默认30天
    
    Returns:
        str: 有效的交易日期，格式为'YYYY-MM-DD'
    """
    try:
        # 处理输入日期
        if target_date is None:
            current_date = datetime.now()
        elif isinstance(target_date, str):
            current_date = datetime.strptime(target_date, '%Y-%m-%d')
        else:
            current_date = target_date
        
        # 向前查找最近的交易日
        for i in range(max_days_back):
            check_date = current_date - timedelta(days=i)
            date_str = check_date.strftime('%Y-%m-%d')
            
            # 跳过周末
            if check_date.weekday() >= 5:  # 周六=5, 周日=6
                continue
            
            # 使用AKShare验证是否为交易日
            try:
                # 尝试获取该日期的股票数据来验证是否为交易日
                test_df = ak.stock_zh_a_hist(
                    symbol='000001',  # 使用平安银行作为测试股票
                    period='daily',
                    start_date=check_date.strftime('%Y%m%d'),
                    end_date=check_date.strftime('%Y%m%d'),
                    adjust=''
                )
                
                if test_df is not None and not test_df.empty:
                    logger.info(f"找到有效交易日: {date_str}")
                    return date_str
                    
            except Exception as e:
                logger.warning(f"检查日期{date_str}失败: {e}")
                continue
        
        # 如果都找不到，返回最近的工作日
        fallback_date = current_date
        while fallback_date.weekday() >= 5:
            fallback_date -= timedelta(days=1)
        
        fallback_str = fallback_date.strftime('%Y-%m-%d')
        logger.warning(f"无法找到有效交易日，使用回退日期: {fallback_str}")
        return fallback_str
        
    except Exception as e:
        logger.error(f"获取有效交易日失败: {e}")
        # 返回今天作为最后备用
        return datetime.now().strftime('%Y-%m-%d')

def get_next_trading_date(current_date, forward=True):
    """
    获取下一个或上一个交易日
    
    Args:
        current_date: 当前日期，字符串格式'YYYY-MM-DD'
        forward: True为获取下一个交易日，False为获取上一个交易日
    
    Returns:
        dict: {
            'date': str,  # 新的交易日期
            'is_latest': bool,  # 是否已经是最新的交易日
            'message': str  # 提示信息
        }
    """
    try:
        current_dt = datetime.strptime(current_date, '%Y-%m-%d')
        today = datetime.now().date()
        
        if forward:
            # 获取下一个交易日
            next_date = current_dt + timedelta(days=1)
            
            # 如果下一个日期超过今天，说明已经是最新
            if next_date.date() > today:
                return {
                    'date': current_date,
                    'is_latest': True,
                    'message': '已经是最新的交易日'
                }
            
            # 查找下一个有效交易日
            valid_date = get_valid_trading_date(next_date)
            
            # 如果找到的日期仍然是今天之后，说明已经是最新
            if datetime.strptime(valid_date, '%Y-%m-%d').date() > today:
                return {
                    'date': current_date,
                    'is_latest': True,
                    'message': '已经是最新的交易日'
                }
            
            return {
                'date': valid_date,
                'is_latest': False,
                'message': f'切换到交易日: {valid_date}'
            }
        else:
            # 获取上一个交易日
            prev_date = current_dt - timedelta(days=1)
            valid_date = get_valid_trading_date(prev_date)
            
            return {
                'date': valid_date,
                'is_latest': False,
                'message': f'切换到交易日: {valid_date}'
            }
            
    except Exception as e:
        logger.error(f"获取交易日导航失败: {e}")
        return {
            'date': current_date,
            'is_latest': False,
            'message': f'日期导航失败: {str(e)}'
        }

def validate_and_get_trading_date(date_param):
    """
    验证并获取有效的交易日期
    
    Args:
        date_param: 从请求参数中获取的日期字符串
    
    Returns:
        str: 有效的交易日期字符串
    """
    if not date_param:
        # 如果没有提供日期，获取最近的交易日
        return get_valid_trading_date()
    
    try:
        # 验证日期格式
        datetime.strptime(date_param, '%Y-%m-%d')
        # 获取该日期对应的有效交易日
        return get_valid_trading_date(date_param)
    except ValueError:
        logger.warning(f"无效的日期格式: {date_param}")
        return get_valid_trading_date() 