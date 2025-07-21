#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬虫号码池注册后端主应用
提供自动注册、登录、数据获取的API接口
"""

import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
from loguru import logger
import threading
import time

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.crawler_manager import CrawlerManager
from core.phone_pool import PhonePoolManager
from core.captcha_solver import CaptchaSolver
from core.session_manager import SessionManager
from utils.config import Config
from utils.database import DatabaseManager
from api.routes import register_routes

# 创建Flask应用
app = Flask(__name__)
CORS(app)

# 配置日志
logger.add("logs/crawler.log", rotation="1 day", retention="7 days", level="INFO")

# 全局管理器实例
crawler_manager = None
phone_pool_manager = None
session_manager = None
db_manager = None

def initialize_managers():
    """初始化所有管理器"""
    global crawler_manager, phone_pool_manager, session_manager, db_manager
    
    try:
        # 初始化配置
        config = Config()
        
        # 初始化数据库管理器
        db_manager = DatabaseManager(config)
        
        # 初始化会话管理器
        session_manager = SessionManager(config, db_manager)
        
        # 初始化号码池管理器
        phone_pool_manager = PhonePoolManager(config, db_manager)
        
        # 初始化爬虫管理器
        crawler_manager = CrawlerManager(
            config=config,
            phone_pool=phone_pool_manager,
            session_manager=session_manager,
            db_manager=db_manager
        )
        
        logger.info("✅ 所有管理器初始化成功")
        
    except Exception as e:
        logger.error(f"❌ 管理器初始化失败: {e}")
        raise

def before_first_request():
    """在第一个请求前初始化"""
    initialize_managers()

# 在应用启动时初始化
with app.app_context():
    before_first_request()

@app.route('/health')
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'healthy',
        'message': '爬虫号码池注册服务运行正常',
        'version': '1.0.0',
        'timestamp': time.time(),
        'services': {
            'crawler_manager': crawler_manager is not None,
            'phone_pool': phone_pool_manager is not None,
            'session_manager': session_manager is not None,
            'database': db_manager is not None
        }
    })

@app.route('/')
def index():
    """根路径"""
    return jsonify({
        'message': '爬虫号码池注册API服务',
        'version': '1.0.0',
        'endpoints': {
            'health': '/health',
            'register': '/api/register',
            'login': '/api/login',
            'phone_pool': '/api/phone-pool',
            'captcha': '/api/captcha',
            'data': '/api/data'
        }
    })

# 注册API路由
register_routes(app, crawler_manager, phone_pool_manager, session_manager)

@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return jsonify({
        'error': '接口不存在',
        'message': '请检查API路径是否正确',
        'available_endpoints': [
            '/health',
            '/api/register',
            '/api/login',
            '/api/phone-pool',
            '/api/captcha',
            '/api/data'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    logger.error(f"内部服务器错误: {error}")
    return jsonify({
        'error': '内部服务器错误',
        'message': '请稍后重试'
    }), 500

@app.errorhandler(Exception)
def handle_exception(error):
    """通用异常处理"""
    logger.error(f"未处理的异常: {error}")
    return jsonify({
        'error': '服务器异常',
        'message': str(error)
    }), 500

if __name__ == '__main__':
    # 创建日志目录
    os.makedirs('logs', exist_ok=True)
    
    logger.info("🚀 启动爬虫号码池注册服务")
    logger.info("📁 项目根目录: " + os.path.dirname(os.path.abspath(__file__)))
    
    # 启动服务
    app.run(
        host='0.0.0.0',
        port=9003,
        debug=True,
        threaded=True
    ) 