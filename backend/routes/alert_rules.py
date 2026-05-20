"""条件预警规则管理 API"""
import logging
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query, execute_write, execute_insert
from utils.auth_middleware import login_required
from utils.stock_utils import get_stock_name_by_code

logger = logging.getLogger(__name__)

alert_rules_bp = Blueprint('alert_rules', __name__)

VALID_ALERT_TYPES = {'change_pct', 'limit_up', 'limit_down', 'seal_order'}
TYPES_WITH_THRESHOLD = {'change_pct', 'seal_order'}

MAX_ACTIVE_RULES_PER_USER = 20  # 每用户最多同时 active 的规则数


@alert_rules_bp.route('/api/alert-rules', methods=['GET'])
@login_required
def list_rules():
    user_id = request.current_user['user_id']
    rows = execute_query(
        "SELECT id, code, stock_name, alert_type, threshold, direction, email, "
        "status, triggered_at, created_at FROM alert_rules "
        "WHERE user_id = %s ORDER BY created_at DESC",
        (user_id,)
    )
    items = []
    for r in rows:
        items.append({
            'id': r['id'],
            'code': r['code'],
            'stock_name': r['stock_name'],
            'alert_type': r['alert_type'],
            'threshold': r['threshold'],
            'direction': r['direction'],
            'email': r['email'],
            'status': r['status'],
            'triggered_at': r['triggered_at'].strftime('%Y-%m-%d %H:%M:%S') if r['triggered_at'] else None,
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else None,
        })
    return v1_success_response(data={'items': items})


@alert_rules_bp.route('/api/alert-rules/batch', methods=['POST'])
@login_required
def batch_create_rules():
    user_id = request.current_user['user_id']
    body = request.get_json(silent=True) or {}
    rules = body.get('rules', [])

    if not rules:
        return v1_error_response('规则列表不能为空')
    if len(rules) > 3:
        return v1_error_response('一次最多添加3条规则')

    active_count = execute_query(
        "SELECT COUNT(*) AS cnt FROM alert_rules WHERE user_id = %s AND status = 'active'",
        (user_id,)
    )[0]['cnt']
    if active_count + len(rules) > MAX_ACTIVE_RULES_PER_USER:
        remaining = MAX_ACTIVE_RULES_PER_USER - active_count
        return v1_error_response(
            f"监控中规则已达上限（{MAX_ACTIVE_RULES_PER_USER} 条），"
            f"当前还可新增 {max(remaining, 0)} 条，请先停用或删除部分规则"
        )

    for rule in rules:
        if not rule.get('code', '').strip():
            return v1_error_response('股票代码不能为空')
        if rule.get('alert_type') not in VALID_ALERT_TYPES:
            return v1_error_response(f"预警类型无效: {rule.get('alert_type')}")
        if not rule.get('email', '').strip():
            return v1_error_response('收件邮箱不能为空')
        if rule.get('alert_type') in TYPES_WITH_THRESHOLD and rule.get('threshold') is None:
            return v1_error_response(f"{rule.get('alert_type')} 类型需要设置阈值")

    created_ids = []
    for rule in rules:
        code = rule['code'].strip().zfill(6)
        stock_name = get_stock_name_by_code(code) or ''
        new_id = execute_insert(
            "INSERT INTO alert_rules (user_id, code, stock_name, alert_type, threshold, direction, email) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, code, stock_name, rule['alert_type'],
             rule.get('threshold'), rule.get('direction'), rule['email'].strip())
        )
        created_ids.append(new_id)

    return v1_success_response(data={'created_ids': created_ids},
                               message=f'成功创建 {len(created_ids)} 条规则')


@alert_rules_bp.route('/api/alert-rules/monitor-status', methods=['GET'])
@login_required
def monitor_status():
    from services.alert_monitor import get_monitor_status
    s = get_monitor_status()
    now = __import__('datetime').datetime.now()

    seconds_since_check = None
    if s['last_check_at']:
        last_dt = __import__('datetime').datetime.strptime(s['last_check_at'], '%Y-%m-%d %H:%M:%S')
        seconds_since_check = int((now - last_dt).total_seconds())

    if not s['running']:
        display = 'stopped'
    elif s['sleeping']:
        display = 'sleeping'
    elif not s['healthy']:
        display = 'error'
    elif seconds_since_check is not None and seconds_since_check > 120:
        display = 'error'
    else:
        display = 'running'

    return v1_success_response(data={
        'display': display,
        'healthy': s['healthy'],
        'sleeping': s['sleeping'],
        'last_check_at': s['last_check_at'],
        'seconds_since_check': seconds_since_check,
        'last_error': s['last_error'],
    })


@alert_rules_bp.route('/api/alert-rules/<int:rule_id>', methods=['PUT'])
@login_required
def update_rule(rule_id):
    user_id = request.current_user['user_id']
    existing = execute_query("SELECT user_id FROM alert_rules WHERE id = %s", (rule_id,))
    if not existing or existing[0]['user_id'] != user_id:
        return v1_error_response('规则不存在或无权限')

    body = request.get_json(silent=True) or {}
    email = body.get('email', '').strip()
    if not email:
        return v1_error_response('收件邮箱不能为空')

    execute_write(
        "UPDATE alert_rules SET threshold = %s, direction = %s, email = %s WHERE id = %s",
        (body.get('threshold'), body.get('direction'), email, rule_id)
    )
    return v1_success_response(message='更新成功')


@alert_rules_bp.route('/api/alert-rules/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_rule(rule_id):
    user_id = request.current_user['user_id']
    existing = execute_query("SELECT user_id FROM alert_rules WHERE id = %s", (rule_id,))
    if not existing or existing[0]['user_id'] != user_id:
        return v1_error_response('规则不存在或无权限')

    execute_write("DELETE FROM alert_rules WHERE id = %s", (rule_id,))
    return v1_success_response(message='删除成功')


@alert_rules_bp.route('/api/alert-rules/<int:rule_id>/reactivate', methods=['POST'])
@login_required
def reactivate_rule(rule_id):
    user_id = request.current_user['user_id']
    existing = execute_query("SELECT user_id FROM alert_rules WHERE id = %s", (rule_id,))
    if not existing or existing[0]['user_id'] != user_id:
        return v1_error_response('规则不存在或无权限')

    execute_write(
        "UPDATE alert_rules SET status = 'active', triggered_at = NULL WHERE id = %s",
        (rule_id,)
    )
    return v1_success_response(message='已重新激活')


@alert_rules_bp.route('/api/alert-rules/<int:rule_id>/disable', methods=['POST'])
@login_required
def disable_rule(rule_id):
    user_id = request.current_user['user_id']
    existing = execute_query("SELECT user_id FROM alert_rules WHERE id = %s", (rule_id,))
    if not existing or existing[0]['user_id'] != user_id:
        return v1_error_response('规则不存在或无权限')

    execute_write(
        "UPDATE alert_rules SET status = 'disabled' WHERE id = %s",
        (rule_id,)
    )
    return v1_success_response(message='已停用')
