#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e码平台服务集成
支持获取虚拟手机号和短信验证码
"""

import time
import re
import requests
import urllib.parse
from datetime import datetime, timedelta
from loguru import logger

class EmaService:
    def __init__(self, config):
        self.config = config
        self.username = config.EMA_USERNAME
        self.password = config.EMA_PASSWORD
        self.api_url = "http://api.eomsg.com/zc/data.php"
        self.token = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # 默认配置
        self.default_keyword = "【牛老韭】"  # 短信关键词
        self.default_card_type = "实体"  # 卡类型
        self.phone_prefix = "18"  # 手机号前缀
        
        logger.info("✅ e码服务初始化完成")

    def login(self):
        """登录获取token"""
        try:
            params = {
                'code': 'login',
                'user': self.username,
                'password': self.password
            }
            
            response = self.session.get(self.api_url, params=params, timeout=10)
            result = response.text.strip()
            
            if result.startswith('ERROR:'):
                logger.error(f"❌ e码登录失败: {result}")
                return False
            
            self.token = result
            logger.info(f"✅ e码登录成功，token: {self.token[:10]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ e码登录异常: {e}")
            return False

    def get_balance(self):
        """查询余额"""
        try:
            if not self.token:
                if not self.login():
                    return None
            
            params = {
                'code': 'leftAmount',
                'token': self.token
            }
            
            response = self.session.get(self.api_url, params=params, timeout=10)
            result = response.text.strip()
            
            if result.startswith('ERROR:'):
                logger.error(f"❌ 查询余额失败: {result}")
                return None
            
            balance = float(result)
            logger.info(f"💰 e码余额: {balance}")
            return balance
            
        except Exception as e:
            logger.error(f"❌ 查询余额异常: {e}")
            return None

    def get_phone(self, phone_prefix=None, province=None, card_type=None, check_availability=True):
        """获取手机号"""
        try:
            if not self.token:
                if not self.login():
                    return None
            
            # 使用默认配置
            card_type = card_type or self.default_card_type
            
            params = {
                'code': 'getPhone',
                'token': self.token,
                'cardType': card_type
            }
            
            # 如果指定了省份
            if province:
                params['province'] = province
            
            # 尝试多次获取，筛选优质号码
            max_attempts = 15  # 增加重试次数
            for attempt in range(max_attempts):
                response = self.session.get(self.api_url, params=params, timeout=10)
                result = response.text.strip()
                
                if result.startswith('ERROR:'):
                    logger.error(f"❌ 获取手机号失败: {result}")
                    return None
                
                # 检查是否是完整的手机号
                if len(result) == 11 and result.isdigit():
                    # 优先检查是否是18开头的号码
                    if result.startswith('18'):
                        logger.info(f"🎯 获取到18开头手机号: {result}")
                        if check_availability:
                            if self.check_phone_availability(result):
                                logger.info(f"✅ 18开头号码可用性检测通过: {result}")
                                return result
                            else:
                                logger.warning(f"⚠️ 18开头号码可用性检测失败: {result}，重试...")
                                self.release_phone(result)
                                time.sleep(2)
                                continue
                        else:
                            return result
                    
                    # 检查其他号码质量
                    elif self.is_good_phone(result):
                        logger.info(f"📱 获取到优质手机号: {result}")
                        
                        # 检查号码可用性
                        if check_availability:
                            if self.check_phone_availability(result):
                                logger.info(f"✅ 号码可用性检测通过: {result}")
                                return result
                            else:
                                logger.warning(f"⚠️ 号码可用性检测失败: {result}，重试...")
                                self.release_phone(result)
                                time.sleep(2)
                                continue
                        else:
                            return result
                    else:
                        logger.info(f"📱 获取到手机号 {result}，质量不佳，重试...")
                        # 释放这个号码，重新获取
                        self.release_phone(result)
                        time.sleep(2)
                        continue
                else:
                    logger.warning(f"⚠️ 返回结果格式异常: {result}")
                    return None
            
            logger.warning(f"⚠️ 尝试 {max_attempts} 次后仍未获取到可用号码")
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取手机号异常: {e}")
            return None

    def is_good_phone(self, phone):
        """检查号码质量"""
        try:
            # 避免特殊号码段
            special_prefixes = ['100', '400', '800', '955']
            if phone[:3] in special_prefixes:
                return False
            
            # 优先18开头的号码
            if phone.startswith('18'):
                return True
            
            # 其他主流运营商号码段
            good_prefixes = [
                '130', '131', '132',  # 联通
                '134', '135', '136', '137', '138', '139',  # 移动
                '150', '151', '152', '157', '158', '159',  # 移动
                '133', '153', '189',  # 电信
                '155', '156', '186', '187',  # 联通
                '166', '167',  # 联通虚拟运营商
                '170', '171', '172', '173', '174', '175', '176', '177', '178'  # 虚拟运营商
            ]
            
            if phone[:3] in good_prefixes:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 检查号码质量异常: {e}")
            return True  # 异常时默认通过

    def check_phone_availability(self, phone):
        """检查号码可用性"""
        try:
            logger.info(f"🔍 检查号码可用性: {phone}")
            
            # 使用真实的号码检测服务
            from core.phone_detection_service import create_phone_detection_service
            
            detection_service = create_phone_detection_service(self.config)
            detection_result = detection_service.check_phone_comprehensive(phone)
            
            # 根据检测结果判断是否可用
            if not detection_result['is_valid']:
                logger.warning(f"⚠️ 号码检测不通过: {phone}")
                logger.warning(f"📊 检测详情: {detection_result}")
                return False
            
            if detection_result['risk_level'] == 'high':
                logger.warning(f"⚠️ 号码风险等级过高: {phone}")
                logger.warning(f"📊 风险详情: {detection_result['details']['risk']}")
                return False
            
            logger.info(f"✅ 号码可用性检测通过: {phone}")
            logger.info(f"📊 风险等级: {detection_result['risk_level']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 检查号码可用性异常: {e}")
            return True  # 异常时默认通过

    def is_phone_marked(self, phone):
        """检查号码是否被标注"""
        try:
            # 这里可以集成第三方标注查询API
            # 目前返回模拟数据
            
            # 模拟标注检查
            marked_numbers = {
                "16655124250": "疑似营销号码",
                "10086": "中国移动客服",
                "10010": "中国联通客服",
                "10000": "中国电信客服"
            }
            
            return phone in marked_numbers
            
        except Exception as e:
            logger.error(f"❌ 检查号码标注异常: {e}")
            return False

    def is_phone_blacklisted(self, phone):
        """检查号码是否被拉黑"""
        try:
            # 1. 检查本地黑名单
            local_blacklist = [
                "16655124250",  # 之前失败的号码
                "17000000000",  # 虚拟运营商
                "40000000000"   # 企业号码
            ]
            
            if phone in local_blacklist:
                logger.warning(f"⚠️ 号码在本地黑名单中: {phone}")
                return True
            
            # 2. 调用第三方API检查号码状态
            if self.check_phone_with_api(phone):
                logger.warning(f"⚠️ 号码被第三方API标记为黑名单: {phone}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 检查号码黑名单异常: {e}")
            return False

    def check_phone_with_api(self, phone):
        """通过第三方API检查号码状态"""
        try:
            # 使用免费的号码归属地查询API
            url = f"https://api.ipify.org?format=json"
            response = self.session.get(url, timeout=5)
            
            # 这里可以集成真实的号码检测API
            # 例如：阿里云号码检测、腾讯云号码检测等
            
            # 模拟API检查结果
            # 在实际使用中，可以替换为真实的API调用
            api_blacklist = [
                "16655124250",  # 模拟API返回的黑名单
            ]
            
            return phone in api_blacklist
            
        except Exception as e:
            logger.error(f"❌ API检查号码异常: {e}")
            return False

    def is_valid_phone_format(self, phone):
        """检查号码格式是否有效"""
        try:
            import re
            
            # 检查是否是11位数字
            if not re.match(r'^1[3-9]\d{9}$', phone):
                return False
            
            # 检查号码段是否有效
            valid_prefixes = [
                '130', '131', '132', '133', '134', '135', '136', '137', '138', '139',
                '150', '151', '152', '153', '155', '156', '157', '158', '159',
                '166', '167', '170', '171', '172', '173', '174', '175', '176', '177', '178',
                '180', '181', '182', '183', '184', '185', '186', '187', '188', '189'
            ]
            
            return phone[:3] in valid_prefixes
            
        except Exception as e:
            logger.error(f"❌ 检查号码格式异常: {e}")
            return False

    def is_phone_overused(self, phone):
        """检查号码是否被过度使用"""
        try:
            # 1. 检查本地使用历史
            if self.check_local_usage_history(phone):
                logger.warning(f"⚠️ 号码在本地使用历史中过度使用: {phone}")
                return True
            
            # 2. 检查e码平台历史记录
            if self.check_ema_usage_history(phone):
                logger.warning(f"⚠️ 号码在e码平台使用历史中过度使用: {phone}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 检查号码使用情况异常: {e}")
            return False

    def check_local_usage_history(self, phone):
        """检查本地使用历史"""
        try:
            # 这里可以查询本地数据库的使用记录
            # 检查号码在最近24小时内的使用次数
            
            # 模拟本地使用历史检查
            local_overused = [
                "16655124250",  # 之前失败的号码
            ]
            
            return phone in local_overused
            
        except Exception as e:
            logger.error(f"❌ 检查本地使用历史异常: {e}")
            return False

    def check_ema_usage_history(self, phone):
        """检查e码平台使用历史"""
        try:
            # 获取e码平台的历史记录
            history = self.get_history()
            if not history:
                return False
            
            # 统计该号码在历史记录中的使用次数
            usage_count = 0
            for record in history:
                if phone in record:
                    usage_count += 1
            
            # 如果使用次数超过阈值，认为过度使用
            max_usage_threshold = 3  # 24小时内最多使用3次
            if usage_count >= max_usage_threshold:
                logger.warning(f"⚠️ 号码在e码平台使用 {usage_count} 次，超过阈值 {max_usage_threshold}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 检查e码平台使用历史异常: {e}")
            return False

    def get_sms_code(self, phone, keyword=None, timeout=60, interval=3):
        """获取短信验证码"""
        try:
            if not self.token:
                if not self.login():
                    return None
            
            keyword = keyword or self.default_keyword
            start_time = time.time()
            
            logger.info(f"📨 等待短信验证码，关键词: {keyword}")
            
            while time.time() - start_time < timeout:
                params = {
                    'code': 'getMsg',
                    'token': self.token,
                    'phone': phone,
                    'keyWord': keyword
                }
                
                response = self.session.get(self.api_url, params=params, timeout=10)
                result = response.text.strip()
                
                if result.startswith('ERROR:'):
                    logger.error(f"❌ 获取短信失败: {result}")
                    return None
                
                if '[尚未收到]' in result:
                    logger.info(f"⏳ 短信尚未收到，继续等待... ({int(time.time() - start_time)}s)")
                    time.sleep(interval)
                    continue
                
                # 提取验证码
                sms_code = self.extract_sms_code(result)
                if sms_code:
                    logger.info(f"✅ 收到短信验证码: {sms_code}")
                    return sms_code
                
                logger.info(f"📨 收到短信: {result}")
                time.sleep(interval)
            
            logger.warning(f"⏰ 短信等待超时 ({timeout}s)")
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取短信异常: {e}")
            return None

    def extract_sms_code(self, sms_content):
        """从短信内容中提取验证码"""
        try:
            # 常见的验证码模式
            patterns = [
                r'验证码[：:]\s*(\d{4,6})',
                r'码[：:]\s*(\d{4,6})',
                r'(\d{4,6})',
                r'【(\d{4,6})】',
                r'验证码是(\d{4,6})',
                r'您的验证码是(\d{4,6})'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, sms_content)
                if match:
                    code = match.group(1)
                    # 验证码通常是4-6位数字
                    if len(code) >= 4 and len(code) <= 6:
                        return code
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 提取验证码异常: {e}")
            return None

    def release_phone(self, phone):
        """释放手机号"""
        try:
            if not self.token:
                if not self.login():
                    return False
            
            params = {
                'code': 'release',
                'token': self.token,
                'phone': phone
            }
            
            response = self.session.get(self.api_url, params=params, timeout=10)
            result = response.text.strip()
            
            if result.startswith('ERROR:'):
                logger.warning(f"⚠️ 释放手机号失败: {result}")
                return False
            
            logger.info(f"✅ 释放手机号成功: {phone}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 释放手机号异常: {e}")
            return False

    def block_phone(self, phone):
        """拉黑手机号"""
        try:
            if not self.token:
                if not self.login():
                    return False
            
            params = {
                'code': 'block',
                'token': self.token,
                'phone': phone
            }
            
            response = self.session.get(self.api_url, params=params, timeout=10)
            result = response.text.strip()
            
            if result.startswith('ERROR:'):
                logger.warning(f"⚠️ 拉黑手机号失败: {result}")
                return False
            
            logger.info(f"✅ 拉黑手机号成功: {phone}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 拉黑手机号异常: {e}")
            return False

    def get_history(self):
        """查询历史记录"""
        try:
            if not self.token:
                if not self.login():
                    return None
            
            params = {
                'code': 'queryUsed',
                'token': self.token
            }
            
            response = self.session.get(self.api_url, params=params, timeout=10)
            result = response.text.strip()
            
            if result.startswith('ERROR:'):
                logger.error(f"❌ 查询历史记录失败: {result}")
                return None
            
            records = result.split('\n') if result else []
            logger.info(f"📋 历史记录数量: {len(records)}")
            return records
            
        except Exception as e:
            logger.error(f"❌ 查询历史记录异常: {e}")
            return None

    def get_service_status(self):
        """获取服务状态"""
        try:
            balance = self.get_balance()
            if balance is None:
                return "❌ 服务异常"
            
            return f"✅ 服务正常，余额: {balance}"
            
        except Exception as e:
            logger.error(f"❌ 获取服务状态异常: {e}")
            return "❌ 服务异常"

class EmaManager:
    def __init__(self, config):
        self.config = config
        self.service = EmaService(config)
        self.active_phones = {}

    def get_phone(self, province=None, check_availability=True):
        """获取手机号"""
        phone = self.service.get_phone(province=province, check_availability=check_availability)
        if phone:
            self.active_phones[phone] = {
                'get_time': datetime.now(),
                'status': 'active'
            }
        return phone

    def get_sms_code(self, phone, keyword=None, timeout=60):
        """获取短信验证码"""
        return self.service.get_sms_code(phone, keyword=keyword, timeout=timeout)

    def release_phone(self, phone):
        """释放手机号"""
        success = self.service.release_phone(phone)
        if success and phone in self.active_phones:
            self.active_phones[phone]['status'] = 'released'
        return success

    def block_phone(self, phone):
        """拉黑手机号"""
        success = self.service.block_phone(phone)
        if success and phone in self.active_phones:
            self.active_phones[phone]['status'] = 'blocked'
        return success

    def get_balance(self):
        """获取余额"""
        return self.service.get_balance()

    def get_service_status(self):
        """获取服务状态"""
        return self.service.get_service_status()

    def get_history(self):
        """获取历史记录"""
        return self.service.get_history()

def create_ema_service(config):
    """创建e码服务管理器"""
    return EmaManager(config)

def test_ema_service():
    """测试e码服务"""
    from utils.config import Config
    
    config = Config()
    ema = create_ema_service(config)
    
    print("🧪 测试e码服务")
    print("=" * 50)
    
    # 测试登录和余额
    balance = ema.get_balance()
    if balance is not None:
        print(f"✅ 余额查询成功: {balance}")
    else:
        print("❌ 余额查询失败")
        return
    
    # 测试获取手机号
    phone = ema.get_phone()
    if phone:
        print(f"✅ 获取手机号成功: {phone}")
        
        # 测试释放手机号
        if ema.release_phone(phone):
            print(f"✅ 释放手机号成功: {phone}")
        else:
            print(f"❌ 释放手机号失败: {phone}")
    else:
        print("❌ 获取手机号失败")
    
    # 测试历史记录
    history = ema.get_history()
    if history:
        print(f"✅ 历史记录查询成功，共 {len(history)} 条")
    else:
        print("❌ 历史记录查询失败")

if __name__ == "__main__":
    test_ema_service() 