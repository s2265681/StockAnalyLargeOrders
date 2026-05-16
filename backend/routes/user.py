# backend/routes/user.py
from flask import Blueprint, request, jsonify
from utils.db import execute_query
from utils.auth_middleware import require_auth

user_bp = Blueprint('user', __name__)


@user_bp.route('/api/user/profile', methods=['GET'])
@require_auth
def profile():
    user_id = request.current_user['user_id']
    rows = execute_query(
        'SELECT id, username, phone, role FROM users WHERE id=%s',
        (user_id,)
    )
    if not rows:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    user = rows[0]

    subs = execute_query(
        'SELECT plan_type, end_time FROM user_subscriptions '
        'WHERE user_id=%s AND is_active=1 AND end_time > NOW() '
        'ORDER BY end_time DESC LIMIT 1',
        (user_id,)
    )
    expire_time = None
    is_vip = False
    if subs:
        sub = subs[0]
        expire_time = (
            sub['end_time'].strftime('%Y/%m/%d %H:%M:%S')
            if hasattr(sub['end_time'], 'strftime')
            else str(sub['end_time'])
        )
        is_vip = True

    return jsonify({
        'success': True,
        'data': {
            'id': user['id'],
            'username': user['username'],
            'phone': user['phone'] or '',
            'role': user['role'],
            'is_vip': is_vip,
            'expire_time': expire_time,
        }
    })
