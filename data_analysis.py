#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奥康国际(603001)大单数据分析脚本
基于真实接口数据分析主力和散户行为模式
"""

import json
import requests
from datetime import datetime

class StockBigOrderAnalyzer:
    def __init__(self):
        self.base_url = "https://niulaojiu.cn/api/v1"
        self.token = "1d10c95b7b2d4bb05f0fb8be4c4fd2976e145bf2a2a38766d1f711cc8bee0cd81f6818575ea2b0546f3f6cd018ca5a4b"
        self.finger_print = "946a0274e1a1076142e0bb266dc9bedd"
        
        # 真实数据示例 (2025-01-15 奥康国际 603001)
        self.real_data = {
            "buy_nums_300": "0",      # 超大单买入(≥300万)
            "buy_amount_300": "0.00",
            "sell_nums_300": "0", 
            "sell_amount_300": "0.00",
            
            "buy_nums_100": "0",      # 大单买入(≥100万)
            "buy_amount_100": "0.00",
            "sell_nums_100": "0",
            "sell_amount_100": "0.00",
            
            "buy_nums_50": "2",       # 中单买入(≥50万)
            "buy_amount_50": "146.26",
            "sell_nums_50": "5",
            "sell_amount_50": "295.79",
            
            "buy_nums_30": "7",       # 小单买入(≥30万)
            "buy_amount_30": "263.38",
            "sell_nums_30": "14",
            "sell_amount_30": "576.79",
            
            "buy_nums_below_50": "885",   # 散户买入(<50万)
            "buy_amount_below_50": "2411.83",
            "sell_nums_below_50": "887",
            "sell_amount_below_50": "2852.92",
            
            "total_buy_amount": "2660.54",   # 总买入金额
            "total_sell_amount": "3895.84"   # 总卖出金额
        }
    
    def analyze_main_force_vs_retail(self):
        """分析主力资金与散户资金对比"""
        print("=" * 60)
        print("🔍 奥康国际(603001) 主力 vs 散户资金分析")
        print("=" * 60)
        
        # 主力资金定义：≥50万的交易
        main_force_buy_nums = int(self.real_data["buy_nums_50"])
        main_force_buy_amount = float(self.real_data["buy_amount_50"])
        main_force_sell_nums = int(self.real_data["sell_nums_50"])
        main_force_sell_amount = float(self.real_data["sell_amount_50"])
        
        # 散户资金定义：<50万的交易
        retail_buy_nums = int(self.real_data["buy_nums_below_50"])
        retail_buy_amount = float(self.real_data["buy_amount_below_50"])
        retail_sell_nums = int(self.real_data["sell_nums_below_50"])
        retail_sell_amount = float(self.real_data["sell_amount_below_50"])
        
        # 总交易数据
        total_buy = float(self.real_data["total_buy_amount"])
        total_sell = float(self.real_data["total_sell_amount"])
        
        print("📊 主力资金(≥50万):")
        print(f"   买入: {main_force_buy_nums}笔, {main_force_buy_amount:.2f}万元")
        print(f"   卖出: {main_force_sell_nums}笔, {main_force_sell_amount:.2f}万元")
        print(f"   净流入: {main_force_buy_amount - main_force_sell_amount:.2f}万元")
        
        print("\n👥 散户资金(<50万):")
        print(f"   买入: {retail_buy_nums}笔, {retail_buy_amount:.2f}万元")
        print(f"   卖出: {retail_sell_nums}笔, {retail_sell_amount:.2f}万元")
        print(f"   净流入: {retail_buy_amount - retail_sell_amount:.2f}万元")
        
        print(f"\n💰 总体情况:")
        print(f"   总买入: {total_buy:.2f}万元")
        print(f"   总卖出: {total_sell:.2f}万元")
        print(f"   净流入: {total_buy - total_sell:.2f}万元")
        
        # 计算占比
        main_force_buy_ratio = (main_force_buy_amount / total_buy) * 100 if total_buy > 0 else 0
        main_force_sell_ratio = (main_force_sell_amount / total_sell) * 100 if total_sell > 0 else 0
        retail_buy_ratio = (retail_buy_amount / total_buy) * 100 if total_buy > 0 else 0
        retail_sell_ratio = (retail_sell_amount / total_sell) * 100 if total_sell > 0 else 0
        
        print(f"\n📈 资金占比分析:")
        print(f"   主力买入占比: {main_force_buy_ratio:.1f}%")
        print(f"   主力卖出占比: {main_force_sell_ratio:.1f}%")
        print(f"   散户买入占比: {retail_buy_ratio:.1f}%")
        print(f"   散户卖出占比: {retail_sell_ratio:.1f}%")
        
        return {
            "main_force": {
                "buy_amount": main_force_buy_amount,
                "sell_amount": main_force_sell_amount,
                "net_inflow": main_force_buy_amount - main_force_sell_amount,
                "buy_ratio": main_force_buy_ratio,
                "sell_ratio": main_force_sell_ratio
            },
            "retail": {
                "buy_amount": retail_buy_amount,
                "sell_amount": retail_sell_amount,
                "net_inflow": retail_buy_amount - retail_sell_amount,
                "buy_ratio": retail_buy_ratio,
                "sell_ratio": retail_sell_ratio
            }
        }
    
    def analyze_big_order_levels(self):
        """分析不同级别大单统计"""
        print("\n" + "=" * 60)
        print("💎 大单分级统计分析")
        print("=" * 60)
        
        levels = [
            ("超大单(≥300万)", "300", "🔥"),
            ("大单(≥100万)", "100", "🟠"),
            ("中单(≥50万)", "50", "🟡"),
            ("小大单(≥30万)", "30", "🟢")
        ]
        
        for level_name, level_key, emoji in levels:
            buy_nums = int(self.real_data[f"buy_nums_{level_key}"])
            buy_amount = float(self.real_data[f"buy_amount_{level_key}"])
            sell_nums = int(self.real_data[f"sell_nums_{level_key}"])
            sell_amount = float(self.real_data[f"sell_amount_{level_key}"])
            
            net_inflow = buy_amount - sell_amount
            
            print(f"{emoji} {level_name}:")
            print(f"   买入: {buy_nums}笔 | {buy_amount:.2f}万")
            print(f"   卖出: {sell_nums}笔 | {sell_amount:.2f}万")
            
            if net_inflow > 0:
                print(f"   净流入: +{net_inflow:.2f}万 (主力流入)")
            elif net_inflow < 0:
                print(f"   净流出: {net_inflow:.2f}万 (主力流出)")
            else:
                print(f"   净流入: {net_inflow:.2f}万 (持平)")
            print()
    
    def generate_market_sentiment_analysis(self):
        """生成市场情绪分析"""
        print("=" * 60)
        print("🎯 市场情绪与主力动向分析")
        print("=" * 60)
        
        # 主力净流入
        main_force_net = float(self.real_data["buy_amount_50"]) - float(self.real_data["sell_amount_50"])
        # 散户净流入
        retail_net = float(self.real_data["buy_amount_below_50"]) - float(self.real_data["sell_amount_below_50"])
        # 总净流入
        total_net = float(self.real_data["total_buy_amount"]) - float(self.real_data["total_sell_amount"])
        
        print(f"📊 资金流向总结:")
        print(f"   主力资金净流入: {main_force_net:.2f}万")
        print(f"   散户资金净流入: {retail_net:.2f}万")
        print(f"   总资金净流入: {total_net:.2f}万")
        
        # 分析市场情绪
        print(f"\n🔮 市场情绪判断:")
        if main_force_net > 0 and retail_net > 0:
            sentiment = "多方占优，主力与散户一致看多"
            color = "🟢"
        elif main_force_net > 0 and retail_net < 0:
            sentiment = "主力看多，散户分歧，可能有反转机会"
            color = "🟡"
        elif main_force_net < 0 and retail_net > 0:
            sentiment = "主力看空，散户追涨，注意风险"
            color = "🟠"
        elif main_force_net < 0 and retail_net < 0:
            sentiment = "空方占优，主力与散户一致看空"
            color = "🔴"
        else:
            sentiment = "市场观望，资金流入流出基本平衡"
            color = "⚪"
        
        print(f"   {color} {sentiment}")
        
        # 强度分析
        total_volume = float(self.real_data["total_buy_amount"]) + float(self.real_data["total_sell_amount"])
        if total_volume > 0:
            main_force_participation = ((float(self.real_data["buy_amount_50"]) + float(self.real_data["sell_amount_50"])) / total_volume) * 100
            print(f"\n📈 主力参与度: {main_force_participation:.1f}%")
            
            if main_force_participation > 20:
                print("   🔥 主力高度活跃")
            elif main_force_participation > 10:
                print("   🟡 主力适度参与") 
            else:
                print("   🟢 主力参与度较低，以散户为主")
    
    def create_data_structure_analysis(self):
        """分析数据结构和统计逻辑"""
        print("\n" + "=" * 60)
        print("🏗️ 接口数据结构与统计逻辑分析")
        print("=" * 60)
        
        print("📝 接口设计分析:")
        print("1. base_info: 股票基本信息(价格、涨跌幅等)")
        print("2. quote: 分时数据(包含主力线zhuli[]和散户线sanhu[])")
        print("3. dadan: 大单交易明细列表")
        print("4. dadantongji: 大单统计汇总")
        
        print(f"\n🔢 统计分级逻辑:")
        print(f"   ≥300万: 超大单 (机构/大户)")
        print(f"   ≥100万: 大单 (中大型资金)")
        print(f"   ≥50万:  中单 (小型主力)")
        print(f"   ≥30万:  小大单 (准主力)")
        print(f"   <50万:   散户单 (个人投资者)")
        
        print(f"\n📊 关键指标说明:")
        print(f"   buy_nums_xxx: 对应级别买入笔数")
        print(f"   buy_amount_xxx: 对应级别买入金额(万元)")
        print(f"   sell_nums_xxx: 对应级别卖出笔数")
        print(f"   sell_amount_xxx: 对应级别卖出金额(万元)")
        
        print(f"\n🎯 主力识别逻辑:")
        print(f"   主力 = ≥50万的交易 (包含50万、100万、300万级别)")
        print(f"   散户 = <50万的交易")
        print(f"   净流入 = 买入金额 - 卖出金额")
        print(f"   参与度 = (买入+卖出) / 总交易额")

def main():
    """主函数"""
    analyzer = StockBigOrderAnalyzer()
    
    print("🚀 开始分析奥康国际(603001)大单数据...")
    print(f"📅 分析日期: 2025-01-15")
    print(f"📈 股票代码: 603001 (奥康国际)")
    
    # 执行各项分析
    analyzer.analyze_main_force_vs_retail()
    analyzer.analyze_big_order_levels()
    analyzer.generate_market_sentiment_analysis()
    analyzer.create_data_structure_analysis()
    
    print("\n" + "=" * 60)
    print("✅ 分析完成！")
    print("=" * 60)

if __name__ == "__main__":
    main() 