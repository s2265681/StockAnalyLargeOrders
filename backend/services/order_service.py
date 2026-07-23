"""订单与 VIP 订阅业务逻辑"""
import logging
from datetime import datetime, timedelta
from utils.db import execute_query, execute_write

logger = logging.getLogger(__name__)

PLANS = {
    # 测试阶段：微信支付最低 0.01 元（1 分）
    'daily':     {'name': '测试VIP 1分', 'amount': 0.01, 'days': 1},
    'test2':     {'name': '测试VIP 2分', 'amount': 0.02, 'days': 1},
    # 正式上线价格（测试完成后恢复展示）
    'monthly':   {'name': '月度VIP',  'amount': 380.00, 'days': 30},
    'quarterly': {'name': '季度VIP',  'amount': 900.00, 'days': 90},
    'semi':      {'name': '半年VIP',  'amount': 1600.00, 'days': 180},
    'annual':    {'name': '年度VIP',  'amount': 2500.00, 'days': 365},
}


def get_plan(plan_type):
    return PLANS.get(plan_type)


def activate_subscription(user_id, plan_type):
    """支付成功后延长或创建 VIP 订阅。"""
    plan = PLANS.get(plan_type, PLANS['daily'])
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
    logger.info('VIP activated user_id=%s plan=%s', user_id, plan_type)


def mark_order_paid(order_no, payment_channel, transaction_id=None):
    """
    将订单标记为已支付并激活 VIP。
    幂等：已支付订单直接返回 True。
    """
    order_rows = execute_query(
        'SELECT id, user_id, plan_type, status FROM orders WHERE order_no = %s',
        (order_no,)
    )
    if not order_rows:
        logger.warning('mark_order_paid: order not found %s', order_no)
        return False

    order = order_rows[0]
    if order['status'] == 'paid':
        return True

    execute_write(
        'UPDATE orders SET status = %s, payment_channel = %s, transaction_id = %s, paid_at = %s '
        'WHERE order_no = %s AND status = %s',
        ('paid', payment_channel, transaction_id, datetime.now(), order_no, 'pending')
    )
    activate_subscription(order['user_id'], order['plan_type'])
    return True
