#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json

def test_new_large_orders_analysis():
    """测试新的基于成交明细的大单分析系统"""
    
    base_url = "http://localhost:9001"
    test_stocks = ['603001', '000001', '000002']
    
    print("=== 测试基于成交明细的大单分析系统 ===")
    
    for stock_code in test_stocks:
        print(f"\n🔍 测试股票: {stock_code}")
        
        try:
            # 测试大单列表API
            print("  📊 测试大单列表...")
            response = requests.get(f"{base_url}/api/stock/large-orders", 
                                  params={'stock_code': stock_code})
            
            if response.status_code == 200:
                data = response.json()
                print(f"    ✅ 成功获取大单数据")
                print(f"    📈 数据源: {data.get('data_source', 'unknown')}")
                print(f"    🔢 分析方法: {data.get('analysis_method', 'unknown')}")
                print(f"    📝 大单数量: {data.get('large_orders_count', 0)}条")
                print(f"    📋 总成交笔数: {data.get('total_trades', 0)}笔")
                
                # 显示前5条大单
                large_orders = data.get('large_orders', [])
                if large_orders:
                    print(f"    🎯 前5条大单:")
                    for i, order in enumerate(large_orders[:5]):
                        print(f"      {i+1}. {order['time']} {order['direction']} "
                              f"{order['amount']:,.0f}元 @{order['price']} ({order['type']})")
                
            else:
                print(f"    ❌ 大单API失败: {response.status_code}")
                print(f"    错误: {response.text}")
            
            # 测试大单统计API
            print("  📈 测试大单统计...")
            response = requests.get(f"{base_url}/api/v1/dadantongji", 
                                  params={'stock_code': stock_code})
            
            if response.status_code == 200:
                data = response.json()
                print(f"    ✅ 成功获取统计数据")
                print(f"    🔢 分析方法: {data.get('analysis_method', 'unknown')}")
                print(f"    📊 大单总数: {data.get('total_large_orders', 0)}条")
                
                # 显示各级别统计
                statistics = data.get('statistics', [])
                if statistics:
                    print(f"    📋 各级别统计:")
                    for stat in statistics:
                        level = stat['level']
                        buy_count = stat['buy_count']
                        sell_count = stat['sell_count']
                        net_count = stat['net_count']
                        print(f"      {level}: {buy_count}买{sell_count}卖 净流入{net_count}笔")
                
            else:
                print(f"    ❌ 统计API失败: {response.status_code}")
                print(f"    错误: {response.text}")
                
        except Exception as e:
            print(f"    💥 测试{stock_code}时出错: {e}")

def test_data_consistency():
    """测试数据一致性"""
    print("\n=== 测试数据一致性 ===")
    
    base_url = "http://localhost:9001"
    stock_code = '603001'
    
    print(f"🔍 测试股票 {stock_code} 的数据一致性...")
    
    try:
        # 连续请求3次，检查数据是否一致
        results = []
        for i in range(3):
            print(f"  第{i+1}次请求...")
            response = requests.get(f"{base_url}/api/v1/dadantongji", 
                                  params={'stock_code': stock_code})
            if response.status_code == 200:
                data = response.json()
                stats = data.get('statistics', [])
                result_summary = {}
                for stat in stats:
                    result_summary[stat['level']] = f"{stat['buy_count']}买{stat['sell_count']}卖"
                results.append(result_summary)
            else:
                print(f"    ❌ 请求失败: {response.status_code}")
                return
        
        # 检查一致性
        all_same = all(result == results[0] for result in results)
        
        if all_same:
            print("  ✅ 数据完全一致！")
            print("  📊 统计结果:")
            for level, count in results[0].items():
                print(f"    {level}: {count}")
        else:
            print("  ❌ 数据不一致！")
            for i, result in enumerate(results):
                print(f"    第{i+1}次结果: {result}")
                
    except Exception as e:
        print(f"  💥 一致性测试出错: {e}")

def test_analysis_quality():
    """测试分析质量"""
    print("\n=== 测试分析质量 ===")
    
    base_url = "http://localhost:9001"
    stock_code = '603001'
    
    try:
        response = requests.get(f"{base_url}/api/stock/large-orders", 
                              params={'stock_code': stock_code})
        
        if response.status_code == 200:
            data = response.json()
            large_orders = data.get('large_orders', [])
            
            if large_orders:
                print(f"  📊 分析质量评估:")
                
                # 检查买卖方向分布
                buy_orders = [o for o in large_orders if o['direction'] == '主买']
                sell_orders = [o for o in large_orders if o['direction'] == '主卖']
                neutral_orders = [o for o in large_orders if o['direction'] == '中性']
                
                print(f"    买单: {len(buy_orders)}笔")
                print(f"    卖单: {len(sell_orders)}笔") 
                print(f"    中性: {len(neutral_orders)}笔")
                
                # 检查金额分布
                amounts = [o['amount'] for o in large_orders]
                if amounts:
                    avg_amount = sum(amounts) / len(amounts)
                    max_amount = max(amounts)
                    min_amount = min(amounts)
                    
                    print(f"    平均金额: {avg_amount:,.0f}元")
                    print(f"    最大金额: {max_amount:,.0f}元")
                    print(f"    最小金额: {min_amount:,.0f}元")
                
                # 检查时间分布
                times = set(o['time'] for o in large_orders)
                print(f"    时间段数: {len(times)}个")
                
                print("  ✅ 分析质量检查完成")
            else:
                print("  ❌ 没有大单数据")
        else:
            print(f"  ❌ 获取数据失败: {response.status_code}")
            
    except Exception as e:
        print(f"  💥 质量测试出错: {e}")

if __name__ == "__main__":
    # 运行所有测试
    test_new_large_orders_analysis()
    test_data_consistency()
    test_analysis_quality()
    
    print("\n🎉 测试完成！") 