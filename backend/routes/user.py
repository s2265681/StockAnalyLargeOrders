"""用户信息 API"""
import logging
import re
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query, execute_write
from utils.auth_middleware import login_required

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__)

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _validate_email(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(email.strip()))


@user_bp.route('/api/user/profile', methods=['GET'])
@login_required
def get_profile():
    user_id = request.current_user['user_id']

    user = execute_query(
        'SELECT id, username, phone, default_email, role, created_at FROM users WHERE id = %s',
        (user_id,),
    )
    if not user:
        return v1_error_response('用户不存在')

    u = user[0]
    sub = execute_query(
        'SELECT plan_type, end_time FROM user_subscriptions '
        'WHERE user_id = %s AND is_active = 1 AND end_time > NOW() '
        'ORDER BY end_time DESC LIMIT 1',
        (user_id,)
    )

    vip_info = None
    if sub:
        vip_info = {
            'plan_type': sub[0]['plan_type'],
            'end_time': sub[0]['end_time'].strftime('%Y-%m-%d %H:%M:%S') if sub[0]['end_time'] else None,
        }

    return v1_success_response(data={
        'id': u['id'],
        'username': u['username'],
        'phone': u['phone'],
        'default_email': u.get('default_email') or '',
        'role': u['role'],
        'created_at': u['created_at'].strftime('%Y-%m-%d %H:%M:%S') if u['created_at'] else None,
        'vip': vip_info,
    })


@user_bp.route('/api/user/profile', methods=['PUT'])
@login_required
def update_profile():
    user_id = request.current_user['user_id']
    body = request.get_json(silent=True) or {}

    if 'default_email' not in body:
        return v1_error_response('缺少 default_email 字段')

    default_email = (body.get('default_email') or '').strip()
    if default_email and not _validate_email(default_email):
        return v1_error_response('邮箱格式不正确')

    execute_write(
        'UPDATE users SET default_email = %s WHERE id = %s',
        (default_email or None, user_id),
    )
    return v1_success_response(
        data={'default_email': default_email},
        message='常用邮箱已保存',
    )
