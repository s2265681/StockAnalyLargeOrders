#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
号码池管理器
"""

import time
import random
import string
from datetime import datetime, timedelta
from loguru import logger
import threading

class PhonePoolManager:
    """号码池管理器"""
    
    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.lock = threading.Lock()
        self.phone_cache = {}  # 内存缓存
        self.init_phone_pool()
    
    def init_phone_pool(self):
        """初始化号码池"""
        try:
            # 添加一些测试号码
            test_phones = [
                "15605489400",  # 接口说明中的测试号码
                "13800138000",
                "13900139000",
                "13700137000",
                "13600136000",
                "13500135000"
            ]
            
            for phone in test_phones:
                self.add_phone(phone, source="test")
            
            logger.info(f"✅ 号码池初始化完成，当前号码数量: {len(test_phones)}")
            
        except Exception as e:
            logger.error(f"❌ 号码池初始化失败: {e}")
    
    def add_phone(self, phone, source="manual", expires_at=None):
        """添加号码到号码池"""
        try:
            with self.lock:
                # 检查号码格式
                if not self.validate_phone(phone):
                    logger.warning(f"号码格式无效: {phone}")
                    return False
                
                # 添加到数据库
                phone_id = self.db_manager.add_phone_to_pool(phone, source, expires_at)
                if phone_id:
                    # 添加到内存缓存
                    self.phone_cache[phone] = {
                        'id': phone_id,
                        'status': 'available',
                        'usage_count': 0,
                        'last_used': None,
                        'source': source,
                        'expires_at': expires_at
                    }
                    logger.info(f"✅ 号码 {phone} 已添加到号码池")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"添加号码失败: {e}")
            return False
    
    def get_phone(self):
        """获取可用号码"""
        try:
            with self.lock:
                # 先从数据库获取
                phone_data = self.db_manager.get_available_phone()
                if not phone_data:
                    logger.warning("号码池中没有可用号码")
                    return None
                
                # 标记号码为使用中
                if self.db_manager.mark_phone_used(phone_data['id']):
                    # 更新内存缓存
                    phone = phone_data['phone']
                    if phone in self.phone_cache:
                        self.phone_cache[phone]['status'] = 'in_use'
                        self.phone_cache[phone]['usage_count'] += 1
                        self.phone_cache[phone]['last_used'] = datetime.now()
                    
                    logger.info(f"✅ 获取号码: {phone}")
                    return phone_data
                
                return None
                
        except Exception as e:
            logger.error(f"获取号码失败: {e}")
            return None
    
    def release_phone(self, phone):
        """释放号码"""
        try:
            with self.lock:
                # 从数据库获取号码信息
                phone_data = self.db_manager.get_available_phone()
                if phone_data and phone_data['phone'] == phone:
                    # 标记号码为可用
                    if self.db_manager.mark_phone_available(phone_data['id']):
                        # 更新内存缓存
                        if phone in self.phone_cache:
                            self.phone_cache[phone]['status'] = 'available'
                        
                        logger.info(f"✅ 释放号码: {phone}")
                        return True
                
                return False
                
        except Exception as e:
            logger.error(f"释放号码失败: {e}")
            return False
    
    def generate_phone(self):
        """生成虚拟号码"""
        try:
            # 生成11位手机号
            prefixes = ['130', '131', '132', '133', '134', '135', '136', '137', '138', '139',
                       '150', '151', '152', '153', '155', '156', '157', '158', '159',
                       '180', '181', '182', '183', '184', '185', '186', '187', '188', '189']
            
            prefix = random.choice(prefixes)
            suffix = ''.join(random.choices(string.digits, k=8))
            phone = prefix + suffix
            
            return phone
            
        except Exception as e:
            logger.error(f"生成号码失败: {e}")
            return None
    
    def validate_phone(self, phone):
        """验证号码格式"""
        if not phone or len(phone) != 11:
            return False
        
        if not phone.isdigit():
            return False
        
        # 检查号码前缀
        valid_prefixes = ['130', '131', '132', '133', '134', '135', '136', '137', '138', '139',
                         '150', '151', '152', '153', '155', '156', '157', '158', '159',
                         '180', '181', '182', '183', '184', '185', '186', '187', '188', '189']
        
        return any(phone.startswith(prefix) for prefix in valid_prefixes)
    
    def get_pool_status(self):
        """获取号码池状态"""
        try:
            with self.lock:
                total_count = len(self.phone_cache)
                available_count = sum(1 for phone in self.phone_cache.values() 
                                    if phone['status'] == 'available')
                in_use_count = sum(1 for phone in self.phone_cache.values() 
                                 if phone['status'] == 'in_use')
                
                return {
                    'total': total_count,
                    'available': available_count,
                    'in_use': in_use_count,
                    'utilization_rate': (in_use_count / total_count * 100) if total_count > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"获取号码池状态失败: {e}")
            return None
    
    def cleanup_expired_phones(self):
        """清理过期号码"""
        try:
            with self.lock:
                current_time = datetime.now()
                expired_phones = []
                
                for phone, data in self.phone_cache.items():
                    if data['expires_at'] and data['expires_at'] < current_time:
                        expired_phones.append(phone)
                
                for phone in expired_phones:
                    del self.phone_cache[phone]
                    logger.info(f"清理过期号码: {phone}")
                
                if expired_phones:
                    logger.info(f"✅ 清理了 {len(expired_phones)} 个过期号码")
                
        except Exception as e:
            logger.error(f"清理过期号码失败: {e}")
    
    def get_phone_info(self, phone):
        """获取号码信息"""
        try:
            with self.lock:
                if phone in self.phone_cache:
                    return self.phone_cache[phone].copy()
                return None
                
        except Exception as e:
            logger.error(f"获取号码信息失败: {e}")
            return None
    
    def mark_phone_blocked(self, phone, reason="unknown"):
        """标记号码为被封禁"""
        try:
            with self.lock:
                # 添加到黑名单
                self.db_manager.add_to_blacklist('phone', phone, reason)
                
                # 更新内存缓存
                if phone in self.phone_cache:
                    self.phone_cache[phone]['status'] = 'blocked'
                
                logger.warning(f"号码 {phone} 已被标记为封禁，原因: {reason}")
                return True
                
        except Exception as e:
            logger.error(f"标记号码封禁失败: {e}")
            return False
    
    def is_phone_blocked(self, phone):
        """检查号码是否被封禁"""
        try:
            return self.db_manager.is_blacklisted('phone', phone)
        except Exception as e:
            logger.error(f"检查号码封禁状态失败: {e}")
            return False 