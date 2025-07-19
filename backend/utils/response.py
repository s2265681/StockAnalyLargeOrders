"""
响应工具模块
统一API响应格式
"""
from flask import jsonify
from datetime import datetime

def success_response(data=None, message='success', code=200):
    """成功响应格式"""
    response = {
        'code': code,
        'message': message,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }
    return jsonify(response)

def error_response(message='error', code=500, error_type=None, data=None):
    """错误响应格式"""
    response = {
        'code': code,
        'message': message,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }
    if error_type:
        response['error_type'] = error_type
    return jsonify(response), code

def v1_success_response(data=None, message='success'):
    """竞品格式成功响应"""
    return jsonify({
        'success': True,
        'data': data,
        'message': message
    })

def v1_error_response(message='error', data=None):
    """竞品格式错误响应"""
    return jsonify({
        'success': False,
        'data': data,
        'message': message
    }) 