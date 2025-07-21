"""
股票分时数据接口模块
处理股票分时数据相关的所有API接口
"""
import logging
import json
import random
import requests
import pandas as pd
import akshare as ak
from datetime import datetime, timedelta
from flask import Blueprint, request
from utils.cache import cache_with_timeout
from utils.response import success_response, error_response, v1_success_response, v1_error_response
from utils.date_utils import validate_and_get_trading_date
from routes.stock_basic import get_stock_basic_data

logger = logging.getLogger(__name__)

# 创建蓝图
stock_timeshare_bp = Blueprint('stock_timeshare', __name__)

def generate_complete_timeshare_data(raw_data, yesterday_close):
    """
    处理原始分时数据，不进行填充，只返回实际有数据的时间点
    
    Args:
        raw_data: 原始分时数据列表
        yesterday_close: 昨收价，用于计算涨跌幅
    
    Returns:
        list: 原始分时数据，不填充空白时间点
    """
    if not raw_data:
        return []
    
    # 处理原始数据，确保格式正确
    processed_data = []
    cumulative_volume = 0
    cumulative_amount = 0
    
    for item in raw_data:
        # 标准化时间格式
        time_str = item['time']
        if len(time_str) == 8:  # HH:MM:SS格式
            time_str = time_str[:5]  # 转换为HH:MM
        
        # 只处理有实际交易的时间点
        volume = item.get('volume', 0)
        amount = item.get('amount', 0)
        price = item.get('price', yesterday_close)
        
        cumulative_volume += volume
        cumulative_amount += amount
        
        processed_data.append({
            'time': time_str,
            'price': price,
            'volume': volume,
            'amount': amount,
            'open': item.get('open', price),
            'high': item.get('high', price),
            'low': item.get('low', price),
            'avg_price': cumulative_amount / cumulative_volume if cumulative_volume > 0 else price,
            'change_percent': round((price - yesterday_close) / yesterday_close * 100, 2) if yesterday_close > 0 else 0
        })
    
    logger.info(f"处理原始分时数据: {len(processed_data)}个实际数据点")
    return processed_data

