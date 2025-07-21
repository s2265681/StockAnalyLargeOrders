#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API测试脚本
"""

import requests
import json
import time
from loguru import logger

class CrawlerAPITester:
    """爬虫API测试器"""
    
    def __init__(self, base_url="http://localhost:9003"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def test_health(self):
        """测试健康检查"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ 健康检查成功: {data}")
                return True
            else:
                logger.error(f"❌ 健康检查失败: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ 健康检查异常: {e}")
            return False
    
    def test_phone_pool_status(self):
        """测试号码池状态"""
        try:
            response = self.session.get(f"{self.base_url}/api/phone-pool")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ 号码池状态: {data}")
                return data.get('data')
            else:
                logger.error(f"❌ 获取号码池状态失败: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取号码池状态异常: {e}")
            return None
    
    def test_add_phone(self, phone="13800138000"):
        """测试添加号码"""
        try:
            data = {
                "phone": phone,
                "source": "test"
            }
            response = self.session.post(
                f"{self.base_url}/api/phone-pool",
                json=data
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ 添加号码成功: {result}")
                return True
            else:
                logger.error(f"❌ 添加号码失败: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ 添加号码异常: {e}")
            return False
    
    def test_register_account(self, count=1):
        """测试注册账户"""
        try:
            data = {
                "count": count
            }
            response = self.session.post(
                f"{self.base_url}/api/register",
                json=data
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ 注册账户成功: {result}")
                return result.get('data')
            else:
                logger.error(f"❌ 注册账户失败: {response.status_code}")
                logger.error(f"响应内容: {response.text}")
                return None
        except Exception as e:
            logger.error(f"❌ 注册账户异常: {e}")
            return None
    
    def test_login_account(self, username, password):
        """测试登录账户"""
        try:
            data = {
                "username": username,
                "password": password
            }
            response = self.session.post(
                f"{self.base_url}/api/login",
                json=data
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ 登录账户成功: {result}")
                return result.get('data')
            else:
                logger.error(f"❌ 登录账户失败: {response.status_code}")
                logger.error(f"响应内容: {response.text}")
                return None
        except Exception as e:
            logger.error(f"❌ 登录账户异常: {e}")
            return None
    
    def test_get_stock_data(self, user_info, stock_code="000001"):
        """测试获取股票数据"""
        try:
            data = {
                "user_info": user_info,
                "stock_code": stock_code
            }
            response = self.session.post(
                f"{self.base_url}/api/data",
                json=data
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ 获取股票数据成功: {result}")
                return result.get('data')
            else:
                logger.error(f"❌ 获取股票数据失败: {response.status_code}")
                logger.error(f"响应内容: {response.text}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取股票数据异常: {e}")
            return None
    
    def test_system_status(self):
        """测试系统状态"""
        try:
            response = self.session.get(f"{self.base_url}/api/status")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ 系统状态: {data}")
                return data.get('data')
            else:
                logger.error(f"❌ 获取系统状态失败: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取系统状态异常: {e}")
            return None
    
    def test_sessions(self):
        """测试会话管理"""
        try:
            response = self.session.get(f"{self.base_url}/api/sessions")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ 会话列表: {data}")
                return data.get('data')
            else:
                logger.error(f"❌ 获取会话列表失败: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取会话列表异常: {e}")
            return None
    
    def run_full_test(self):
        """运行完整测试"""
        logger.info("🚀 开始运行完整API测试")
        
        # 1. 健康检查
        logger.info("📋 1. 测试健康检查")
        if not self.test_health():
            logger.error("❌ 健康检查失败，停止测试")
            return False
        
        # 2. 系统状态
        logger.info("📋 2. 测试系统状态")
        self.test_system_status()
        
        # 3. 号码池状态
        logger.info("📋 3. 测试号码池状态")
        self.test_phone_pool_status()
        
        # 4. 添加测试号码
        logger.info("📋 4. 测试添加号码")
        self.test_add_phone()
        
        # 5. 注册账户
        logger.info("📋 5. 测试注册账户")
        register_result = self.test_register_account(1)
        
        if register_result:
            # 6. 登录账户
            logger.info("📋 6. 测试登录账户")
            if isinstance(register_result, list) and len(register_result) > 0:
                user_data = register_result[0]
                username = user_data.get('username')
                password = user_data.get('password')
                
                if username and password:
                    login_result = self.test_login_account(username, password)
                    
                    if login_result:
                        # 7. 获取股票数据
                        logger.info("📋 7. 测试获取股票数据")
                        self.test_get_stock_data(login_result)
        
        # 8. 会话管理
        logger.info("📋 8. 测试会话管理")
        self.test_sessions()
        
        logger.info("🎉 完整API测试完成")
        return True

def main():
    """主函数"""
    # 配置日志
    logger.add("test_api.log", rotation="1 day", level="INFO")
    
    # 创建测试器
    tester = CrawlerAPITester()
    
    # 运行测试
    success = tester.run_full_test()
    
    if success:
        logger.info("✅ 所有测试通过")
    else:
        logger.error("❌ 测试失败")
    
    return success

if __name__ == "__main__":
    main() 