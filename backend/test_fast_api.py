#!/usr/bin/env python3
# 简化测试版本
from flask import Flask, jsonify, request
from datetime import datetime
import requests
import time

app = Flask(__name__)

def get_sina_stock_data_fast(code):
    """快速获取新浪股票数据"""
    try:
        market_code = f"{'sh' if code.startswith('6') else 'sz'}{code}"
        url = f"https://hq.sinajs.cn/list={market_code}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=2)
        response.encoding = 'gbk'
        
        if response.status_code == 200 and 'var hq_str_' in response.text:
            data_str = response.text.split('"')[1]
            data_parts = data_str.split(',')
            
            if len(data_parts) >= 32:
                current_price = float(data_parts[3]) if data_parts[3] else 0
                yesterday_close = float(data_parts[2]) if data_parts[2] else 0
                
                return {
                    'name': data_parts[0],
                    'current_price': current_price,
                    'change_percent': ((current_price - yesterday_close) / yesterday_close * 100) if yesterday_close > 0 else 0,
                    'source': 'sina_fast'
                }
        return None
    except:
        return None

@app.route('/api/v1/dadantongji', methods=['GET'])
def get_dadan_statistics_fast():
    """快速大单统计接口"""
    code = request.args.get('code', '603001')
    
    # 快速获取股票数据
    stock_data = get_sina_stock_data_fast(code)
    
    if stock_data:
        # 基于真实数据生成统计
        change_percent = stock_data.get('change_percent', 0)
        
        # 根据涨跌幅模拟大单活跃度
        if change_percent > 5:  # 大涨
            multiplier = 1.5
        elif change_percent > 0:  # 上涨
            multiplier = 1.2
        else:  # 下跌
            multiplier = 0.8
            
        statistics_data = {
            "buy_nums_300": str(int(2 * multiplier)),
            "buy_amount_300": f"{1825.25 * multiplier:.2f}",
            "sell_nums_300": str(int(5 * multiplier)), 
            "sell_amount_300": f"{2800.08 * multiplier:.2f}",
            
            "buy_nums_100": str(int(4 * multiplier)),
            "buy_amount_100": f"{733.08 * multiplier:.2f}",
            "sell_nums_100": str(int(7 * multiplier)),
            "sell_amount_100": f"{1217.15 * multiplier:.2f}",
            
            "buy_nums_50": str(int(3 * multiplier)),
            "buy_amount_50": f"{161.41 * multiplier:.2f}",
            "sell_nums_50": str(int(2 * multiplier)),
            "sell_amount_50": f"{95.50 * multiplier:.2f}",
            
            "buy_nums_30": str(int(5 * multiplier)),
            "buy_amount_30": f"{185.20 * multiplier:.2f}",
            "sell_nums_30": str(int(8 * multiplier)),
            "sell_amount_30": f"{298.15 * multiplier:.2f}",
            
            "buy_nums_below_30": str(int(1256 * multiplier)),
            "buy_amount_below_30": f"{2825.50 * multiplier:.2f}",
            "sell_nums_below_30": str(int(1389 * multiplier)),
            "sell_amount_below_30": f"{3156.75 * multiplier:.2f}",
            
            "buy_nums_below_50": str(int(1261 * multiplier)),
            "buy_amount_below_50": f"{3010.70 * multiplier:.2f}",
            "sell_nums_below_50": str(int(1397 * multiplier)),
            "sell_amount_below_50": f"{3454.90 * multiplier:.2f}",
            
            "total_buy_amount": f"{5930.44 * multiplier:.2f}",
            "total_sell_amount": f"{7567.63 * multiplier:.2f}"
        }
    else:
        # 默认数据
        statistics_data = {
            "buy_nums_300": "2",
            "buy_amount_300": "1825.25",
            "sell_nums_300": "5", 
            "sell_amount_300": "2800.08",
            "buy_nums_100": "4",
            "buy_amount_100": "733.08",
            "sell_nums_100": "7",
            "sell_amount_100": "1217.15",
            "buy_nums_50": "3",
            "buy_amount_50": "161.41",
            "sell_nums_50": "2",
            "sell_amount_50": "95.50",
            "buy_nums_30": "5",
            "buy_amount_30": "185.20",
            "sell_nums_30": "8",
            "sell_amount_30": "298.15",
            "buy_nums_below_30": "1256",
            "buy_amount_below_30": "2825.50",
            "sell_nums_below_30": "1389",
            "sell_amount_below_30": "3156.75",
            "buy_nums_below_50": "1261",
            "buy_amount_below_50": "3010.70",
            "sell_nums_below_50": "1397",
            "sell_amount_below_50": "3454.90",
            "total_buy_amount": "5930.44",
            "total_sell_amount": "7567.63"
        }
    
    return jsonify({
        "code": 0,
        "msg": "操作成功 (快速API)",
        "data": statistics_data
    })

if __name__ == '__main__':
    print("🚀 启动快速测试API服务...")
    app.run(debug=False, host='0.0.0.0', port=9002)
