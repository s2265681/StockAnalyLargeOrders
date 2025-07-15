#!/usr/bin/env python3
"""
测试所有股票数据源的连接性和数据质量
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_data_manager import stock_data_manager
import json
import time

def test_data_sources():
    """测试所有数据源"""
    print("🚀 开始测试股票数据源管理器...")
    print("=" * 60)
    
    # 测试股票代码
    test_codes = ['603001', '000001', '600519']  # 奥康国际、平安银行、贵州茅台
    
    for code in test_codes:
        print(f"\n📊 测试股票: {code}")
        print("-" * 40)
        
        # 测试所有数据源连接性
        results = stock_data_manager.test_all_sources_connectivity(code)
        
        # 获取最优数据
        best_data = stock_data_manager.get_best_stock_data(code)
        
        if best_data:
            print(f"✅ 最优数据获取成功:")
            print(f"   股票名称: {best_data.name}")
            print(f"   当前价格: {best_data.current_price}")
            print(f"   涨跌幅: {best_data.change_percent:.2f}%")
            print(f"   成交量: {best_data.volume}")
            print(f"   数据源: {best_data.source}")
        else:
            print("❌ 未能获取到有效数据")
        
        # 测试大单数据
        large_orders = stock_data_manager.get_large_orders_data(code)
        print(f"📈 大单数据: {len(large_orders)} 条")
        
        time.sleep(1)  # 避免请求过于频繁
    
    # 生成数据源报告
    print("\n" + "=" * 60)
    print("📋 数据源状态报告")
    print("=" * 60)
    
    report = stock_data_manager.get_data_source_report()
    
    print(f"总数据源: {report['total_sources']}")
    print(f"可用数据源: {report['available_count']}")
    print(f"不可用数据源: {report['unavailable_count']}")
    print(f"推荐数据源: {report['recommended_source']}")
    
    print("\n✅ 可用数据源:")
    for source in report['available_sources']:
        print(f"   {source['name']}: 质量{source['quality_score']:.1f}, 响应{source['response_time']:.0f}ms")
    
    if report['unavailable_sources']:
        print("\n❌ 不可用数据源:")
        for source in report['unavailable_sources']:
            print(f"   {source['name']}: {source['error']}")
    
    print(f"\n测试时间: {report['test_time']}")
    
    return report

def main():
    """主函数"""
    try:
        report = test_data_sources()
        
        # 保存测试结果
        with open('data_source_test_result.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 测试结果已保存到 data_source_test_result.json")
        
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 