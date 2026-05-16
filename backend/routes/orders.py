# backend/routes/orders.py
import time
import datetime
import random
import string
from flask import Blueprint, request, jsonify
from utils.db import execute_query, execute_write
from utils.auth_middleware import require_auth

orders_bp = Blueprint('orders', __name__)

PLANS = {
    'monthly':   {'name': '月度VIP',  'amount': 380.00, 'days': 30},
    'quarterly': {'name': '季度VIP',  'amount': 900.00, 'days': 90},
    'semi':      {'name': '半年VIP',  'amount': 1600.00, 'days': 180},
    'annual':    {'name': '年度VIP',  'amount': 2500.00, 'days': 365},
    'daily':     {'name': '日度VIP',  'amount': 0.01,   'days': 1},
}


def _gen_order_no():
    """生成26位唯一订单号：毫秒时间戳13位 + 随机数字13位"""
    ts = str(int(time.time() * 1000))
    rand = ''.join(random.choices(string.digits, k=13))
    return (ts + rand)[:26]


@orders_bp.route('/api/orders', methods=['GET'])
@require_auth
def list_orders():
    user_id = request.current_user['user_id']
    page = max(1, int(request.args.get('page', 1)))
    page_size = max(1, min(100, int(request.args.get('page_size', 10))))
    offset = (page - 1) * page_size

    total_rows = execute_query(
        'SELECT COUNT(*) AS cnt FROM orders WHERE user_id=%s', (user_id,)
    )
    total = total_rows[0]['cnt'] if total_rows else 0

    rows = execute_query(
        'SELECT id, order_no, plan_type, amount, status, created_at '
        'FROM orders WHERE user_id=%s ORDER BY created_at DESC LIMIT %s OFFSET %s',
        (user_id, page_size, offset)
    )

    def fmt_row(r):
        plan = PLANS.get(r['plan_type'], {})
        return {
            'id': r['id'],
            'order_no': r['order_no'],
            'plan_name': plan.get('name', r['plan_type']),
            'amount': float(r['amount']),
            'status': r['status'],
            'created_at': (
                r['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                if hasattr(r['created_at'], 'strftime')
                else str(r['created_at'])
            ),
        }

    return jsonify({
        'success': True,
        'data': {
            'list': [fmt_row(r) for r in rows],
            'total': total,
            'page': page,
            'page_size': page_size,
        }
    })


@orders_bp.route('/api/orders/create', methods=['POST'])
@require_auth
def create_order():
    data = request.get_json(silent=True) or {}
    plan_type = data.get('plan_type', '')
    if plan_type not in PLANS:
        return jsonify({'success': False, 'message': '无效的套餐类型'}), 400

    user_id = request.current_user['user_id']
    plan = PLANS[plan_type]
    order_no = _gen_order_no()

    execute_write(
        'INSERT INTO orders (order_no, user_id, plan_type, amount, status) '
        'VALUES (%s,%s,%s,%s,"pending")',
        (order_no, user_id, plan_type, plan['amount'])
    )
    return jsonify({
        'success': True,
        'data': {
            'order_no': order_no,
            'plan_name': plan['name'],
            'amount': plan['amount'],
        }
    })


@orders_bp.route('/api/orders/mock-pay', methods=['POST'])
@require_auth
def mock_pay():
    """测试用：直接激活会员（Mock支付，不走真实支付渠道）"""
    data = request.get_json(silent=True) or {}
    order_no = data.get('order_no', '')
    if not order_no:
        return jsonify({'success': False, 'message': '订单号不能为空'}), 400

    user_id = request.current_user['user_id']

    rows = execute_query(
        'SELECT id, plan_type FROM orders WHERE order_no=%s AND user_id=%s',
        (order_no, user_id)
    )
    if not rows:
        return jsonify({'success': False, 'message': '订单不存在'}), 404

    order = rows[0]
    plan = PLANS.get(order['plan_type'], {'days': 1})

    # 更新订单为已支付
    execute_write('UPDATE orders SET status="paid" WHERE order_no=%s', (order_no,))

    # 激活/续费订阅
    now = datetime.datetime.now()
    existing = execute_query(
        'SELECT id, end_time FROM user_subscriptions '
        'WHERE user_id=%s AND is_active=1 AND end_time > NOW()',
        (user_id,)
    )
    if existing:
        base_time = existing[0]['end_time']
        end_time = base_time + datetime.timedelta(days=plan['days'])
        execute_write(
            'UPDATE user_subscriptions SET end_time=%s, plan_type=%s WHERE id=%s',
            (end_time, order['plan_type'], existing[0]['id'])
        )
    else:
        end_time = now + datetime.timedelta(days=plan['days'])
        execute_write(
            'INSERT INTO user_subscriptions (user_id, plan_type, start_time, end_time, is_active) '
            'VALUES (%s,%s,%s,%s,1)',
            (user_id, order['plan_type'], now, end_time)
        )

    expire_str = end_time.strftime('%Y/%m/%d %H:%M:%S')
    return jsonify({
        'success': True,
        'message': f'支付成功！会员有效期至 {expire_str}',
        'data': {'expire_time': expire_str}
    })
