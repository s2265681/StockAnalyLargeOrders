#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time
from datetime import datetime
from collections import defaultdict

def get_sina_tick_data(symbol, date=None):
    """
    获取新浪财经成交明细数据（逐笔数据）
    symbol: 股票代码，如 sh600000, sz000001
    date: 日期，格式 YYYY-MM-DD，默认当日
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    # 新浪成交明细接口
    url = f"http://market.finance.sina.com.cn/downxls.php"
    params = {
        'date': date,
        'symbol': symbol
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            # 解析CSV格式数据
            lines = response.text.strip().split('\n')
            if len(lines) > 1:
                tick_data = []
                for line in lines[1:]:  # 跳过标题行
                    parts = line.split('\t')
                    if len(parts) >= 4:
                        tick_data.append({
                            'time': parts[0],
                            'price': float(parts[1]),
                            'volume': int(parts[2]),
                            'amount': float(parts[1]) * int(parts[2]),
                            'direction': parts[3] if len(parts) > 3 else '中性'
                        })
                return tick_data
    except Exception as e:
        print(f"获取新浪数据失败: {e}")
    
    return []

def get_eastmoney_tick_data(symbol):
    """
    获取东方财富成交明细数据
    """
    # 转换股票代码格式
    if symbol.startswith('6'):
        code = f"1.{symbol}"
    else:
        code = f"0.{symbol}"
    
    url = "http://push2ex.eastmoney.com/getStockFenShi"
    params = {
        'pagesize': '1000',  # 获取更多数据
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
        'dpt': 'wzfscj',
        'cb': 'jQuery112409639903197724653_1640853306115',
        'secid': code,
        '_': int(time.time() * 1000)
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            # 提取JSON数据
            text = response.text
            start = text.find('(') + 1
            end = text.rfind(')')
            json_data = json.loads(text[start:end])
            
            if json_data.get('rc') == 0 and 'data' in json_data:
                data = json_data['data']
                if 'details' in data:
                    tick_data = []
                    for detail in data['details']:
                        parts = detail.split(',')
                        if len(parts) >= 3:
                            tick_data.append({
                                'time': parts[0],
                                'price': float(parts[1]),
                                'volume': int(parts[2]),
                                'amount': float(parts[1]) * int(parts[2]),
                                'direction': determine_direction(parts)
                            })
                    return tick_data
    except Exception as e:
        print(f"获取东方财富数据失败: {e}")
    
    return []

def determine_direction(parts):
    """
    根据成交明细判断买卖方向
    """
    if len(parts) > 3:
        # 如果有买卖方向标识
        direction_flag = parts[3]
        if direction_flag == '1':
            return '买盘'
        elif direction_flag == '2':
            return '卖盘'
    return '中性'

def analyze_tick_data_for_large_orders(tick_data, large_order_threshold=500000):
    """
    基于成交明细数据分析大单交易
    
    Args:
        tick_data: 成交明细数据列表
        large_order_threshold: 大单阈值（金额，默认50万）
    
    Returns:
        dict: 大单分析结果
    """
    large_orders = []
    order_stats = defaultdict(lambda: {'count': 0, 'volume': 0, 'amount': 0})
    
    for tick in tick_data:
        amount = tick['amount']
        direction = tick['direction']
        
        # 识别大单
        if amount >= large_order_threshold:
            large_orders.append({
                'time': tick['time'],
                'price': tick['price'],
                'volume': tick['volume'],
                'amount': amount,
                'direction': direction,
                'type': get_order_type(amount)
            })
        
        # 统计不同金额级别的订单
        order_type = get_order_type(amount)
        order_stats[order_type]['count'] += 1
        order_stats[order_type]['volume'] += tick['volume']
        order_stats[order_type]['amount'] += amount
    
    # 计算大单统计
    large_order_stats = calculate_large_order_stats(large_orders)
    
    return {
        'large_orders': large_orders,
        'order_statistics': dict(order_stats),
        'large_order_stats': large_order_stats,
        'total_orders': len(tick_data),
        'large_orders_count': len(large_orders)
    }

def get_order_type(amount):
    """
    根据金额确定订单类型
    """
    if amount >= 3000000:  # 300万以上
        return '超大单'
    elif amount >= 1000000:  # 100万以上
        return '大单'
    elif amount >= 500000:  # 50万以上
        return '中单'
    elif amount >= 300000:  # 30万以上
        return '小单'
    else:
        return '散单'

def calculate_large_order_stats(large_orders):
    """
    计算大单统计信息
    """
    if not large_orders:
        return {}
    
    buy_orders = [order for order in large_orders if order['direction'] == '买盘']
    sell_orders = [order for order in large_orders if order['direction'] == '卖盘']
    
    stats = {
        'total_count': len(large_orders),
        'buy_count': len(buy_orders),
        'sell_count': len(sell_orders),
        'total_amount': sum(order['amount'] for order in large_orders),
        'buy_amount': sum(order['amount'] for order in buy_orders),
        'sell_amount': sum(order['amount'] for order in sell_orders),
        'net_flow': sum(order['amount'] for order in buy_orders) - sum(order['amount'] for order in sell_orders),
        'average_amount': sum(order['amount'] for order in large_orders) / len(large_orders)
    }
    
    # 按时间分组统计
    time_stats = defaultdict(lambda: {'buy': 0, 'sell': 0})
    for order in large_orders:
        hour = order['time'][:2] if ':' in order['time'] else order['time'][:4]
        if order['direction'] == '买盘':
            time_stats[hour]['buy'] += order['amount']
        elif order['direction'] == '卖盘':
            time_stats[hour]['sell'] += order['amount']
    
    stats['time_distribution'] = dict(time_stats)
    
    return stats

def test_tick_data_sources():
    """
    测试不同数据源的成交明细获取
    """
    test_stocks = ['600000', '000001', '603001']  # 测试股票
    
    print("=== 测试成交明细数据获取 ===")
    
    for stock in test_stocks:
        print(f"\n测试股票: {stock}")
        
        # 测试新浪财经
        print("尝试获取新浪财经数据...")
        sina_data = get_sina_tick_data(f"sh{stock}" if stock.startswith('6') else f"sz{stock}")
        print(f"新浪数据: 获取到 {len(sina_data)} 条记录")
        
        # 测试东方财富
        print("尝试获取东方财富数据...")
        eastmoney_data = get_eastmoney_tick_data(stock)
        print(f"东方财富数据: 获取到 {len(eastmoney_data)} 条记录")
        
        # 选择数据量更多的数据源进行分析
        if sina_data and len(sina_data) > len(eastmoney_data):
            tick_data = sina_data
            source = "新浪财经"
        elif eastmoney_data:
            tick_data = eastmoney_data
            source = "东方财富"
        else:
            print("无法获取到有效数据")
            continue
        
        print(f"使用{source}数据进行大单分析...")
        
        # 进行大单分析
        analysis_result = analyze_tick_data_for_large_orders(tick_data)
        
        print(f"分析结果:")
        print(f"  总成交笔数: {analysis_result['total_orders']}")
        print(f"  大单笔数: {analysis_result['large_orders_count']}")
        
        if analysis_result['large_order_stats']:
            stats = analysis_result['large_order_stats']
            print(f"  大单总金额: {stats['total_amount']:,.0f} 元")
            print(f"  买单数量: {stats['buy_count']} 笔")
            print(f"  卖单数量: {stats['sell_count']} 笔")
            print(f"  净流入: {stats['net_flow']:,.0f} 元")
        
        # 显示订单分布
        print(f"  订单类型分布:")
        for order_type, data in analysis_result['order_statistics'].items():
            print(f"    {order_type}: {data['count']} 笔, {data['amount']:,.0f} 元")

if __name__ == "__main__":
    test_tick_data_sources() 