@cache_with_timeout(30)
def get_akshare_timeshare_data(code, target_date=None):
    """从AKShare获取真实分时数据（最高优先级）"""
    try:
        # 获取有效的交易日期
        trading_date = validate_and_get_trading_date(target_date)
        logger.info(f"尝试使用AKShare获取{code}在{trading_date}的分时数据...")
        
        # 1. 尝试使用AKShare的分时数据接口
        timeshare_df = None
        
        # 尝试获取指定日期的1分钟数据
        try:
            date_str = trading_date.replace('-', '')  # 转换为YYYYMMDD格式
            logger.info(f"尝试获取{code}在{date_str}的分时数据")
            
            timeshare_df = ak.stock_zh_a_hist_min_em(
                symbol=code, 
                period="1", 
                start_date=date_str, 
                end_date=date_str, 
                adjust=""
            )
            
            if timeshare_df is not None and not timeshare_df.empty:
                logger.info(f"获取到{trading_date}的分时数据，共{len(timeshare_df)}条")
            else:
                logger.warning(f"指定日期{trading_date}无分时数据")
                
        except Exception as e:
            logger.warning(f"获取指定日期{trading_date}数据失败: {e}")
            
            # 备用方案：如果指定日期失败，尝试获取最近的交易日数据
            try:
                logger.info("尝试获取最近几天的分时数据...")
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
                
                timeshare_df = ak.stock_zh_a_hist_min_em(
                    symbol=code, 
                    period="1", 
                    start_date=start_date, 
                    end_date=end_date, 
                    adjust=""
                )
                
                # 如果获取到数据，只取最后一个交易日的数据
                if timeshare_df is not None and not timeshare_df.empty:
                    # 确保时间列是datetime类型
                    if not pd.api.types.is_datetime64_any_dtype(timeshare_df['时间']):
                        timeshare_df['时间'] = pd.to_datetime(timeshare_df['时间'])
                    
                    # 获取最后交易日的数据
                    last_date = timeshare_df['时间'].dt.date.max()
                    timeshare_df = timeshare_df[timeshare_df['时间'].dt.date == last_date]
                    logger.info(f"使用最近交易日{last_date}的分时数据，共{len(timeshare_df)}条")
                    
            except Exception as e2:
                logger.warning(f"获取最近数据也失败: {e2}")
                
                # 最后的备用方案：使用固定的历史交易日期
                historical_dates = [
                    "20240715",  # 2024-07-15
                    "20240712",  # 2024-07-12
                    "20240711",  # 2024-07-11
                    "20240710",  # 2024-07-10
                    "20240709",  # 2024-07-09
                ]
                
                for date_str in historical_dates:
                    try:
                        logger.info(f"尝试使用历史日期{date_str}获取分时数据...")
                        
                        timeshare_df = ak.stock_zh_a_hist_min_em(
                            symbol=code, 
                            period="1", 
                            start_date=date_str, 
                            end_date=date_str, 
                            adjust=""
                        )
                        
                        if timeshare_df is not None and not timeshare_df.empty:
                            logger.info(f"使用{date_str}获取到{len(timeshare_df)}条分时数据")
                            break
                            
                    except Exception as e3:
                        logger.warning(f"日期{date_str}获取失败: {e3}")
                        continue
                
                if timeshare_df is None or timeshare_df.empty:
                    logger.error("所有历史日期获取都失败")
                    return None
        
        if timeshare_df is not None and not timeshare_df.empty:
            # 获取股票基础信息，用于获取昨收价
            stock_basic = get_stock_basic_data(code)
            yesterday_close = stock_basic['yesterday_close']
            
            # 转换原始数据格式
            raw_timeshare_data = []
            for _, row in timeshare_df.iterrows():
                time_str = str(row['时间']).split(' ')[-1] if ' ' in str(row['时间']) else str(row['时间'])
                if len(time_str) == 8:  # HH:MM:SS
                    time_str = time_str[:5]  # 只取HH:MM
                
                raw_timeshare_data.append({
                    'time': time_str,
                    'price': float(row['收盘']),
                    'volume': int(row['成交量']) if pd.notna(row['成交量']) else 0,
                    'amount': float(row['成交额']) if pd.notna(row['成交额']) else 0,
                    'open': float(row['开盘']) if pd.notna(row['开盘']) else float(row['收盘']),
                    'high': float(row['最高']) if pd.notna(row['最高']) else float(row['收盘']),
                    'low': float(row['最低']) if pd.notna(row['最低']) else float(row['收盘']),
                    'avg_price': float(row['均价']) if '均价' in row and pd.notna(row['均价']) else float(row['收盘'])
                })
            
            # 生成完整的分时数据（09:30-15:00）
            complete_timeshare_data = generate_complete_timeshare_data(raw_timeshare_data, yesterday_close)
            
            if complete_timeshare_data:
                # 计算统计信息
                prices = [d['price'] for d in complete_timeshare_data if d['volume'] > 0]
                volumes = [d['volume'] for d in complete_timeshare_data]
                amounts = [d['amount'] for d in complete_timeshare_data]
                
                logger.info(f"✅ AKShare分时数据获取成功: {len(complete_timeshare_data)}个数据点（原始{len(raw_timeshare_data)}条）")
                
                return {
                    'timeshare': complete_timeshare_data,
                    'trading_date': trading_date,
                    'statistics': {
                        'current_price': stock_basic['current_price'],
                        'yesterdayClose': yesterday_close,
                        'change_percent': stock_basic['change_percent'],
                        'change_amount': stock_basic['change_amount'],
                        'high': max(prices) if prices else stock_basic['high'],
                        'low': min(prices) if prices else stock_basic['low'],
                        'volume': sum(volumes) if volumes else stock_basic['volume'],
                        'turnover': sum(amounts) if amounts else stock_basic['turnover']
                    }
                }
        
        logger.warning(f"AKShare分时数据获取失败或数据不足")
        return None
        
    except Exception as e:
        logger.warning(f"AKShare分时数据获取异常: {e}")
        return None

