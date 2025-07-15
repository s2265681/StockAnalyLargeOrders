#!/usr/bin/env python3
import requests
import json
import time

def test_dadan_api():
    """测试大单统计接口"""
    base_url = "http://localhost:9001"
    
    test_cases = [
        {"code": "603001", "name": "奥康国际"},
        {"code": "000001", "name": "平安银行"}
    ]
    
    print("🔍 测试大单统计接口修改...")
    print("=" * 50)
    
    for case in test_cases:
        print(f"\n📊 测试股票: {case['name']} ({case['code']})")
        
        try:
            url = f"{base_url}/api/v1/dadantongji?code={case['code']}&dt=2025-01-16"
            
            # 设置较短的超时时间
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ 接口调用成功")
                print(f"   📈 响应代码: {data.get('code', 'N/A')}")
                print(f"   📝 响应消息: {data.get('msg', 'N/A')}")
                
                # 检查数据字段
                stats = data.get('data', {})
                if stats:
                    print(f"   💰 总买入: {stats.get('total_buy_amount', '0')} 万元")
                    print(f"   💸 总卖出: {stats.get('total_sell_amount', '0')} 万元")
                    print(f"   🔥 超大单买入: {stats.get('buy_nums_300', '0')} 笔")
                    print(f"   🔥 超大单卖出: {stats.get('sell_nums_300', '0')} 笔")
                else:
                    print(f"   ⚠️  数据字段为空")
            else:
                print(f"   ❌ HTTP错误: {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ 请求超时（5秒）")
        except requests.exceptions.ConnectionError:
            print(f"   🔌 连接错误（服务可能未启动）")
        except Exception as e:
            print(f"   ❌ 其他错误: {e}")
    
    print("\n" + "=" * 50)
    print("✅ 测试完成")

if __name__ == "__main__":
    test_dadan_api()
