#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会话管理器
"""

import time
import json
import uuid
import random
from datetime import datetime, timedelta
from loguru import logger
import threading
import requests

class SessionManager:
    """会话管理器"""
    
    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.sessions = {}  # 内存中的会话缓存
        self.lock = threading.Lock()
    
    def create_session(self, user_id=None):
        """创建新会话"""
        try:
            session_id = str(uuid.uuid4())
            
            # 创建requests会话
            session = requests.Session()
            
            # 设置默认请求头
            session.headers.update({
                'User-Agent': random.choice(self.config.USER_AGENTS),
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'zh-CN,zh;q=0.9,en-AU;q=0.8,en;q=0.7,vi;q=0.6,th;q=0.5,id;q=0.4,en-US;q=0.3',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Ch-Ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"macOS"',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'X-Requested-With': 'XMLHttpRequest'
            })
            
            # 设置代理（如果启用）
            if self.config.USE_PROXY and self.config.PROXY_LIST:
                proxy = random.choice(self.config.PROXY_LIST)
                session.proxies = {
                    'http': proxy,
                    'https': proxy
                }
            
            # 设置超时
            session.timeout = self.config.REQUEST_TIMEOUT
            
            # 创建会话数据
            session_data = {
                'id': session_id,
                'user_id': user_id,
                'session': session,
                'created_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(seconds=self.config.SESSION_TIMEOUT),
                'is_active': True,
                'request_count': 0,
                'last_request': None
            }
            
            # 保存到内存
            with self.lock:
                self.sessions[session_id] = session_data
            
            # 保存到数据库
            if user_id:
                self.db_manager.add_session(
                    user_id=user_id,
                    session_id=session_id,
                    cookies=dict(session.cookies),
                    headers=dict(session.headers),
                    expires_at=session_data['expires_at']
                )
            
            logger.info(f"✅ 创建会话成功: {session_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            return None
    
    def get_session(self, session_id):
        """获取会话"""
        try:
            with self.lock:
                if session_id in self.sessions:
                    session_data = self.sessions[session_id]
                    
                    # 检查会话是否过期
                    if session_data['expires_at'] < datetime.now():
                        logger.warning(f"会话已过期: {session_id}")
                        self.remove_session(session_id)
                        return None
                    
                    # 更新请求计数
                    session_data['request_count'] += 1
                    session_data['last_request'] = datetime.now()
                    
                    return session_data['session']
                
                # 从数据库恢复会话
                db_session = self.db_manager.get_session(session_id)
                if db_session:
                    # 重新创建requests会话
                    session = requests.Session()
                    
                    # 恢复cookies
                    if db_session.get('cookies'):
                        session.cookies.update(db_session['cookies'])
                    
                    # 恢复headers
                    if db_session.get('headers'):
                        session.headers.update(db_session['headers'])
                    
                    # 设置默认配置
                    session.headers.update({
                        'User-Agent': random.choice(self.config.USER_AGENTS),
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en-AU;q=0.8,en;q=0.7,vi:q=0.6,th;q=0.5,id;q=0.4,en-US;q=0.3',
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache',
                        'Sec-Ch-Ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                        'Sec-Ch-Ua-Mobile': '?0',
                        'Sec-Ch-Ua-Platform': '"macOS"',
                        'Sec-Fetch-Dest': 'empty',
                        'Sec-Fetch-Mode': 'cors',
                        'Sec-Fetch-Site': 'same-origin',
                        'X-Requested-With': 'XMLHttpRequest'
                    })
                    
                    session.timeout = self.config.REQUEST_TIMEOUT
                    
                    # 保存到内存
                    session_data = {
                        'id': session_id,
                        'user_id': db_session.get('user_id'),
                        'session': session,
                        'created_at': datetime.fromisoformat(db_session['created_at']),
                        'expires_at': datetime.fromisoformat(db_session['expires_at']) if db_session['expires_at'] else None,
                        'is_active': True,
                        'request_count': 0,
                        'last_request': datetime.now()
                    }
                    
                    self.sessions[session_id] = session_data
                    logger.info(f"✅ 从数据库恢复会话: {session_id}")
                    return session
                
                return None
                
        except Exception as e:
            logger.error(f"获取会话失败: {e}")
            return None
    
    def remove_session(self, session_id):
        """移除会话"""
        try:
            with self.lock:
                if session_id in self.sessions:
                    session_data = self.sessions[session_id]
                    
                    # 关闭requests会话
                    if session_data['session']:
                        session_data['session'].close()
                    
                    # 从内存移除
                    del self.sessions[session_id]
                    
                    # 从数据库标记为非活跃
                    # 这里可以添加数据库更新逻辑
                    
                    logger.info(f"✅ 移除会话: {session_id}")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"移除会话失败: {e}")
            return False
    
    def update_session_cookies(self, session_id, cookies):
        """更新会话cookies"""
        try:
            session = self.get_session(session_id)
            if session:
                session.cookies.update(cookies)
                
                # 更新数据库中的cookies
                with self.lock:
                    if session_id in self.sessions:
                        user_id = self.sessions[session_id]['user_id']
                        if user_id:
                            # 这里可以添加数据库更新逻辑
                            pass
                
                logger.info(f"✅ 更新会话cookies: {session_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"更新会话cookies失败: {e}")
            return False
    
    def get_session_info(self, session_id):
        """获取会话信息"""
        try:
            with self.lock:
                if session_id in self.sessions:
                    session_data = self.sessions[session_id]
                    return {
                        'id': session_id,
                        'user_id': session_data['user_id'],
                        'created_at': session_data['created_at'].isoformat(),
                        'expires_at': session_data['expires_at'].isoformat() if session_data['expires_at'] else None,
                        'is_active': session_data['is_active'],
                        'request_count': session_data['request_count'],
                        'last_request': session_data['last_request'].isoformat() if session_data['last_request'] else None,
                        'cookies_count': len(session_data['session'].cookies),
                        'headers_count': len(session_data['session'].headers)
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"获取会话信息失败: {e}")
            return None
    
    def cleanup_expired_sessions(self):
        """清理过期会话"""
        try:
            with self.lock:
                current_time = datetime.now()
                expired_sessions = []
                
                for session_id, session_data in self.sessions.items():
                    if session_data['expires_at'] and session_data['expires_at'] < current_time:
                        expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    self.remove_session(session_id)
                
                if expired_sessions:
                    logger.info(f"✅ 清理了 {len(expired_sessions)} 个过期会话")
                
        except Exception as e:
            logger.error(f"清理过期会话失败: {e}")
    
    def get_all_sessions(self):
        """获取所有会话信息"""
        try:
            with self.lock:
                sessions_info = []
                for session_id, session_data in self.sessions.items():
                    sessions_info.append(self.get_session_info(session_id))
                
                return sessions_info
                
        except Exception as e:
            logger.error(f"获取所有会话信息失败: {e}")
            return []
    
    def get_session_count(self):
        """获取会话数量"""
        try:
            with self.lock:
                return len(self.sessions)
        except Exception as e:
            logger.error(f"获取会话数量失败: {e}")
            return 0 