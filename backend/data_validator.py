import requests
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import efinance as ef
import yfinance as yf
import akshare as ak
import pandas as pd
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def normalize_stock_code(code: str) -> str:
    """标准化股票代码格式"""
    if not code:
        return code
    
    # 去除空格和特殊字符
    code = code.strip().replace(' ', '')
    
    # 如果代码长度不足6位，前面补0
    if len(code) < 6:
        code = code.zfill(6)
    
    # 如果代码长度超过6位，只取前6位
    if len(code) > 6:
        code = code[:6]
    
    # 验证是否为有效的股票代码格式
    if not code.isdigit():
        logger.warning(f"股票代码格式无效: {code}")
        return None
    
    return code

def validate_stock_code(code: str) -> bool:
    """验证股票代码是否有效"""
    if not code:
        return False
    
    # 标准化代码
    normalized_code = normalize_stock_code(code)
    if not normalized_code:
        return False
    
    # 检查是否为有效的A股代码
    # 上海A股：600xxx, 601xxx, 603xxx, 605xxx, 688xxx
    # 深圳A股：000xxx, 001xxx, 002xxx, 003xxx, 300xxx
    first_three = normalized_code[:3]
    valid_prefixes = ['000', '001', '002', '003', '300', '600', '601', '603', '605', '688']
    
    return first_three in valid_prefixes

