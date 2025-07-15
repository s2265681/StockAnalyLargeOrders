#!/usr/bin/env python3
"""
简化的数据源测试脚本 - 单独测试每个数据源
"""

import requests
import json
import time

def test_sina_api(code='603001'):
    """测试新浪财经API"""
    try:
        print(f"🔍 测试新浪财经API - {code}")
        market_code = f"{'sh' if code.startswith('6') else 'sz'}{code}"
        url = f"https://hq.sinajs.cn/list={market_code}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn'
        }
        
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=5)
        response_time = (time.time() - start_time) * 1000
        
        response.encoding = 'gbk'
        
        if response.status_code == 200 and 'var hq_str_' in response.text:
            data_line = response.text.strip()
            if '="";' in data_line:
                print("   ❌ 数据为空")
                return False
                
            data_str = data_line.split('"')[1]
            data_parts = data_str.split(',')
            
            if len(data_parts) >= 32:
                name = data_parts[0]
                current_price = float(data_parts[3]) if data_parts[3] else 0
                yesterday_close = float(data_parts[2]) if data_parts[2] else 0
                volume = int(float(data_parts[8])) if data_parts[8] else 0
                
                print(f"   ✅ 连接成功: {name}, 价格: {current_price}, 响应时间: {response_time:.0f}ms")
                return True
        
        print(f"   ❌ 数据格式错误")
        return False
        
    except Exception as e:
        print(f"   ❌ 连接失败: {e}")
        return False

def test_tencent_api(code='603001'):
    """测试腾讯股票API"""
    try:
        print(f"🔍 测试腾讯股票API - {code}")
        market_code = f"{'sh' if code.startswith('6') else 'sz'}{code}"
        url = f"https://qt.gtimg.cn/q={market_code}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://gu.qq.com'
        }
        
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=5)
        response_time = (time.time() - start_time) * 1000
        
        response.encoding = 'gbk'
        
        if response.status_code == 200 and '~' in response.text:
            data_str = response.text.split('"')[1]
            data_parts = data_str.split('~')
            
            if len(data_parts) >= 47:
                name = data_parts[1]
                current_price = float(data_parts[3]) if data_parts[3] else 0
                yesterday_close = float(data_parts[4]) if data_parts[4] else 0
                
                print(f"   ✅ 连接成功: {name}, 价格: {current_price}, 响应时间: {response_time:.0f}ms")
                return True
        
        print(f"   ❌ 数据格式错误")
        return False
        
    except Exception as e:
        print(f"   ❌ 连接失败: {e}")
        return False

def test_efinance_api(code='603001'):
    """测试efinance API"""
    try:
        print(f"🔍 测试efinance API - {code}")
        import efinance as ef
        
        start_time = time.time()
        
        # 尝试不同的代码格式
        code_formats = [
            code,
            f"SH{code}" if code.startswith('6') else f"SZ{code}",
            f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
        ]
        
        for code_format in code_formats:
            try:
                stock_data = ef.stock.get_realtime_quotes([code_format])
                if stock_data is not None and not stock_data.empty:
                    response_time = (time.time() - start_time) * 1000
                    stock_info = stock_data.iloc[0]
                    name = stock_info.get('股票名称', '')
                    current_price = float(stock_info.get('最新价', 0))
                    
                    print(f"   ✅ 连接成功: {name}, 价格: {current_price}, 格式: {code_format}, 响应时间: {response_time:.0f}ms")
                    return True
            except Exception as e:
                continue
        
        print(f"   ❌ 所有格式都失败")
        return False
        
    except Exception as e:
        print(f"   ❌ 连接失败: {e}")
        return False

def test_akshare_api(code='603001'):
    """测试akshare API"""
    try:
        print(f"🔍 测试akshare API - {code}")
        import akshare as ak
        
        start_time = time.time()
        stock_info = ak.stock_zh_a_spot_em()
        response_time = (time.time() - start_time) * 1000
        
        if stock_info is not None and not stock_info.empty:
            stock_row = stock_info[stock_info['代码'] == code]
            if not stock_row.empty:
                data = stock_row.iloc[0]
                name = data.get('名称', '')
                current_price = float(data.get('最新价', 0))
                
                print(f"   ✅ 连接成功: {name}, 价格: {current_price}, 响应时间: {response_time:.0f}ms")
                return True
        
        print(f"   ❌ 未找到股票数据")
        return False
        
    except Exception as e:
        print(f"   ❌ 连接失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 简化数据源连接测试")
    print("=" * 50)
    
    test_codes = ['603001', '000001']
    
    for code in test_codes:
        print(f"\n📊 测试股票: {code}")
        print("-" * 30)
        
        results = []
        
        # 测试各个数据源
        results.append(('新浪财经', test_sina_api(code)))
        results.append(('腾讯股票', test_tencent_api(code)))
        results.append(('efinance', test_efinance_api(code)))
        results.append(('akshare', test_akshare_api(code)))
        
        # 统计结果
        success_count = sum(1 for _, success in results if success)
        total_count = len(results)
        
        print(f"\n   📈 总结: {success_count}/{total_count} 个数据源可用")
        
        for name, success in results:
            status = "✅" if success else "❌"
            print(f"   {status} {name}")
    
    print("\n" + "=" * 50)
    print("✅ 测试完成")

if __name__ == "__main__":
    main() 