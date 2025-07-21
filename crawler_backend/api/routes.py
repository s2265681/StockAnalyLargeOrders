#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API路由
"""

from flask import request, jsonify
from loguru import logger
import time

def register_routes(app, crawler_manager, phone_pool_manager, session_manager):
    """注册所有API路由"""
    
    @app.route('/api/register', methods=['POST'])
    def register_account():
        """注册账户接口"""
        try:
            start_time = time.time()
            
            # 获取请求参数
            data = request.get_json() or {}
            user_info = data.get('user_info')
            count = data.get('count', 1)
            
            if count > 1:
                # 批量注册
                results = crawler_manager.batch_register(count)
                success_count = len([r for r in results if r])
                
                return jsonify({
                    'success': True,
                    'message': f'批量注册完成，成功 {success_count}/{count} 个账户',
                    'data': {
                        'total': count,
                        'success': success_count,
                        'failed': count - success_count,
                        'results': results
                    },
                    'response_time': time.time() - start_time
                })
            else:
                # 单个注册
                result = crawler_manager.register_account(user_info)
                
                if result:
                    return jsonify({
                        'success': True,
                        'message': '注册成功',
                        'data': result,
                        'response_time': time.time() - start_time
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': '注册失败',
                        'data': None,
                        'response_time': time.time() - start_time
                    }), 400
                    
        except Exception as e:
            logger.error(f"注册接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'注册失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/login', methods=['POST'])
    def login_account():
        """登录账户接口"""
        try:
            start_time = time.time()
            
            # 获取请求参数
            data = request.get_json() or {}
            username = data.get('username')
            password = data.get('password')
            session_id = data.get('session_id')
            
            if not username or not password:
                return jsonify({
                    'success': False,
                    'message': '用户名和密码不能为空',
                    'data': None
                }), 400
            
            result = crawler_manager.login_account(username, password, session_id)
            
            if result:
                return jsonify({
                    'success': True,
                    'message': '登录成功',
                    'data': result,
                    'response_time': time.time() - start_time
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '登录失败',
                    'data': None,
                    'response_time': time.time() - start_time
                }), 400
                
        except Exception as e:
            logger.error(f"登录接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'登录失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/data', methods=['POST'])
    def get_stock_data():
        """获取股票数据接口"""
        try:
            start_time = time.time()
            
            # 获取请求参数
            data = request.get_json() or {}
            user_info = data.get('user_info')
            stock_code = data.get('stock_code', '000001')
            
            if not user_info:
                return jsonify({
                    'success': False,
                    'message': '用户信息不能为空',
                    'data': None
                }), 400
            
            result = crawler_manager.get_stock_data(user_info, stock_code)
            
            if result:
                return jsonify({
                    'success': True,
                    'message': '获取数据成功',
                    'data': result,
                    'response_time': time.time() - start_time
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '获取数据失败',
                    'data': None,
                    'response_time': time.time() - start_time
                }), 400
                
        except Exception as e:
            logger.error(f"获取数据接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'获取数据失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/phone-pool', methods=['GET'])
    def get_phone_pool_status():
        """获取号码池状态接口"""
        try:
            status = phone_pool_manager.get_pool_status()
            
            return jsonify({
                'success': True,
                'message': '获取号码池状态成功',
                'data': status
            })
            
        except Exception as e:
            logger.error(f"获取号码池状态接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'获取号码池状态失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/phone-pool', methods=['POST'])
    def add_phone_to_pool():
        """添加号码到号码池接口"""
        try:
            data = request.get_json() or {}
            phone = data.get('phone')
            source = data.get('source', 'manual')
            
            if not phone:
                return jsonify({
                    'success': False,
                    'message': '手机号码不能为空',
                    'data': None
                }), 400
            
            result = phone_pool_manager.add_phone(phone, source)
            
            if result:
                return jsonify({
                    'success': True,
                    'message': '添加号码成功',
                    'data': {'phone': phone, 'source': source}
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '添加号码失败',
                    'data': None
                }), 400
                
        except Exception as e:
            logger.error(f"添加号码接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'添加号码失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/captcha', methods=['POST'])
    def solve_captcha():
        """验证码识别接口"""
        try:
            data = request.get_json() or {}
            image_data = data.get('image_data')
            captcha_type = data.get('captcha_type', 'general')
            
            if not image_data:
                return jsonify({
                    'success': False,
                    'message': '图片数据不能为空',
                    'data': None
                }), 400
            
            if crawler_manager.captcha_solver:
                result = crawler_manager.captcha_solver.solve_image_captcha(image_data, captcha_type)
                
                if result:
                    return jsonify({
                        'success': True,
                        'message': '验证码识别成功',
                        'data': {'captcha_code': result}
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': '验证码识别失败',
                        'data': None
                    }), 400
            else:
                return jsonify({
                    'success': False,
                    'message': '验证码识别器未初始化',
                    'data': None
                }), 500
                
        except Exception as e:
            logger.error(f"验证码识别接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'验证码识别失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/sessions', methods=['GET'])
    def get_sessions():
        """获取会话列表接口"""
        try:
            sessions = session_manager.get_all_sessions()
            
            return jsonify({
                'success': True,
                'message': '获取会话列表成功',
                'data': {
                    'sessions': sessions,
                    'count': len(sessions)
                }
            })
            
        except Exception as e:
            logger.error(f"获取会话列表接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'获取会话列表失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/sessions/<session_id>', methods=['GET'])
    def get_session_info(session_id):
        """获取会话信息接口"""
        try:
            session_info = session_manager.get_session_info(session_id)
            
            if session_info:
                return jsonify({
                    'success': True,
                    'message': '获取会话信息成功',
                    'data': session_info
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '会话不存在',
                    'data': None
                }), 404
                
        except Exception as e:
            logger.error(f"获取会话信息接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'获取会话信息失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/sessions/<session_id>', methods=['DELETE'])
    def remove_session(session_id):
        """移除会话接口"""
        try:
            result = session_manager.remove_session(session_id)
            
            if result:
                return jsonify({
                    'success': True,
                    'message': '移除会话成功',
                    'data': {'session_id': session_id}
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '会话不存在',
                    'data': None
                }), 404
                
        except Exception as e:
            logger.error(f"移除会话接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'移除会话失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/status', methods=['GET'])
    def get_system_status():
        """获取系统状态接口"""
        try:
            status = crawler_manager.get_system_status()
            
            if status:
                return jsonify({
                    'success': True,
                    'message': '获取系统状态成功',
                    'data': status
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '获取系统状态失败',
                    'data': None
                }), 500
                
        except Exception as e:
            logger.error(f"获取系统状态接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'获取系统状态失败: {str(e)}',
                'data': None
            }), 500
    
    @app.route('/api/cleanup', methods=['POST'])
    def cleanup_system():
        """清理系统接口"""
        try:
            # 清理过期会话
            session_manager.cleanup_expired_sessions()
            
            # 清理过期号码
            phone_pool_manager.cleanup_expired_phones()
            
            # 清理过期数据
            crawler_manager.db_manager.cleanup_expired_data()
            
            return jsonify({
                'success': True,
                'message': '系统清理完成',
                'data': {
                    'sessions_cleaned': True,
                    'phones_cleaned': True,
                    'data_cleaned': True
                }
            })
            
        except Exception as e:
            logger.error(f"系统清理接口异常: {e}")
            return jsonify({
                'success': False,
                'message': f'系统清理失败: {str(e)}',
                'data': None
            }), 500 