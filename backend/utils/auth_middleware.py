"""JWT 认证中间件"""
import os
import logging
from functools import wraps
from flask import request, jsonify
import jwt
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get('JWT_SECRET', 'niuniu-secret')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_DAYS = 7


def generate_token(user_id, username, role='user'):
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'exp': datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning('Token 已过期')
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f'Token 无效: {e}')
        return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': '未登录'}), 401
        token = auth_header[7:]
        payload = decode_token(token)
        if payload is None:
            return jsonify({'success': False, 'message': '登录已过期，请重新登录'}), 401
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if request.current_user.get('role') != 'admin':
            return jsonify({'success': False, 'message': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated
