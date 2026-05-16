"""用户信息 API"""
import logging
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query
from utils.auth_middleware import login_required

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__)


@user_bp.route('/api/user/profile', methods=['GET'])
@login_required
def get_profile():
    user_id = request.current_user['user_id']

    user = execute_query(
        'SELECT id, username, phone, role, created_at FROM users WHERE id = %s', (user_id,)
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
        'role': u['role'],
        'created_at': u['created_at'].strftime('%Y-%m-%d %H:%M:%S') if u['created_at'] else None,
        'vip': vip_info,
    })
