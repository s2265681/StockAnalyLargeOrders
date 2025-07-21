#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库管理器
"""

import sqlite3
import json
import time
from datetime import datetime, timedelta
from loguru import logger
import threading

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, config):
        self.config = config
        self.db_path = 'crawler.db'
        self.lock = threading.Lock()
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 创建用户表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        phone TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        token TEXT,
                        finger_print TEXT,
                        status TEXT DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        login_count INTEGER DEFAULT 0,
                        register_count INTEGER DEFAULT 0
                    )
                ''')
                
                # 创建号码池表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS phone_pool (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone TEXT UNIQUE NOT NULL,
                        status TEXT DEFAULT 'available',
                        usage_count INTEGER DEFAULT 0,
                        last_used TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        source TEXT,
                        notes TEXT
                    )
                ''')
                
                # 创建会话表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        session_id TEXT UNIQUE NOT NULL,
                        cookies TEXT,
                        headers TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                
                # 创建验证码表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS captchas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone TEXT NOT NULL,
                        captcha_type TEXT NOT NULL,
                        captcha_code TEXT,
                        captcha_image TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        solved_at TIMESTAMP,
                        attempts INTEGER DEFAULT 0
                    )
                ''')
                
                # 创建请求日志表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS request_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        endpoint TEXT NOT NULL,
                        method TEXT NOT NULL,
                        status_code INTEGER,
                        response_time REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ip_address TEXT,
                        user_agent TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                
                # 创建黑名单表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS blacklist (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_type TEXT NOT NULL,
                        item_value TEXT NOT NULL,
                        reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1
                    )
                ''')
                
                conn.commit()
                logger.info("✅ 数据库初始化成功")
                
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")
            raise
    
    def add_user(self, username, email, phone, password, token=None, finger_print=None):
        """添加用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (username, email, phone, password, token, finger_print)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (username, email, phone, password, token, finger_print))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.warning(f"用户已存在: {username}")
            return None
        except Exception as e:
            logger.error(f"添加用户失败: {e}")
            return None
    
    def get_user_by_phone(self, phone):
        """根据手机号获取用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE phone = ?', (phone,))
                row = cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            logger.error(f"获取用户失败: {e}")
            return None
    
    def update_user_token(self, user_id, token, finger_print):
        """更新用户token"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET token = ?, finger_print = ?, last_login = CURRENT_TIMESTAMP, login_count = login_count + 1
                    WHERE id = ?
                ''', (token, finger_print, user_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"更新用户token失败: {e}")
            return False
    
    def add_phone_to_pool(self, phone, source="manual", expires_at=None):
        """添加号码到号码池"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO phone_pool (phone, source, expires_at)
                    VALUES (?, ?, ?)
                ''', (phone, source, expires_at))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.warning(f"号码已存在: {phone}")
            return None
        except Exception as e:
            logger.error(f"添加号码失败: {e}")
            return None
    
    def get_available_phone(self):
        """获取可用号码"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM phone_pool 
                    WHERE status = 'available' 
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    AND usage_count < ?
                    ORDER BY last_used ASC NULLS FIRST
                    LIMIT 1
                ''', (self.config.PHONE_MAX_USAGE,))
                row = cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            logger.error(f"获取可用号码失败: {e}")
            return None
    
    def mark_phone_used(self, phone_id):
        """标记号码已使用"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE phone_pool 
                    SET status = 'in_use', usage_count = usage_count + 1, last_used = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (phone_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"标记号码使用失败: {e}")
            return False
    
    def mark_phone_available(self, phone_id):
        """标记号码可用"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE phone_pool 
                    SET status = 'available'
                    WHERE id = ?
                ''', (phone_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"标记号码可用失败: {e}")
            return False
    
    def add_session(self, user_id, session_id, cookies, headers, expires_at=None):
        """添加会话"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO sessions (user_id, session_id, cookies, headers, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, session_id, json.dumps(cookies), json.dumps(headers), expires_at))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加会话失败: {e}")
            return None
    
    def get_session(self, session_id):
        """获取会话"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM sessions 
                    WHERE session_id = ? AND is_active = 1 
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ''', (session_id,))
                row = cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    session_data = dict(zip(columns, row))
                    session_data['cookies'] = json.loads(session_data['cookies'])
                    session_data['headers'] = json.loads(session_data['headers'])
                    return session_data
                return None
        except Exception as e:
            logger.error(f"获取会话失败: {e}")
            return None
    
    def add_captcha(self, phone, captcha_type, captcha_code=None, captcha_image=None):
        """添加验证码记录"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO captchas (phone, captcha_type, captcha_code, captcha_image)
                    VALUES (?, ?, ?, ?)
                ''', (phone, captcha_type, captcha_code, captcha_image))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加验证码记录失败: {e}")
            return None
    
    def update_captcha_solved(self, captcha_id, captcha_code):
        """更新验证码已解决"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE captchas 
                    SET captcha_code = ?, status = 'solved', solved_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (captcha_code, captcha_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"更新验证码状态失败: {e}")
            return False
    
    def add_to_blacklist(self, item_type, item_value, reason, duration_hours=24):
        """添加到黑名单"""
        try:
            expires_at = datetime.now() + timedelta(hours=duration_hours)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO blacklist (item_type, item_value, reason, expires_at)
                    VALUES (?, ?, ?, ?)
                ''', (item_type, item_value, reason, expires_at))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加到黑名单失败: {e}")
            return None
    
    def is_blacklisted(self, item_type, item_value):
        """检查是否在黑名单中"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM blacklist 
                    WHERE item_type = ? AND item_value = ? 
                    AND is_active = 1 
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ''', (item_type, item_value))
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            logger.error(f"检查黑名单失败: {e}")
            return False
    
    def log_request(self, user_id, endpoint, method, status_code, response_time, ip_address=None, user_agent=None):
        """记录请求日志"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO request_logs (user_id, endpoint, method, status_code, response_time, ip_address, user_agent)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, endpoint, method, status_code, response_time, ip_address, user_agent))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"记录请求日志失败: {e}")
            return False
    
    def cleanup_expired_data(self):
        """清理过期数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 清理过期会话
                cursor.execute('''
                    UPDATE sessions 
                    SET is_active = 0 
                    WHERE expires_at < CURRENT_TIMESTAMP
                ''')
                
                # 清理过期黑名单
                cursor.execute('''
                    UPDATE blacklist 
                    SET is_active = 0 
                    WHERE expires_at < CURRENT_TIMESTAMP
                ''')
                
                # 清理过期请求日志
                retention_date = datetime.now() - timedelta(days=self.config.MAX_DATA_RETENTION)
                cursor.execute('''
                    DELETE FROM request_logs 
                    WHERE created_at < ?
                ''', (retention_date,))
                
                conn.commit()
                logger.info("✅ 过期数据清理完成")
                
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}") 