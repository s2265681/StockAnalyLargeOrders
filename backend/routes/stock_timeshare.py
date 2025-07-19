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
        
        response = requests.get(url, params=params, headers=headers, timeout=8)
        
        logger.info(f"东方财富API请求: {url}?{requests.compat.urlencode(params)}")
        logger.info(f"东方财富API响应状态: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = json.loads(response.text)
                logger.info(f"东方财富API响应数据结构: {list(data.keys()) if data else 'None'}")
                
                if data and 'data' in data and data['data'] and 'trends' in data['data']:
                    trends = data['data']['trends']
                    logger.info(f"东方财富分时数据点数量: {len(trends) if trends else 0}")
                    
                    if trends and len(trends) > 50:  # 确保有足够的分时数据
                        timeshare_data = []
                        for i, trend in enumerate(trends):
                            # 东方财富分时数据格式: "日期时间,开盘,最高,最低,收盘,成交量,成交额,均价"
                            parts = trend.split(',')
                            if len(parts) >= 8:
                                try:
                                    # 时间格式处理：2025-07-15 09:30 -> 09:30
                                    datetime_str = parts[0]
                                    if ' ' in datetime_str:
                                        time_str = datetime_str.split(' ')[1]  # 取时间部分 HH:MM
                                    else:
                                        time_str = datetime_str
                                    
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

@stock_timeshare_bp.route('/api/stock/timeshare', methods=['GET'])
def get_timeshare_data():
    """获取分时数据 - 优先使用AKShare，失败时使用其他数据源"""
    code = request.args.get('code', '000001')
    date_param = request.args.get('date', request.args.get('dt'))
    
    try:
        # 获取有效的交易日期
        trading_date = validate_and_get_trading_date(date_param)
        logger.info(f"开始获取{code}在{trading_date}的真实分时数据...")
        
        # 1. 优先尝试AKShare分时数据API（最高优先级）
        akshare_timeshare = get_akshare_timeshare_data(code, trading_date)
        if akshare_timeshare:
            # 添加日期信息到返回数据
            akshare_timeshare['trading_date'] = trading_date
            logger.info(f"✅ 使用AKShare获取{code}在{trading_date}分时数据成功")
            return success_response(
                data=akshare_timeshare,
                message=f'success - AKShare分时数据 ({trading_date})'
            )
        
        # 2. 备用：尝试东方财富分时数据API
        eastmoney_timeshare = get_eastmoney_timeshare_data(code)
        if eastmoney_timeshare:
            logger.info(f"✅ 使用东方财富获取{code}分时数据成功")
            return success_response(
                data=eastmoney_timeshare,
                message='success - 东方财富分时数据'
            )
        
        # 3. 备用：尝试新浪财经分时数据API
        sina_timeshare = get_sina_timeshare_data(code)
        if sina_timeshare:
            logger.info(f"✅ 使用新浪财经获取{code}分时数据成功")
            return success_response(
                data=sina_timeshare,
                message='success - 新浪财经分时数据'
            )
        
        # 4. 备用：尝试腾讯分时数据API 
        tencent_timeshare = get_tencent_timeshare_data(code)
        if tencent_timeshare:
            logger.info(f"✅ 使用腾讯股票获取{code}分时数据成功")
            return success_response(
                data=tencent_timeshare,
                message='success - 腾讯股票分时数据'
            )
        
        # 5. 备用：尝试efinance分时数据
        try:
            import efinance as ef
            ef_data = ef.stock.get_quote_history(code, klt=1)
            
            if ef_data is not None and not ef_data.empty:
                # 转换数据格式 - 获取今日的分时数据
                data = []
                today = datetime.now().strftime('%Y-%m-%d')
                
                for _, row in ef_data.iterrows():
                    row_date = str(row['日期'])
                    if today in row_date:  # 只取今日数据
                        time_part = row_date.split(' ')[-1] if ' ' in row_date else row_date[-5:]
                        data.append({
                            'time': time_part,
                            'price': float(row['收盘']),
                            'volume': int(row['成交量'])
                        })
                
                if data and len(data) >= 100:  # 确保有足够的分时数据
                    # 获取基础股票信息
                    stock_basic = get_stock_basic_data(code)
                    
                    # 计算统计信息
                    prices = [d['price'] for d in data]
                    volumes = [d['volume'] for d in data]
                    
                    logger.info(f"✅ 使用efinance获取{code}分时数据成功，共{len(data)}个数据点")
                    return success_response(
                        data={
                            'timeshare': data,
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
                        },
                        message=f'success - efinance分时数据，共{len(data)}个数据点'
                    )
                else:
                    logger.warning(f"efinance返回的分时数据不足: {len(data) if data else 0}个数据点")
                    
        except Exception as ef_error:
            logger.warning(f"efinance获取分时数据失败: {ef_error}")
        
        # 所有真实数据源都失败，返回错误
        error_msg = f"无法获取股票{code}的真实分时数据：所有数据源都失败"
        logger.error(error_msg)
        return error_response(message=error_msg)
        
    except Exception as e:
        error_msg = f"获取股票{code}分时数据时发生异常: {str(e)}"
        logger.error(error_msg)
        return error_response(message=error_msg)

@stock_timeshare_bp.route('/api/v1/quote', methods=['GET'])
def get_quote():
    """竞品格式 - 数据源/行情接口"""
    code = request.args.get('code', '603001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        # 获取分时数据
        timeshare_response = get_timeshare_data()
        timeshare_data = timeshare_response.get_json()
        
        if timeshare_data['code'] == 200:
            ts_data = timeshare_data['data']['timeshare']
            stats = timeshare_data['data']['statistics']
            
            # 转换为竞品格式的分时数据
            quote_data = []
            for item in ts_data:
                quote_data.append({
                    'time': item['time'].split(' ')[1] if ' ' in item['time'] else item['time'][-5:],  # 只保留时间部分
                    'price': item['price'],
                    'volume': item['volume'],
                    'amount': round(item['price'] * item['volume'], 2),
                    'avg_price': item['price'],  # 简化处理，实际应计算累计均价
                    'change_percent': round((item['price'] - stats['yesterdayClose']) / stats['yesterdayClose'] * 100, 2)
                })
            
            # 计算均价线
            total_amount = 0
            total_volume = 0
            avg_prices = []
            
            for item in quote_data:
                total_amount += item['amount']
                total_volume += item['volume']
                avg_price = total_amount / total_volume if total_volume > 0 else item['price']
                avg_prices.append(avg_price)
                item['avg_price'] = round(avg_price, 2)
            
            result = {
                'code': code,
                'date': dt,
                'timeshare': quote_data[-240:],  # 最近240个数据点
                'yesterday_close': stats['yesterdayClose'],
                'current_price': stats['current_price'],
                'high': stats['high'],
                'low': stats['low'],
                'volume': stats['volume'],
                'turnover': stats['turnover'],
                'change_percent': stats['change_percent'],
                'change_amount': stats['change_amount'],
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return v1_success_response(data=result)
        else:
            raise Exception("获取分时数据失败")
            
    except Exception as e:
        logger.error(f"获取行情数据失败: {e}")
        return v1_error_response(message=f'获取行情数据失败: {str(e)}') 