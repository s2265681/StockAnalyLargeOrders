"""订单管理 API"""
import logging
import random
from datetime import datetime, timedelta
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query, execute_write
from utils.auth_middleware import login_required

logger = logging.getLogger(__name__)

orders_bp = Blueprint('orders', __name__)

PLANS = {
    'daily':     {'name': '日度VIP',  'amount': 0.01,   'days': 1},
    'monthly':   {'name': '月度VIP',  'amount': 380.00, 'days': 30},
    'quarterly': {'name': '季度VIP',  'amount': 900.00, 'days': 90},
    'semi':      {'name': '半年VIP',  'amount': 1600.00, 'days': 180},
    'annual':    {'name': '年度VIP',  'amount': 2500.00, 'days': 365},
}


def _gen_order_no():
    now = datetime.now().strftime('%Y%m%d%H%M%S')
    rand = f'{random.randint(0, 999999):06d}'
    return f'NN{now}{rand}'


@orders_bp.route('/api/orders', methods=['GET'])
@login_required
def list_orders():
    user_id = request.current_user['user_id']
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    offset = (page - 1) * page_size

    total_row = execute_query('SELECT COUNT(*) as cnt FROM orders WHERE user_id = %s', (user_id,))
    total = total_row[0]['cnt'] if total_row else 0

    rows = execute_query(
        'SELECT order_no, plan_type, amount, status, created_at '
        'FROM orders WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s',
        (user_id, page_size, offset)
    )
    items = []
    for r in rows:
        plan = PLANS.get(r['plan_type'], {})
        items.append({
            'order_no': r['order_no'],
            'plan_name': plan.get('name', r['plan_type']),
            'plan_type': r['plan_type'],
            'amount': float(r['amount']),
            'status': r['status'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M') if r['created_at'] else None,
        })

    return v1_success_response(data={
        'items': items, 'total': total, 'page': page, 'page_size': page_size,
    })


@orders_bp.route('/api/orders/create', methods=['POST'])
@login_required
def create_order():
    body = request.get_json(silent=True) or {}
    plan_type = body.get('plan_type', '')
    user_id = request.current_user['user_id']

    if plan_type not in PLANS:
        return v1_error_response('无效的套餐类型')

    plan = PLANS[plan_type]
    order_no = _gen_order_no()

    execute_write(
        'INSERT INTO orders (order_no, user_id, plan_type, amount, status) VALUES (%s, %s, %s, %s, %s)',
        (order_no, user_id, plan_type, plan['amount'], 'pending')
    )

    return v1_success_response(data={
        'order_no': order_no, 'plan_name': plan['name'], 'amount': plan['amount'],
    }, message='订单创建成功')


@orders_bp.route('/api/orders/mock-pay', methods=['POST'])
@login_required
def mock_pay():
    body = request.get_json(silent=True) or {}
    order_no = body.get('order_no', '')
    user_id = request.current_user['user_id']

    if not order_no:
        return v1_error_response('缺少订单号')

    order = execute_query(
        'SELECT id, plan_type, status FROM orders WHERE order_no = %s AND user_id = %s',
        (order_no, user_id)
    )
    if not order:
        return v1_error_response('订单不存在')
    if order[0]['status'] == 'paid':
        return v1_error_response('订单已支付')

    plan_type = order[0]['plan_type']
    plan = PLANS.get(plan_type, PLANS['daily'])

    execute_write('UPDATE orders SET status = %s WHERE order_no = %s', ('paid', order_no))

    now = datetime.now()
    existing_sub = execute_query(
        'SELECT id, end_time FROM user_subscriptions '
        'WHERE user_id = %s AND is_active = 1 AND end_time > NOW() '
        'ORDER BY end_time DESC LIMIT 1',
        (user_id,)
    )
    if existing_sub:
        start = existing_sub[0]['end_time']
        end = start + timedelta(days=plan['days'])
        execute_write(
            'UPDATE user_subscriptions SET end_time = %s, plan_type = %s WHERE id = %s',
            (end, plan_type, existing_sub[0]['id'])
        )
    else:
        end = now + timedelta(days=plan['days'])
        execute_write(
            'INSERT INTO user_subscriptions (user_id, plan_type, start_time, end_time) VALUES (%s, %s, %s, %s)',
            (user_id, plan_type, now, end)
        )

    return v1_success_response(message='支付成功，VIP 已激活')