class StockDataValidator:
    """股票数据验证器 - 多数据源交叉验证"""
    
    def __init__(self):
        self.timeout = 10  # 请求超时时间
        self.retry_count = 3  # 重试次数
        
    def fetch_sina_data(self, code: str) -> Optional[Dict]:
        """从新浪财经获取股票数据"""
        try:
            # 标准化股票代码
            normalized_code = normalize_stock_code(code)
            if not normalized_code or not validate_stock_code(normalized_code):
                logger.warning(f"股票代码无效，跳过新浪数据获取: {code}")
                return None
            
            # 新浪财经API
            url = f"http://hq.sinajs.cn/list={'sh' if normalized_code.startswith('6') else 'sz'}{normalized_code}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.encoding = 'gbk'
            
            if response.status_code == 200:
                content = response.text
                if 'var hq_str_' in content:
                    data_str = content.split('"')[1]
                    data_parts = data_str.split(',')
                    
                    if len(data_parts) >= 31:
                        return {
                            'source': 'sina',
                            'code': normalized_code,
                            'name': data_parts[0],
                            'current_price': float(data_parts[3]) if data_parts[3] else 0,
                            'yesterday_close': float(data_parts[2]) if data_parts[2] else 0,
                            'today_open': float(data_parts[1]) if data_parts[1] else 0,
                            'high': float(data_parts[4]) if data_parts[4] else 0,
                            'low': float(data_parts[5]) if data_parts[5] else 0,
                            'volume': int(float(data_parts[8])) if data_parts[8] else 0,
                            'turnover': float(data_parts[9]) if data_parts[9] else 0,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
        except Exception as e:
            logger.warning(f"新浪财经数据获取失败: {e}")
        return None
    
    def fetch_tencent_data(self, code: str) -> Optional[Dict]:
        """从腾讯股票获取数据"""
        try:
            # 标准化股票代码
            normalized_code = normalize_stock_code(code)
            if not normalized_code or not validate_stock_code(normalized_code):
                logger.warning(f"股票代码无效，跳过腾讯数据获取: {code}")
                return None
            
            # 腾讯股票API
            market_code = f"{'sh' if normalized_code.startswith('6') else 'sz'}{normalized_code}"
            url = f"http://qt.gtimg.cn/q={market_code}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.encoding = 'gbk'
            
            if response.status_code == 200:
                content = response.text
                if '~' in content:
                    data_str = content.split('"')[1]
                    data_parts = data_str.split('~')
                    
                    if len(data_parts) >= 47:
                        current_price = float(data_parts[3]) if data_parts[3] else 0
                        yesterday_close = float(data_parts[4]) if data_parts[4] else 0
                        
                        return {
                            'source': 'tencent',
                            'code': normalized_code,
                            'name': data_parts[1],
                            'current_price': current_price,
                            'yesterday_close': yesterday_close,
                            'today_open': float(data_parts[5]) if data_parts[5] else 0,
                            'high': float(data_parts[33]) if data_parts[33] else 0,
                            'low': float(data_parts[34]) if data_parts[34] else 0,
                            'volume': int(float(data_parts[6])) if data_parts[6] else 0,
                            'turnover': float(data_parts[37]) if data_parts[37] else 0,
                            'change_amount': current_price - yesterday_close,
                            'change_percent': ((current_price - yesterday_close) / yesterday_close * 100) if yesterday_close > 0 else 0,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
        except Exception as e:
            logger.warning(f"腾讯股票数据获取失败: {e}")
        return None
    
    def fetch_efinance_data(self, code: str) -> Optional[Dict]:
        """从efinance获取数据"""
        try:
            # 标准化股票代码
            normalized_code = normalize_stock_code(code)
            if not normalized_code or not validate_stock_code(normalized_code):
                logger.warning(f"股票代码无效，跳过efinance数据获取: {code}")
                return None
            
            # 检查是否为已知无法获取的股票（减少重试）
            known_unavailable_codes = ['603001']  # 奥康国际等已知无法获取的股票
            if normalized_code in known_unavailable_codes:
                logger.debug(f"跳过已知无法获取的股票代码: {normalized_code}")
                return None
            
            # 使用重试机制，但对已知问题股票减少重试次数
            max_attempts = 1 if normalized_code in known_unavailable_codes else self.retry_count
            
            for attempt in range(max_attempts):
                try:
                    # efinance可能需要不同的代码格式，尝试多种格式
                    code_formats = [
                        normalized_code,  # 标准6位代码
                        f"SH{normalized_code}" if normalized_code.startswith('6') else f"SZ{normalized_code}",  # 带市场前缀
                        f"{normalized_code}.SH" if normalized_code.startswith('6') else f"{normalized_code}.SZ"  # 带市场后缀
                    ]
                    
                    for code_format in code_formats:
                        try:
                            stock_data = ef.stock.get_realtime_quotes([code_format])
                            if stock_data is not None and not stock_data.empty:
                                stock_info = stock_data.iloc[0]
                                current_price = float(stock_info.get('最新价', 0))
                                yesterday_close = float(stock_info.get('昨收', 0))
                                
                                # 验证数据有效性
                                if current_price > 0 and yesterday_close > 0:
                                    result = {
                                        'source': 'efinance',
                                        'code': normalized_code,
                                        'name': stock_info.get('股票名称', ''),
                                        'current_price': current_price,
                                        'yesterday_close': yesterday_close,
                                        'today_open': float(stock_info.get('今开', 0)),
                                        'high': float(stock_info.get('最高', 0)),
                                        'low': float(stock_info.get('最低', 0)),
                                        'volume': int(stock_info.get('成交量', 0)),
                                        'turnover': float(stock_info.get('成交额', 0)),
                                        'change_amount': current_price - yesterday_close,
                                        'change_percent': float(stock_info.get('涨跌幅', 0)),
                                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    }
                                    logger.info(f"efinance数据获取成功: {normalized_code} (使用格式: {code_format})")
                                    return result
                                else:
                                    logger.debug(f"efinance返回无效价格数据: {code_format}")
                            else:
                                logger.debug(f"efinance格式{code_format}无数据")
                        except Exception as format_error:
                            logger.debug(f"efinance格式{code_format}失败: {format_error}")
                            continue
                    
                    # 如果所有格式都失败，只在最后一次尝试时记录警告
                    if attempt == max_attempts - 1:
                        logger.warning(f"efinance所有格式都失败，股票代码: {normalized_code}")
                    
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.warning(f"efinance数据获取失败: {e} (股票代码: {normalized_code})")
                    
                if attempt < max_attempts - 1:
                    time.sleep(0.5)  # 减少重试等待时间
                    
        except Exception as e:
            logger.error(f"efinance数据获取异常: {e}")
        
        # 只在debug模式下记录最终失败
        logger.debug(f"efinance数据获取最终失败: {normalized_code}")
        return None
    
    def fetch_akshare_data(self, code: str) -> Optional[Dict]:
        """从akshare获取数据"""
        try:
            # 标准化股票代码
            normalized_code = normalize_stock_code(code)
            if not normalized_code or not validate_stock_code(normalized_code):
                logger.warning(f"股票代码无效，跳过akshare数据获取: {code}")
                return None
            
            # akshare实时行情
            stock_info = ak.stock_zh_a_spot_em()
            if stock_info is not None and not stock_info.empty:
                # 查找对应股票
                stock_row = stock_info[stock_info['代码'] == normalized_code]
                if not stock_row.empty:
                    data = stock_row.iloc[0]
                    current_price = float(data.get('最新价', 0))
                    yesterday_close = float(data.get('昨收', 0))
                    
                    return {
                        'source': 'akshare',
                        'code': normalized_code,
                        'name': data.get('名称', ''),
                        'current_price': current_price,
                        'yesterday_close': yesterday_close,
                        'today_open': float(data.get('今开', 0)),
                        'high': float(data.get('最高', 0)),
                        'low': float(data.get('最低', 0)),
                        'volume': int(float(data.get('成交量', 0))),
                        'turnover': float(data.get('成交额', 0)),
                        'change_amount': current_price - yesterday_close,
                        'change_percent': float(data.get('涨跌幅', 0)),
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
        except Exception as e:
            logger.warning(f"akshare数据获取失败: {e}")
        return None
    
    def validate_pingan_bank_data(self) -> Dict:
        """专门验证平安银行(000001)数据"""
        code = '000001'
        logger.info(f"开始验证平安银行({code})数据...")
        
        # 从多个数据源获取数据
        data_sources = {}
        
        # 获取新浪数据
        sina_data = self.fetch_sina_data(code)
        if sina_data:
            data_sources['sina'] = sina_data
            logger.info(f"新浪财经数据获取成功: 价格={sina_data['current_price']}")
        
        # 获取腾讯数据
        tencent_data = self.fetch_tencent_data(code)
        if tencent_data:
            data_sources['tencent'] = tencent_data
            logger.info(f"腾讯股票数据获取成功: 价格={tencent_data['current_price']}")
        
        # 获取efinance数据
        efinance_data = self.fetch_efinance_data(code)
        if efinance_data:
            data_sources['efinance'] = efinance_data
            logger.info(f"efinance数据获取成功: 价格={efinance_data['current_price']}")
        
        # 获取akshare数据
        akshare_data = self.fetch_akshare_data(code)
        if akshare_data:
            data_sources['akshare'] = akshare_data
            logger.info(f"akshare数据获取成功: 价格={akshare_data['current_price']}")
        
        # 数据验证和分析
        validation_result = self.cross_validate_data(data_sources)
        
        return {
            'stock_code': code,
            'stock_name': '平安银行',
            'validation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_sources': data_sources,
            'validation_result': validation_result,
            'recommendations': self.generate_recommendations(validation_result)
        }
    
    def cross_validate_data(self, data_sources: Dict) -> Dict:
        """交叉验证多源数据"""
        if not data_sources:
            return {
                'status': 'failed',
                'message': '没有可用的数据源',
                'consistency_score': 0
            }
        
        # 提取所有数据源的价格
        prices = []
        volumes = []
        sources = []
        
        for source, data in data_sources.items():
            if data and data.get('current_price', 0) > 0:
                prices.append(data['current_price'])
                volumes.append(data.get('volume', 0))
                sources.append(source)
        
        if len(prices) < 2:
            return {
                'status': 'insufficient_data',
                'message': '数据源不足，无法进行交叉验证',
                'consistency_score': 0
            }
        
        # 计算价格一致性
        price_variance = self.calculate_variance(prices)
        max_price_diff = max(prices) - min(prices)
        avg_price = sum(prices) / len(prices)
        
        # 计算成交量一致性
        volume_variance = self.calculate_variance(volumes) if volumes else 0
        
        # 计算一致性评分 (0-100)
        price_consistency = max(0, 100 - (max_price_diff / avg_price * 100 * 100))  # 价格差异转换为评分
        
        consistency_score = price_consistency
        
        # 判断数据质量
        if consistency_score >= 95:
            status = 'excellent'
            message = '数据高度一致，质量优秀'
        elif consistency_score >= 85:
            status = 'good'
            message = '数据基本一致，质量良好'
        elif consistency_score >= 70:
            status = 'acceptable'
            message = '数据存在轻微差异，质量可接受'
        else:
            status = 'poor'
            message = '数据差异较大，建议谨慎使用'
        
        return {
            'status': status,
            'message': message,
            'consistency_score': round(consistency_score, 2),
            'price_analysis': {
                'avg_price': round(avg_price, 2),
                'min_price': min(prices),
                'max_price': max(prices),
                'price_variance': round(price_variance, 4),
                'max_difference': round(max_price_diff, 2),
                'sources_count': len(sources)
            },
            'volume_analysis': {
                'volumes': volumes,
                'volume_variance': round(volume_variance, 2) if volume_variance else 0
            },
            'active_sources': sources
        }
    
    def calculate_variance(self, values: List[float]) -> float:
        """计算方差"""
        if len(values) < 2:
            return 0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance
    
    def generate_recommendations(self, validation_result: Dict) -> List[str]:
        """根据验证结果生成建议"""
        recommendations = []
        
        consistency_score = validation_result.get('consistency_score', 0)
        status = validation_result.get('status', 'unknown')
        
        if status == 'excellent':
            recommendations.append("✅ 数据质量优秀，可直接使用")
            recommendations.append("📊 建议优先使用efinance和新浪财经的数据")
        elif status == 'good':
            recommendations.append("✅ 数据质量良好，建议多源对比")
            recommendations.append("🔍 可考虑增加更多数据源进行验证")
        elif status == 'acceptable':
            recommendations.append("⚠️ 数据存在差异，建议谨慎使用")
            recommendations.append("🔄 建议实时更新数据并重新验证")
        else:
            recommendations.append("❌ 数据质量较差，不建议直接使用")
            recommendations.append("🚨 建议检查网络连接和API可用性")
            recommendations.append("🔧 考虑使用备用数据源或缓存数据")
        
        # 根据具体情况添加建议
        price_analysis = validation_result.get('price_analysis', {})
        max_diff = price_analysis.get('max_difference', 0)
        
        if max_diff > 0.1:
            recommendations.append(f"💰 价格差异较大({max_diff:.2f}元)，建议核实数据准确性")
        
        sources_count = price_analysis.get('sources_count', 0)
        if sources_count >= 3:
            recommendations.append(f"📈 已获取{sources_count}个数据源，数据覆盖度良好")
        else:
            recommendations.append(f"📉 仅获取{sources_count}个数据源，建议增加数据源")
        
        return recommendations
    
    def get_large_orders_validation(self, code: str) -> Dict:
        """验证大单数据"""
        try:
            # 获取历史资金流向
            history_bill = ef.stock.get_history_bill(code)
            
            if history_bill is not None and not history_bill.empty:
                recent_data = history_bill.head(20)
                
                large_orders = []
                total_inflow = 0
                total_outflow = 0
                
                for _, row in recent_data.iterrows():
                    net_inflow = float(row.get('主力净流入', 0))
                    if abs(net_inflow) >= 500000:  # 50万以上为大单
                        large_orders.append({
                            'date': row['日期'],
                            'net_inflow': net_inflow,
                            'inflow_amount': float(row.get('主力流入', 0)),
                            'outflow_amount': float(row.get('主力流出', 0)),
                            'type': '流入' if net_inflow > 0 else '流出'
                        })
                        
                        if net_inflow > 0:
                            total_inflow += net_inflow
                        else:
                            total_outflow += abs(net_inflow)
                
                return {
                    'status': 'success',
                    'large_orders': large_orders,
                    'summary': {
                        'total_orders': len(large_orders),
                        'total_inflow': total_inflow,
                        'total_outflow': total_outflow,
                        'net_flow': total_inflow - total_outflow
                    },
                    'validation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                return {
                    'status': 'no_data',
                    'message': '暂无大单数据',
                    'large_orders': [],
                    'summary': {
                        'total_orders': 0,
                        'total_inflow': 0,
                        'total_outflow': 0,
                        'net_flow': 0
                    }
                }
                
        except Exception as e:
            logger.error(f"获取大单数据失败: {e}")
            return {
                'status': 'error',
                'message': f'获取大单数据失败: {str(e)}',
                'large_orders': [],
                'summary': {
                    'total_orders': 0,
                    'total_inflow': 0,
                    'total_outflow': 0,
                    'net_flow': 0
                }
            }
    
    def check_data_freshness(self, timestamp_str: str, max_delay_minutes: int = 5) -> bool:
        """检查数据新鲜度"""
        try:
            data_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            current_time = datetime.now()
            delay = (current_time - data_time).total_seconds() / 60
            
            return delay <= max_delay_minutes
        except Exception as e:
            logger.warning(f"检查数据新鲜度失败: {e}")
            return False

# 创建全局验证器实例
validator = StockDataValidator()

def validate_pingan_bank():
    """验证平安银行数据的快捷函数"""
    return validator.validate_pingan_bank_data()

def get_validated_stock_data(code: str) -> Dict:
    """获取经过验证的股票数据"""
    # 首先验证和标准化股票代码
    normalized_code = normalize_stock_code(code)
    if not normalized_code or not validate_stock_code(normalized_code):
        logger.error(f"股票代码无效: {code}")
        return None
    
    data_sources = {}
    
    # 尝试从多个数据源获取数据
    sina_data = validator.fetch_sina_data(normalized_code)
    if sina_data:
        data_sources['sina'] = sina_data
    
    tencent_data = validator.fetch_tencent_data(normalized_code)
    if tencent_data:
        data_sources['tencent'] = tencent_data
    
    efinance_data = validator.fetch_efinance_data(normalized_code)
    if efinance_data:
        data_sources['efinance'] = efinance_data
    
    # 选择最可靠的数据源
    if data_sources:
        # 优先使用efinance，其次新浪，最后腾讯
        preferred_sources = ['efinance', 'sina', 'tencent']
        for source in preferred_sources:
            if source in data_sources:
                return data_sources[source]
        
        # 如果都没有，返回第一个可用的
        return list(data_sources.values())[0]
    
    return None 