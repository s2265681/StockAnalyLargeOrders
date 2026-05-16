"""认证相关 API：注册、登录、修改密码"""
import logging
from flask import Blueprint, request
from werkzeug.security import generate_password_hash, check_password_hash
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query, execute_write
from utils.auth_middleware import generate_token, login_required

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    body = request.get_json(silent=True) or {}
    username = (body.get('username') or '').strip()
    password = body.get('password', '')
    phone = (body.get('phone') or '').strip() or None

    if not username or len(username) < 2 or len(username) > 20:
        return v1_error_response('用户名需要2-20个字符')
    if not password or len(password) < 6:
        return v1_error_response('密码至少6个字符')

    existing = execute_query('SELECT id FROM users WHERE username = %s', (username,))
    if existing:
        return v1_error_response('用户名已存在')

    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    try:
        execute_write(
            'INSERT INTO users (username, password_hash, phone) VALUES (%s, %s, %s)',
            (username, password_hash, phone)
        )
    except Exception as e:
        logger.error(f'注册失败: {e}')
        return v1_error_response('注册失败，请稍后重试')

    user = execute_query('SELECT id, username, role FROM users WHERE username = %s', (username,))
    if user:
        u = user[0]
        token = generate_token(u['id'], u['username'], u['role'])
        return v1_success_response(data={
            'token': token,
            'user': {'id': u['id'], 'username': u['username'], 'role': u['role']}
        }, message='注册成功')

    return v1_error_response('注册异常')


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get('username') or '').strip()
    password = body.get('password', '')

    if not username or not password:
        return v1_error_response('请输入用户名和密码')

    user = execute_query(
        'SELECT id, username, password_hash, role FROM users WHERE username = %s', (username,)
    )
    if not user:
        return v1_error_response('用户名或密码错误')

    u = user[0]
    if not check_password_hash(u['password_hash'], password):
        return v1_error_response('用户名或密码错误')

    token = generate_token(u['id'], u['username'], u['role'])
    return v1_success_response(data={
        'token': token,
        'user': {'id': u['id'], 'username': u['username'], 'role': u['role']}
    }, message='登录成功')


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    body = request.get_json(silent=True) or {}
    old_password = body.get('old_password', '')
    new_password = body.get('new_password', '')

    if not old_password or not new_password:
        return v1_error_response('请输入旧密码和新密码')
    if len(new_password) < 6:
        return v1_error_response('新密码至少6个字符')

    user_id = request.current_user['user_id']
    user = execute_query('SELECT password_hash FROM users WHERE id = %s', (user_id,))
    if not user:
        return v1_error_response('用户不存在')

    if not check_password_hash(user[0]['password_hash'], old_password):
        return v1_error_response('旧密码错误')

    new_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    execute_write('UPDATE users SET password_hash = %s WHERE id = %s', (new_hash, user_id))
    return v1_success_response(message='密码修改成功')
