#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证码识别器
"""

import base64
import io
import time
import random
from loguru import logger

# 移除不兼容的依赖
DDDDOCR_AVAILABLE = False
TESSERACT_AVAILABLE = False

class CaptchaSolver:
    """验证码识别器"""
    
    def __init__(self, config):
        self.config = config
        self.ocr = None
        self.init_ocr()
    
    def init_ocr(self):
        """初始化OCR引擎"""
        try:
            logger.info("⚠️ 使用模拟验证码识别器")
            logger.warning("OCR引擎未启用，将使用模拟验证码")
                
        except Exception as e:
            logger.error(f"❌ OCR初始化失败: {e}")
    
    def solve_image_captcha(self, image_data, captcha_type="general"):
        """识别图片验证码"""
        try:
            # 模拟验证码识别
            logger.info("🖼️ 模拟验证码识别")
            
            # 生成随机验证码
            captcha_code = ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
            logger.info(f"✅ 模拟验证码识别成功: {captcha_code}")
            return captcha_code
            
        except Exception as e:
            logger.error(f"验证码识别失败: {e}")
            return None
    
    def preprocess_image(self, image_data):
        """预处理图片"""
        try:
            # 简化处理，直接返回原数据
            return image_data
            
        except Exception as e:
            logger.error(f"图片预处理失败: {e}")
            return image_data
    
    def manual_solve_captcha(self, image_data):
        """手动识别验证码（模拟）"""
        # 这里可以集成人工打码服务
        # 暂时返回随机字符串
        return ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
    
    def solve_sms_captcha(self, phone, target_site):
        """处理短信验证码"""
        try:
            # 等待短信到达
            logger.info(f"等待短信验证码到达: {phone}")
            time.sleep(self.config.SMS_WAIT_TIME)
            
            # 这里应该集成短信平台API来获取验证码
            # 暂时返回模拟验证码
            sms_code = self.get_sms_from_platform(phone, target_site)
            
            if sms_code:
                logger.info(f"✅ 获取短信验证码成功: {sms_code}")
                return sms_code
            else:
                logger.warning("❌ 获取短信验证码失败")
                return None
                
        except Exception as e:
            logger.error(f"处理短信验证码失败: {e}")
            return None
    
    def get_sms_from_platform(self, phone, target_site):
        """从短信平台获取验证码"""
        try:
            # 这里应该调用真实的短信平台API
            # 暂时返回模拟验证码
            return str(random.randint(100000, 999999))
            
        except Exception as e:
            logger.error(f"从短信平台获取验证码失败: {e}")
            return None
    
    def validate_captcha_format(self, captcha_code):
        """验证验证码格式"""
        if not captcha_code:
            return False
        
        # 检查长度
        if len(captcha_code) < 4 or len(captcha_code) > 6:
            return False
        
        # 检查字符类型
        valid_chars = set('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
        if not all(c in valid_chars for c in captcha_code):
            return False
        
        return True
    
    def get_captcha_image_from_url(self, session, url):
        """从URL获取验证码图片"""
        try:
            response = session.get(url, timeout=self.config.REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"获取验证码图片失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"获取验证码图片失败: {e}")
            return None
    
    def refresh_captcha(self, session, refresh_url):
        """刷新验证码"""
        try:
            response = session.get(refresh_url, timeout=self.config.REQUEST_TIMEOUT)
            if response.status_code == 200:
                logger.info("✅ 验证码刷新成功")
                return True
            else:
                logger.error(f"验证码刷新失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"验证码刷新失败: {e}")
            return False
    
    def solve_captcha_with_retry(self, image_data, max_attempts=3):
        """带重试的验证码识别"""
        for attempt in range(max_attempts):
            try:
                result = self.solve_image_captcha(image_data)
                if result and self.validate_captcha_format(result):
                    return result
                
                logger.warning(f"验证码识别失败，尝试第 {attempt + 1} 次")
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"验证码识别异常: {e}")
                time.sleep(1)
        
        logger.error(f"验证码识别失败，已尝试 {max_attempts} 次")
        return None 