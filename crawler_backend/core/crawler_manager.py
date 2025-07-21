#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬虫管理器
实现注册、登录和数据获取功能
"""

import time
import random
import string
import re
import json
from datetime import datetime
from loguru import logger
import threading
from urllib.parse import urlencode

class CrawlerManager:
    """爬虫管理器"""
    
    def __init__(self, config, phone_pool, session_manager, db_manager):
        self.config = config
        self.phone_pool = phone_pool
        self.session_manager = session_manager
        self.db_manager = db_manager
        self.captcha_solver = None
        self.lock = threading.Lock()
        
        # 导入验证码识别器
        try:
            from core.captcha_solver import CaptchaSolver
            self.captcha_solver = CaptchaSolver(config)
        except Exception as e:
            logger.error(f"初始化验证码识别器失败: {e}")
    
    def register_account(self, user_info=None):
        """注册账户"""
        try:
            # 获取可用号码
            phone_data = self.phone_pool.get_phone()
            if not phone_data:
                logger.error("❌ 无法获取可用号码")
                return None
            
            phone = phone_data['phone']
            logger.info(f"🎯 开始注册账户，使用号码: {phone}")
            
            # 创建会话
            session_id = self.session_manager.create_session()
            if not session_id:
                logger.error("❌ 创建会话失败")
                self.phone_pool.release_phone(phone)
                return None
            
            session = self.session_manager.get_session(session_id)
            if not session:
                logger.error("❌ 获取会话失败")
                self.phone_pool.release_phone(phone)
                return None
            
            try:
                # 生成用户信息
                if not user_info:
                    user_info = self.generate_user_info()
                
                # 1. 访问注册页面获取初始cookies
                logger.info("📄 访问注册页面...")
                response = session.get(self.config.REGISTER_URL, timeout=self.config.REQUEST_TIMEOUT)
                if response.status_code != 200:
                    logger.error(f"❌ 访问注册页面失败: {response.status_code}")
                    return None
                
                # 2. 获取图形验证码
                logger.info("🖼️ 获取图形验证码...")
                captcha_code = self.get_image_captcha(session)
                if not captcha_code:
                    logger.error("❌ 获取图形验证码失败")
                    return None
                
                # 3. 发送短信验证码
                logger.info("📱 发送短信验证码...")
                sms_sent = self.send_sms_code(session, phone, user_info, captcha_code)
                if not sms_sent:
                    logger.error("❌ 发送短信验证码失败")
                    return None
                
                # 4. 获取短信验证码
                logger.info("📨 获取短信验证码...")
                sms_code = self.get_sms_code(phone)
                if not sms_code:
                    logger.error("❌ 获取短信验证码失败")
                    return None
                
                # 5. 提交注册
                logger.info("📝 提交注册...")
                register_result = self.submit_registration(session, phone, user_info, captcha_code, sms_code)
                if not register_result:
                    logger.error("❌ 注册失败")
                    return None
                
                # 6. 保存用户信息到数据库
                user_id = self.db_manager.add_user(
                    username=user_info['username'],
                    email=user_info['email'],
                    phone=phone,
                    password=user_info['password']
                )
                
                if user_id:
                    logger.info(f"✅ 注册成功，用户ID: {user_id}")
                    
                    # 更新会话用户ID
                    with self.lock:
                        if session_id in self.session_manager.sessions:
                            self.session_manager.sessions[session_id]['user_id'] = user_id
                    
                    return {
                        'user_id': user_id,
                        'username': user_info['username'],
                        'email': user_info['email'],
                        'phone': phone,
                        'password': user_info['password'],
                        'session_id': session_id,
                        'status': 'registered'
                    }
                else:
                    logger.error("❌ 保存用户信息失败")
                    return None
                
            except Exception as e:
                logger.error(f"注册过程异常: {e}")
                return None
            finally:
                # 释放号码
                self.phone_pool.release_phone(phone)
                
        except Exception as e:
            logger.error(f"注册账户失败: {e}")
            return None
    
    def login_account(self, username, password, session_id=None):
        """登录账户"""
        try:
            logger.info(f"🎯 开始登录账户: {username}")
            
            # 创建或获取会话
            if not session_id:
                session_id = self.session_manager.create_session()
            
            session = self.session_manager.get_session(session_id)
            if not session:
                logger.error("❌ 获取会话失败")
                return None
            
            try:
                # 1. 访问登录页面
                logger.info("📄 访问登录页面...")
                response = session.get(self.config.LOGIN_URL, timeout=self.config.REQUEST_TIMEOUT)
                if response.status_code != 200:
                    logger.error(f"❌ 访问登录页面失败: {response.status_code}")
                    return None
                
                # 2. 获取图形验证码
                logger.info("🖼️ 获取图形验证码...")
                captcha_code = self.get_image_captcha(session)
                if not captcha_code:
                    logger.error("❌ 获取图形验证码失败")
                    return None
                
                # 3. 提交登录
                logger.info("🔐 提交登录...")
                login_result = self.submit_login(session, username, password, captcha_code)
                if not login_result:
                    logger.error("❌ 登录失败")
                    return None
                
                # 4. 获取用户信息
                user_data = self.db_manager.get_user_by_phone(username)  # 假设用户名是手机号
                if not user_data:
                    logger.error("❌ 获取用户信息失败")
                    return None
                
                # 5. 更新用户token
                if 'token' in login_result and 'finger_print' in login_result:
                    self.db_manager.update_user_token(
                        user_data['id'], 
                        login_result['token'], 
                        login_result['finger_print']
                    )
                
                logger.info(f"✅ 登录成功，用户ID: {user_data['id']}")
                
                return {
                    'user_id': user_data['id'],
                    'username': user_data['username'],
                    'phone': user_data['phone'],
                    'token': login_result.get('token'),
                    'finger_print': login_result.get('finger_print'),
                    'session_id': session_id,
                    'status': 'logged_in'
                }
                
            except Exception as e:
                logger.error(f"登录过程异常: {e}")
                return None
                
        except Exception as e:
            logger.error(f"登录账户失败: {e}")
            return None
    
    def get_stock_data(self, user_info, stock_code="000001"):
        """获取股票数据"""
        try:
            logger.info(f"📊 获取股票数据: {stock_code}")
            
            session_id = user_info.get('session_id')
            if not session_id:
                logger.error("❌ 缺少会话ID")
                return None
            
            session = self.session_manager.get_session(session_id)
            if not session:
                logger.error("❌ 获取会话失败")
                return None
            
            # 构建API请求URL
            token = user_info.get('token')
            finger_print = user_info.get('finger_print')
            
            if not token or not finger_print:
                logger.error("❌ 缺少token或finger_print")
                return None
            
            # 测试登录成功的接口
            api_url = f"{self.config.API_BASE_URL}/recent_5_trade_days"
            params = {
                'dt': '',
                'token': token,
                'finger_print': finger_print
            }
            
            url = f"{api_url}?{urlencode(params)}"
            
            logger.info(f"🌐 请求API: {url}")
            
            response = session.get(url, timeout=self.config.REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.info(f"✅ 获取股票数据成功")
                    return data
                except json.JSONDecodeError:
                    logger.error("❌ 解析JSON失败")
                    return None
            else:
                logger.error(f"❌ API请求失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"获取股票数据失败: {e}")
            return None
    
    def generate_user_info(self):
        """生成用户信息"""
        try:
            # 生成用户名
            username = f"{self.config.DEFAULT_USER_INFO['username_prefix']}{random.randint(1000, 9999)}"
            
            # 生成邮箱
            email = f"{username}@{self.config.DEFAULT_USER_INFO['email_domain']}"
            
            # 生成密码
            password = ''.join(random.choices(
                self.config.DEFAULT_USER_INFO['password_chars'], 
                k=self.config.DEFAULT_USER_INFO['password_length']
            ))
            
            return {
                'username': username,
                'email': email,
                'password': password
            }
            
        except Exception as e:
            logger.error(f"生成用户信息失败: {e}")
            return None
    
    def get_image_captcha(self, session):
        """获取图形验证码"""
        try:
            # 刷新验证码接口
            refresh_url = f"{self.config.AJAX_URL}?action=xh_social_add_ons_login&tab=register&xh_social_add_ons_login=b26a2f323b&notice_str=0563112987&hash=b62c106b0e3d428a8d70119480be4fe6"
            
            # 这里需要从页面中提取验证码图片URL
            # 暂时使用模拟验证码
            if self.captcha_solver:
                # 实际应该从页面获取验证码图片
                captcha_code = self.captcha_solver.solve_image_captcha(None)
                if captcha_code:
                    return captcha_code
            
            # 备用方案：生成随机验证码
            return ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
            
        except Exception as e:
            logger.error(f"获取图形验证码失败: {e}")
            return None
    
    def send_sms_code(self, session, phone, user_info, captcha_code):
        """发送短信验证码"""
        try:
            # 发送验证码接口
            url = self.config.AJAX_URL
            
            data = {
                'action': 'xh_social_wechat_social_add_ons_social_mobile',
                'tab': 'mobile_login_vcode',
                'xh_social_wechat_social_add_ons_social_mobile': 'fde9f1b914',
                'notice_str': '1926813750',
                'unique': '1',
                'hash': '2a3fb4b058f9bff14be3957e18956a47',
                'register_user_login': user_info['username'],
                'register_user_email': user_info['email'],
                'mobile': phone,
                'captcha': captcha_code,
                'mobile_vcode': '',
                'register_password': user_info['password']
            }
            
            response = session.post(url, data=data, timeout=self.config.REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('status') == 'success':
                        logger.info("✅ 短信验证码发送成功")
                        return True
                    else:
                        logger.error(f"❌ 短信验证码发送失败: {result}")
                        return False
                except json.JSONDecodeError:
                    logger.error("❌ 解析短信发送响应失败")
                    return False
            else:
                logger.error(f"❌ 短信验证码发送请求失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"发送短信验证码失败: {e}")
            return False
    
    def get_sms_code(self, phone):
        """获取短信验证码"""
        try:
            if self.captcha_solver:
                return self.captcha_solver.solve_sms_captcha(phone, self.config.TARGET_SITE)
            
            # 备用方案：返回模拟验证码
            return str(random.randint(100000, 999999))
            
        except Exception as e:
            logger.error(f"获取短信验证码失败: {e}")
            return None
    
    def submit_registration(self, session, phone, user_info, captcha_code, sms_code):
        """提交注册"""
        try:
            url = f"{self.config.AJAX_URL}?action=xh_social_add_ons_login&tab=register&xh_social_add_ons_login=b26a2f323b&notice_str=0563112987&hash=b62c106b0e3d428a8d70119480be4fe6"
            
            data = {
                'register_user_login': user_info['username'],
                'register_user_email': user_info['email'],
                'mobile': phone,
                'captcha': captcha_code,
                'mobile_vcode': sms_code,
                'register_password': user_info['password']
            }
            
            response = session.post(url, data=data, timeout=self.config.REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('status') == 'success':
                        logger.info("✅ 注册提交成功")
                        return True
                    else:
                        logger.error(f"❌ 注册提交失败: {result}")
                        return False
                except json.JSONDecodeError:
                    logger.error("❌ 解析注册响应失败")
                    return False
            else:
                logger.error(f"❌ 注册提交请求失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"提交注册失败: {e}")
            return False
    
    def submit_login(self, session, username, password, captcha_code):
        """提交登录"""
        try:
            url = f"{self.config.AJAX_URL}?action=xh_social_add_ons_login&tab=login&xh_social_add_ons_login=b26a2f323b&notice_str=5617079903&hash=12d23292bbec6aeb0324957c26fe1664"
            
            data = {
                'login_name': username,
                'login_password': password,
                'captcha': captcha_code
            }
            
            response = session.post(url, data=data, timeout=self.config.REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('status') == 'success':
                        logger.info("✅ 登录提交成功")
                        
                        # 提取token和finger_print（需要从响应中解析）
                        # 这里需要根据实际响应格式调整
                        return {
                            'status': 'success',
                            'token': result.get('token'),
                            'finger_print': result.get('finger_print')
                        }
                    else:
                        logger.error(f"❌ 登录提交失败: {result}")
                        return None
                except json.JSONDecodeError:
                    logger.error("❌ 解析登录响应失败")
                    return None
            else:
                logger.error(f"❌ 登录提交请求失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"提交登录失败: {e}")
            return None
    
    def batch_register(self, count=5):
        """批量注册"""
        try:
            results = []
            for i in range(count):
                logger.info(f"🔄 开始第 {i+1}/{count} 个账户注册")
                
                result = self.register_account()
                if result:
                    results.append(result)
                    logger.info(f"✅ 第 {i+1} 个账户注册成功")
                else:
                    logger.error(f"❌ 第 {i+1} 个账户注册失败")
                
                # 随机延迟
                delay = random.uniform(*self.config.REQUEST_INTERVAL)
                logger.info(f"⏳ 等待 {delay:.1f} 秒...")
                time.sleep(delay)
            
            logger.info(f"🎉 批量注册完成，成功 {len(results)}/{count} 个账户")
            return results
            
        except Exception as e:
            logger.error(f"批量注册失败: {e}")
            return []
    
    def get_system_status(self):
        """获取系统状态"""
        try:
            return {
                'phone_pool': self.phone_pool.get_pool_status(),
                'sessions': {
                    'count': self.session_manager.get_session_count(),
                    'active': len([s for s in self.session_manager.get_all_sessions() if s and s['is_active']])
                },
                'captcha_solver': self.captcha_solver is not None,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return None 