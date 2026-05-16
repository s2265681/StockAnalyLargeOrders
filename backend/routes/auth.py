# backend/routes/auth.py
import datetime
import jwt
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from utils.db import execute_query, execute_write
from utils.auth_middleware import JWT_SECRET, JWT_ALGORITHM, JWT_EXP_DAYS, require_auth

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    rows = execute_query(
        'SELECT id, username, password_hash, phone, role FROM users WHERE username=%s',
        (username,)
    )
    if not rows:
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401
    user = rows[0]

    if not check_password_hash(user['password_hash'], password):
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

    exp = datetime.datetime.utcnow() + datetime.timedelta(days=JWT_EXP_DAYS)
    payload = {
        'user_id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'exp': exp,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'phone': user['phone'],
            'role': user['role'],
        },
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
@require_auth
def logout():
    # JWT 无状态，前端清除 token 即可
    return jsonify({'success': True, 'message': '已退出登录'})


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@require_auth
def change_password():
    data = request.get_json(silent=True) or {}
    old_password = (data.get('old_password') or '').strip()
    new_password = (data.get('new_password') or '').strip()
    if not old_password or not new_password:
        return jsonify({'success': False, 'message': '旧密码和新密码不能为空'}), 400
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码长度不能少于6位'}), 400

    user_id = request.current_user['user_id']
    rows = execute_query('SELECT password_hash FROM users WHERE id=%s', (user_id,))
    if not rows:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    if not check_password_hash(rows[0]['password_hash'], old_password):
        return jsonify({'success': False, 'message': '旧密码错误'}), 400

    new_hash = generate_password_hash(new_password)
    execute_write('UPDATE users SET password_hash=%s WHERE id=%s', (new_hash, user_id))
    return jsonify({'success': True, 'message': '密码修改成功'})