def get_eastmoney_timeshare_data(code):
    """从东方财富获取真实分时数据（经测试可用）"""
    try:
        # 东方财富分时数据接口
        market_code = f"1.{code}" if code.startswith('6') else f"0.{code}"
        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
        
        params = {
            'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
            'ut': '7eea3edcaed734bea9cbfc24409ed989',
            'secid': market_code,
            'ndays': 1  # 获取1天的分时数据
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com'
        }
        
        # 增加超时时间并添加重试机制
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=15)
                break
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    logger.warning(f"东方财富API请求超时，第{attempt + 1}次重试...")
                    continue
                else:
                    logger.error("东方财富API请求多次超时，放弃重试")
                    raise
            except Exception as e:
                logger.error(f"东方财富API请求异常: {e}")
                raise
        
        logger.info(f"东方财富API请求: {url}?{requests.compat.urlencode(params)}")
        logger.info(f"东方财富API响应状态: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = json.loads(response.text)
                logger.info(f"东方财富API响应数据结构: {list(data.keys()) if data else 'None'}")
                
                # 添加更详细的调试信息
                if data and 'data' in data:
                    logger.info(f"data字段存在: {data['data'] is not None}")
                    if data['data']:
                        logger.info(f"data字段内容: {list(data['data'].keys()) if isinstance(data['data'], dict) else type(data['data'])}")
                        if isinstance(data['data'], dict) and 'trends' in data['data']:
                            logger.info(f"trends字段存在: {data['data']['trends'] is not None}")
                            if data['data']['trends']:
                                logger.info(f"trends数据类型: {type(data['data']['trends'])}")
                                if isinstance(data['data']['trends'], list):
                                    logger.info(f"trends数据长度: {len(data['data']['trends'])}")
                
                if data and 'data' in data and data['data'] and 'trends' in data['data']:
                    trends = data['data']['trends']
                    logger.info(f"东方财富分时数据点数量: {len(trends) if trends else 0}")
                    
                    if trends and len(trends) > 50:  # 确保有足够的分时数据
                        timeshare_data = []
                        for i, trend in enumerate(trends):
                            # 东方财富分时数据格式: "日期时间,开盘,最高,最低,收盘,成交量,成交额,均价"
                            parts = trend.split(',')
                            logger.debug(f"处理第{i}个数据点: {trend}, 字段数: {len(parts)}")
                            
                            if len(parts) >= 8:
                                try:
                                    # 时间格式处理：2025-07-15 09:30 -> 09:30
                                    datetime_str = parts[0]
                                    if ' ' in datetime_str:
                                        time_str = datetime_str.split(' ')[1]  # 取时间部分 HH:MM
                                    else:
                                        time_str = datetime_str
                                    
                                    # 过滤掉9:15-9:30的集合竞价数据
                                    if len(time_str) >= 5:
                                        hour_minute = time_str[:5]
                                        if hour_minute >= "09:15" and hour_minute <= "09:30":
                                            logger.debug(f"跳过集合竞价时间段数据: {time_str}")
                                            continue
                                    
                                    # 获取价格数据 (使用收盘价作为当前价格)
                                    open_price = float(parts[1])
                                    high_price = float(parts[2])
                                    low_price = float(parts[3])
                                    close_price = float(parts[4])  # 当前价格
                                    volume = int(parts[5]) if parts[5] and parts[5] != '0' else 0
                                    amount = float(parts[6]) if parts[6] and parts[6] != '0' else 0
                                    avg_price = float(parts[7]) if parts[7] and parts[7] != '0' else close_price
                                    
                                    timeshare_data.append({
                                        'time': time_str,
                                        'price': close_price,
                                        'volume': volume,
                                        'amount': amount,
                                        'open': open_price,
                                        'high': high_price,
                                        'low': low_price,
                                        'avg_price': avg_price
                                    })
                                except (ValueError, IndexError) as e:
                                    logger.debug(f"跳过无效数据行 {i}: {trend}, 错误: {e}")
                                    continue
                            else:
                                logger.debug(f"数据字段不足，跳过第{i}个数据点: {trend}")
                        
                        if timeshare_data:
                            # 获取股票基础信息
                            stock_basic = get_stock_basic_data(code)
                            
                            # 计算统计信息
                            prices = [d['price'] for d in timeshare_data]
                            volumes = [d['volume'] for d in timeshare_data]
                            
                            logger.info(f"✅ 东方财富分时数据获取成功: {len(timeshare_data)}个数据点")
                            
                            return {
                                'timeshare': timeshare_data,
                                'statistics': {
                                    'current_price': stock_basic['current_price'],
                                    'yesterdayClose': stock_basic['yesterday_close'],
                                    'change_percent': stock_basic['change_percent'],
                                    'change_amount': stock_basic['change_amount'],
                                    'high': max(prices) if prices else stock_basic['high'],
                                    'low': min(prices) if prices else stock_basic['low'],
                                    'volume': sum(volumes) if volumes else stock_basic['volume'],
                                    'turnover': stock_basic['turnover']
                                }
                            }
                        else:
                            logger.warning("东方财富分时数据解析失败：无有效数据")
                    else:
                        logger.warning(f"东方财富分时数据不足: {len(trends) if trends else 0}个数据点")
                else:
                    logger.warning("东方财富分时数据响应格式错误")
                    
            except json.JSONDecodeError:
                logger.warning("东方财富分时数据JSON解析失败")
            except Exception as parse_error:
                logger.warning(f"东方财富分时数据解析异常: {parse_error}")
        else:
            logger.warning(f"东方财富分时数据API响应错误: {response.status_code}")
        
        return None
        
    except Exception as e:
        logger.warning(f"东方财富分时数据获取失败: {e}")
        return None

def get_sina_timeshare_data(code):
    """从新浪财经获取真实分时数据"""
    try:
        # 新浪财经分时数据接口
        market_code = f"{'sh' if code.startswith('6') else 'sz'}{code}"
        url = f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MinlineQuery.getMinlineData"
        
        params = {
            'symbol': market_code,
            'scale': 5  # 5分钟间隔
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        
        if response.status_code == 200:
            # 解析JSON数据
            data_text = response.text
            if data_text and '[' in data_text:
                data_list = json.loads(data_text)
                
                if data_list and len(data_list) > 50:  # 确保有足够的数据点
                    timeshare_data = []
                    for item in data_list:
                        if len(item) >= 4:  # 确保数据完整
                            timeshare_data.append({
                                'time': item[0],  # 时间
                                'price': float(item[1]),  # 价格
                                'volume': int(item[2]) if item[2] else 0,  # 成交量
                                'amount': float(item[3]) if item[3] else 0  # 成交额
                            })
                    
                    if timeshare_data:
                        # 获取股票基础信息
                        stock_basic = get_stock_basic_data(code)
                        
                        # 计算统计信息
                        prices = [d['price'] for d in timeshare_data]
                        volumes = [d['volume'] for d in timeshare_data]
                        
                        return {
                            'timeshare': timeshare_data,
                            'statistics': {
                                'current_price': stock_basic['current_price'],
                                'yesterdayClose': stock_basic['yesterday_close'],
                                'change_percent': stock_basic['change_percent'],
                                'change_amount': stock_basic['change_amount'],
                                'high': max(prices) if prices else stock_basic['high'],
                                'low': min(prices) if prices else stock_basic['low'],
                                'volume': sum(volumes) if volumes else stock_basic['volume'],
                                'turnover': stock_basic['turnover']
                            }
                        }
        
        return None
        
    except Exception as e:
        logger.warning(f"新浪财经分时数据获取失败: {e}")
        return None

def get_eastmoney_l2_tick_data(code):
    """从东方财富获取L2大单逐笔成交数据"""
    try:
        # 东方财富L2逐笔成交数据接口
        market_code = f"1.{code}" if code.startswith('6') else f"0.{code}"
        url = "http://push2.eastmoney.com/api/qt/stock/details/get"
        
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4',
            'fields2': 'f51,f52,f53,f54,f55',
            'pos': '-100000'  # 获取更多历史数据
        }
        
        headers = {
            'Referer': 'http://quote.eastmoney.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        logger.info(f"东方财富L2 API请求: {url}?{requests.compat.urlencode(params)}")
        response = requests.get(url, params=params, headers=headers, timeout=15)
        logger.info(f"东方财富L2 API响应状态: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = json.loads(response.text)
                logger.info(f"东方财富L2 API响应数据结构: {list(data.keys()) if data else 'None'}")
                
                if data and 'data' in data and data['data'] and 'details' in data['data']:
                    details = data['data']['details']
                    logger.info(f"东方财富L2逐笔数据点数量: {len(details) if details else 0}")
                    
                    if details and len(details) > 10:  # 确保有足够的逐笔数据
                        tick_data = []
                        for i, detail in enumerate(details):
                            # 东方财富逐笔数据格式: "时间,价格,成交量(手),成交金额,买卖方向"
                            if isinstance(detail, str):
                                parts = detail.split(',')
                                if len(parts) >= 5:
                                    try:
                                        time_str = parts[0]  # 时间 HH:MM:SS
                                        price = float(parts[1])  # 成交价
                                        volume = int(parts[2])  # 成交量(手)
                                        amount_field = int(parts[3]) if parts[3].isdigit() else 0  # 成交金额字段
                                        direction = int(parts[4])  # 买卖方向
                                        
                                        # 计算成交金额 - 假设volume是手数，需要×100转为股数，再×价格
                                        amount_yuan = price * volume * 100  # 总金额（元）
                                        
                                        # 判断交易类型（根据东方财富API实际定义）
                                        if direction == 1:
                                            trade_type = 1  # 买入
                                        elif direction == 2:
                                            trade_type = 3  # 卖出
                                        elif direction == 4:
                                            trade_type = 4  # 集合竞价
                                        else:
                                            trade_type = 3  # 中性
                                        
                                        # 只保留大单数据（成交额>=20万）
                                        if amount_yuan >= 200000:
                                            tick_data.append({
                                                'time': time_str,
                                                'price': price,
                                                'volume': volume * 100,  # 转换为股数
                                                'amount': amount_yuan,
                                                'trade_type': trade_type,
                                                'nature': f"方向{direction}"
                                            })
                                            
                                    except (ValueError, IndexError) as e:
                                        logger.debug(f"跳过无效逐笔数据 {i}: {detail}, 错误: {e}")
                                        continue
                        
                        if tick_data:
                            logger.info(f"✅ 东方财富L2逐笔数据获取成功: {len(tick_data)}个大单数据点")
                            return tick_data
                        else:
                            logger.warning("东方财富L2逐笔数据解析失败：无大单数据")
                    else:
                        logger.warning(f"东方财富L2逐笔数据不足: {len(details) if details else 0}个数据点")
                else:
                    logger.warning("东方财富L2逐笔数据响应格式错误")
                    
            except json.JSONDecodeError:
                logger.warning("东方财富L2逐笔数据JSON解析失败")
            except Exception as parse_error:
                logger.warning(f"东方财富L2逐笔数据解析异常: {parse_error}")
        else:
            logger.warning(f"东方财富L2逐笔数据API响应错误: {response.status_code}")
        
        return None
        
    except Exception as e:
        logger.warning(f"东方财富L2逐笔数据获取失败: {e}")
        return None

def get_tencent_timeshare_data(code):
    """从腾讯股票获取真实分时数据"""
    try:
        # 腾讯股票分时数据接口
        market_code = f"{'sh' if code.startswith('6') else 'sz'}{code}"
        url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query"
        
        params = {
            'code': market_code,
            '_var': 'min_data_' + market_code
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://gu.qq.com'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data_text = response.text
            # 去除JSONP包装
            if 'min_data_' in data_text and '=' in data_text:
                json_part = data_text.split('=', 1)[1].strip()
                if json_part.endswith(';'):
                    json_part = json_part[:-1]
                
                data = json.loads(json_part)
                
                if 'data' in data and market_code in data['data']:
                    minute_data = data['data'][market_code]['data']
                    
                    if minute_data and len(minute_data) > 50:  # 确保有足够的数据点
                        timeshare_data = []
                        for item in minute_data:
                            if len(item) >= 2:  # 时间，价格
                                timeshare_data.append({
                                    'time': item[0],  # 时间
                                    'price': float(item[1]),  # 价格
                                    'volume': int(item[2]) if len(item) > 2 and item[2] else 0,  # 成交量
                                })
                        
                        if timeshare_data:
                            # 获取股票基础信息
                            stock_basic = get_stock_basic_data(code)
                            
                            # 计算统计信息
                            prices = [d['price'] for d in timeshare_data]
                            volumes = [d['volume'] for d in timeshare_data]
                            
                            return {
                                'timeshare': timeshare_data,
                                'statistics': {
                                    'current_price': stock_basic['current_price'],
                                    'yesterdayClose': stock_basic['yesterday_close'],
                                    'change_percent': stock_basic['change_percent'],
                                    'change_amount': stock_basic['change_amount'],
                                    'high': max(prices) if prices else stock_basic['high'],
                                    'low': min(prices) if prices else stock_basic['low'],
                                    'volume': sum(volumes) if volumes else stock_basic['volume'],
                                    'turnover': stock_basic['turnover']
                                }
                            }
        
        return None
        
    except Exception as e:
        logger.warning(f"腾讯股票分时数据获取失败: {e}")
        return None

def get_eastmoney_money_flow_data(code):
    """从东方财富获取主力、散户净流入流出数据"""
    try:
        # 东方财富资金流向接口
        market_code = f"1.{code}" if code.startswith('6') else f"0.{code}"
        url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        
        params = {
            'fields1': 'f1,f2,f3,f7',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65',
            'klt': '1',  # 1分钟
            'fqt': '1',  # 前复权
            'secid': market_code,
            'beg': '0',  # 开始位置
            'end': '20500101',  # 结束日期
            'lmt': '256'  # 限制数量
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com'
        }
        
        # 增加超时时间并添加重试机制
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=15)
                break
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    logger.warning(f"东方财富资金流向API请求超时，第{attempt + 1}次重试...")
                    continue
                else:
                    logger.error("东方财富资金流向API请求多次超时，放弃重试")
                    raise
            except Exception as e:
                logger.error(f"东方财富资金流向API请求异常: {e}")
                raise
        
        logger.info(f"东方财富资金流向API请求: {url}?{requests.compat.urlencode(params)}")
        logger.info(f"东方财富资金流向API响应状态: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = json.loads(response.text)
                logger.info(f"东方财富资金流向API响应数据结构: {list(data.keys()) if data else 'None'}")
                
                if data and 'data' in data and data['data'] and 'klines' in data['data']:
                    klines = data['data']['klines']
                    logger.info(f"东方财富资金流向数据点数量: {len(klines) if klines else 0}")
                    
                    if klines and len(klines) > 0:
                        zhuli_data = []  # 主力净流入
                        sanhu_data = []  # 散户净流入
                        
                        for kline in klines:
                            # 东方财富资金流向数据格式: "时间,主力净流入,超大单净流入,大单净流入,中单净流入,小单净流入"
                            parts = kline.split(',')
                            
                            if len(parts) >= 6:
                                try:
                                    # 主力净流入 = 超大单净流入 + 大单净流入
                                    super_large_net_inflow = float(parts[2]) if parts[2] and parts[2] != '0' else 0
                                    large_net_inflow = float(parts[3]) if parts[3] and parts[3] != '0' else 0
                                    zhuli_net_inflow = super_large_net_inflow + large_net_inflow
                                    
                                    # 散户净流入 = 小单净流入
                                    sanhu_net_inflow = float(parts[5]) if parts[5] and parts[5] != '0' else 0
                                    
                                    # 转换为万元单位，保留3位小数
                                    # 注意：正值表示净流入，负值表示净流出
                                    # 根据业务需求，可能需要反转符号
                                    zhuli_data.append(f"{zhuli_net_inflow/10000:.3f}")
                                    sanhu_data.append(f"{sanhu_net_inflow/10000:.3f}")
                                    
                                except (ValueError, IndexError) as e:
                                    logger.debug(f"跳过无效资金流向数据: {kline}, 错误: {e}")
                                    # 添加默认值
                                    zhuli_data.append("0.000")
                                    sanhu_data.append("0.000")
                                    continue
                            else:
                                logger.debug(f"资金流向数据字段不足: {kline}")
                                # 添加默认值
                                zhuli_data.append("0.000")
                                sanhu_data.append("0.000")
                        
                        if zhuli_data and sanhu_data:
                            logger.info(f"✅ 东方财富资金流向数据获取成功: {len(zhuli_data)}个数据点")
                            
                            return {
                                'zhuli': zhuli_data,
                                'sanhu': sanhu_data
                            }
                        else:
                            logger.warning("东方财富资金流向数据解析失败：无有效数据")
                    else:
                        logger.warning(f"东方财富资金流向数据不足: {len(klines) if klines else 0}个数据点")
                else:
                    logger.warning("东方财富资金流向数据响应格式错误")
                    
            except json.JSONDecodeError:
                logger.warning("东方财富资金流向数据JSON解析失败")
            except Exception as parse_error:
                logger.warning(f"东方财富资金流向数据解析异常: {parse_error}")
        else:
            logger.warning(f"东方财富资金流向数据API响应错误: {response.status_code}")
        
        return None
        
    except Exception as e:
        logger.warning(f"东方财富资金流向数据获取失败: {e}")
        return None

@stock_timeshare_bp.route('/api/stock/timeshare', methods=['GET'])
def get_timeshare_data():
    """获取分时数据 - 仅使用东方财富数据源"""
    code = request.args.get('code', '000001')
    date_param = request.args.get('date', request.args.get('dt'))
    
    try:
        # 标准化股票代码格式
        if len(code) > 6:
            code = code[-6:]  # 取后6位
            logger.info(f"股票代码标准化: {code}")
        
        # 获取有效的交易日期
        trading_date = validate_and_get_trading_date(date_param)
        logger.info(f"开始获取{code}在{trading_date}的东方财富分时数据...")
        
        # 仅使用东方财富分时数据API
        eastmoney_timeshare = get_eastmoney_timeshare_data(code)
        if eastmoney_timeshare:
            # 添加日期信息到返回数据
            eastmoney_timeshare['trading_date'] = trading_date
            logger.info(f"✅ 使用东方财富获取{code}在{trading_date}分时数据成功")
            return success_response(
                data=eastmoney_timeshare,
                message=f'success - 东方财富分时数据 ({trading_date})'
            )
        
        # 东方财富数据获取失败，返回错误
        error_msg = f"无法获取股票{code}的东方财富分时数据"
        logger.error(error_msg)
        return error_response(message=error_msg)
        
    except Exception as e:
        error_msg = f"获取股票{code}分时数据时发生异常: {str(e)}"
        logger.error(error_msg)
        return error_response(message=error_msg)

@stock_timeshare_bp.route('/api/v1/quote', methods=['GET'])
def get_quote():
    """竞品格式 - 数据源/行情接口"""
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        # 标准化股票代码格式
        if len(code) > 6:
            code = code[-6:]  # 取后6位
            logger.info(f"股票代码标准化: {code}")
        
        # 直接获取东方财富分时数据，避免重复调用API
        eastmoney_timeshare = get_eastmoney_timeshare_data(code)
        if not eastmoney_timeshare:
            error_msg = f"无法获取股票{code}的东方财富分时数据"
            logger.error(error_msg)
            return v1_error_response(message=error_msg)
        
        ts_data = eastmoney_timeshare['timeshare']
        stats = eastmoney_timeshare['statistics']
        
                # 提取分时价格数据为fenshi数组
        fenshi = []
        volume = []
        
        # 获取主力、散户净流入流出数据
        money_flow_data = get_eastmoney_money_flow_data(code)
        if money_flow_data:
            zhuli_raw = money_flow_data['zhuli']
            sanhu_raw = money_flow_data['sanhu']
            logger.info(f"✅ 获取到主力数据: {len(zhuli_raw)}个点, 散户数据: {len(sanhu_raw)}个点")
            
            # 过滤掉9:15-9:30的数据，确保与分时数据同步
            zhuli = []
            sanhu = []
            for i, item in enumerate(ts_data):
                time_str = item['time']
                if len(time_str) >= 5:
                    hour_minute = time_str[:5]
                    # 跳过9:15到9:30之间的数据
                    if hour_minute >= "09:15" and hour_minute <= "09:30":
                        continue
                
                # 添加对应的主力、散户数据
                if i < len(zhuli_raw):
                    zhuli.append(zhuli_raw[i])
                else:
                    zhuli.append("0.000")
                    
                if i < len(sanhu_raw):
                    sanhu.append(sanhu_raw[i])
                else:
                    sanhu.append("0.000")
        else:
            # 如果获取失败，生成默认数据
            zhuli = []
            sanhu = []
            for item in ts_data:
                time_str = item['time']
                if len(time_str) >= 5:
                    hour_minute = time_str[:5]
                    # 跳过9:15到9:30之间的数据
                    if hour_minute >= "09:15" and hour_minute <= "09:30":
                        continue
                
                zhuli.append("0.000")
                sanhu.append("0.000")
            logger.warning("资金流向数据获取失败，使用默认值")
        
        for item in ts_data:
            # 过滤掉9:15-9:30的集合竞价数据
            time_str = item['time']
            if len(time_str) >= 5:  # 确保时间格式正确
                hour_minute = time_str[:5]  # 取HH:MM部分
                # 跳过9:15到9:30之间的数据
                if hour_minute >= "09:15" and hour_minute <= "09:30":
                    continue
            
            # 价格数据
            fenshi.append(str(item['price']))
            # 成交量数据，乘以100
            volume.append(item['volume'] * 100)
        
        # 获取L2大单逐笔成交数据
        l2_tick_data = get_eastmoney_l2_tick_data(code)
        
        # 构建big_map数据
        big_map = {}
        if l2_tick_data:
            logger.info(f"开始处理{len(l2_tick_data)}条L2数据，组装big_map...")
            
            # 按时间分组L2数据
            time_groups = {}
            for tick in l2_tick_data:
                time_key = tick['time'][:5]  # 取HH:MM部分作为key
                # 过滤掉9:15-9:30的集合竞价时间
                if time_key >= "09:15" and time_key <= "09:30":
                    continue
                if time_key not in time_groups:
                    time_groups[time_key] = []
                time_groups[time_key].append(tick)
            
            logger.info(f"L2数据按时间分组完成，共{len(time_groups)}个时间点")
            
            # 为每个时间点生成big_map数据
            for time_key, ticks in time_groups.items():
                big_map[time_key] = []
                for tick in ticks:
                    # 添加大单数据，格式：{"t": 交易类型, "v": "成交金额"}
                    # 将成交金额除以10000并取整
                    amount_in_wan = int(tick['amount'] / 10000)
                    big_map[time_key].append({
                        't': tick['trade_type'],  # 交易类型：1=买入，2=卖出，3=中性，4=其他
                        'v': str(amount_in_wan)  # 成交金额（万元），取整
                    })
            
            logger.info(f"✅ big_map组装完成，共{len(big_map)}个时间点，包含大单数据")
        else:
            logger.warning("未获取到L2大单数据，生成空的big_map结构")
            # 从分时数据中提取时间点，确保覆盖到15:00
            time_points = set()
            for item in ts_data:
                time_key = item['time'][:5]  # 取HH:MM部分
                # 过滤掉9:15-9:30的集合竞价时间
                if time_key >= "09:15" and time_key <= "09:30":
                    continue
                time_points.add(time_key)
            
            # 确保包含关键时间点（排除9:15-9:30）
            key_times = ['09:30', '10:00', '11:00', '13:00', '14:00', '15:00']
            for key_time in key_times:
                time_points.add(key_time)
            
            # 按时间排序
            sorted_times = sorted(list(time_points))
            
            # 生成空的big_map结构
            for time_point in sorted_times:
                big_map[time_point] = []
        
        # 构建符合quote.json格式的返回数据
        result = {
            'code': 0,
            'msg': '操作成功',
            'data': {
                'base_info': {
                    'd300ave_percent': f"{stats['change_percent']:.2f}%",
                    'highPrice': str(stats['high']),
                    'lowPrice': str(stats['low']),
                    'prevClosePrice': str(stats['yesterdayClose']),
                    'yi_dong': ""
                },
                'big_map': big_map,
                'fenshi': fenshi,
                'volume': volume,
                'sanhu': sanhu,
                'zhuli': zhuli
            }
        }
        
        logger.info(f"✅ 成功生成竞品格式数据: {len(fenshi)}个价格点, {len(volume)}个成交量点, {len(big_map)}个时间点的大单数据")
        return v1_success_response(data=result['data'])
    except Exception as e:
        logger.error(f"获取行情数据失败: {e}")
        return v1_error_response(message=f'获取行情数据失败: {str(e)}') 