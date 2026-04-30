#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置文件
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Config:
    """配置类"""
    
    def __init__(self):
        # 目标网站配置
        self.TARGET_SITE = "https://niulaojiu.cn"
        self.REGISTER_URL = f"{self.TARGET_SITE}/register/"
        self.LOGIN_URL = f"{self.TARGET_SITE}/login/"
        self.API_BASE_URL = f"{self.TARGET_SITE}/api/v1"
        
        # AJAX接口配置
        self.AJAX_URL = f"{self.TARGET_SITE}/wp-admin/admin-ajax.php"
        
        # 请求配置
        self.REQUEST_TIMEOUT = 60  # 增加超时时间到60秒
        self.MAX_RETRIES = 5       # 增加重试次数
        self.RETRY_DELAY = 3       # 增加重试延迟
        
        # 频率限制
        self.REQUEST_INTERVAL = (2, 8)  # 随机间隔范围(秒)
        self.MAX_REQUESTS_PER_MINUTE = 10
        self.MAX_REQUESTS_PER_HOUR = 100
        
        # 验证码配置
        self.CAPTCHA_TIMEOUT = 60  # 验证码超时时间(秒)
        self.SMS_WAIT_TIME = 30   # 短信等待时间(秒)
        
        # 号码池配置
        self.PHONE_POOL_SIZE = 50
        self.PHONE_COOLDOWN_TIME = 3600  # 号码冷却时间(秒)
        self.PHONE_MAX_USAGE = 10  # 单个号码最大使用次数
        
        # 数据库配置
        self.DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///crawler.db')
        self.REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        
        # 代理配置
        self.USE_PROXY = os.getenv('USE_PROXY', 'false').lower() == 'true'
        self.PROXY_LIST = os.getenv('PROXY_LIST', '').split(',') if os.getenv('PROXY_LIST') else []
        
        # 日志配置
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.LOG_FILE = 'logs/crawler.log'
        
        # 会话配置
        self.SESSION_TIMEOUT = 3600  # 会话超时时间(秒)
        self.MAX_SESSIONS = 100
        
        # 用户代理池
        self.USER_AGENTS = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0'
        ]
        
        # 默认用户信息
        self.DEFAULT_USER_INFO = {
            'username_prefix': 'user',
            'email_domain': 'example.com',
            'password_length': 8,
            'password_chars': 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        }
        
        # 验证码识别配置
        self.CAPTCHA_SOLVERS = {
            'ddddocr': True,
            'tesseract': True,
            'manual': False,
            'chaojiying': True  # 启用超级鹰
        }
        
        # 超级鹰配置
        self.CHAOJIYING_USERNAME = os.getenv('CHAOJIYING_USERNAME', '')
        self.CHAOJIYING_PASSWORD = os.getenv('CHAOJIYING_PASSWORD', '')
        self.CHAOJIYING_SOFT_ID = os.getenv('CHAOJIYING_SOFT_ID', '')
        
        # 短信服务配置
        self.SMS_SERVICE = os.getenv('SMS_SERVICE', 'mock')  # jiema, ema, mock
        self.YUNPIAN_API_KEY = os.getenv('YUNPIAN_API_KEY', '')
        self.YUNPIAN_SECRET = os.getenv('YUNPIAN_SECRET', '')
        self.ALIYUN_ACCESS_KEY = os.getenv('ALIYUN_ACCESS_KEY', '')
        self.ALIYUN_SECRET_KEY = os.getenv('ALIYUN_SECRET_KEY', '')
        self.TENCENT_SECRET_ID = os.getenv('TENCENT_SECRET_ID', '')
        self.TENCENT_SECRET_KEY = os.getenv('TENCENT_SECRET_KEY', '')
        
        # e码平台配置
        self.EMA_USERNAME = os.getenv('EMA_USERNAME', '')
        self.EMA_PASSWORD = os.getenv('EMA_PASSWORD', '')
        

        
        # 异常处理配置
        self.MAX_FAILURES = 5
        self.BLACKLIST_DURATION = 86400  # 黑名单持续时间(秒)
        
        # 数据存储配置
        self.DATA_BACKUP_INTERVAL = 3600  # 数据备份间隔(秒)
        self.MAX_DATA_RETENTION = 30  # 数据保留天数 