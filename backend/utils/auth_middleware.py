# backend/utils/auth_middleware.py
import os
import jwt
from functools import wraps
from flask import request, jsonify

JWT_SECRET = os.environ.get('JWT_SECRET', 'niuniu-jwt-secret-2026')
JWT_ALGORITHM = 'HS256'
JWT_EXP_DAYS = 7


def require_auth(f):
    """JWT 鉴权装饰器，从 Authorization: Bearer <token> 中提取用户信息"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': '未登录或token无效'}), 401
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.current_user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'message': 'token已过期，请重新登录'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'message': 'token无效'}), 401
        return f(*args, **kwargs)
    return decorated
