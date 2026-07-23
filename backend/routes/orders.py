"""订单管理 API"""
import logging
import random
from datetime import datetime
from flask import Blueprint, request, jsonify
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query, execute_write
from utils.auth_middleware import login_required
from services.order_service import PLANS, get_plan, mark_order_paid
from config.wechat_pay import get_wechat_pay_config
from utils.wechat_pay_client import get_wechat_pay_client, is_wechat_pay_enabled, WeChatPayError

logger = logging.getLogger(__name__)

orders_bp = Blueprint('orders', __name__)


def _gen_order_no():
    now = datetime.now().strftime('%Y%m%d%H%M%S')
    rand = f'{random.randint(0, 999999):06d}'
    return f'NN{now}{rand}'


@orders_bp.route('/api/orders/payment-config', methods=['GET'])
def payment_config():
    config = get_wechat_pay_config()
    return v1_success_response(data={
        'wechat_enabled': config['enabled'],
        'mock_enabled': not config['enabled'],
    })


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
        'SELECT order_no, plan_type, amount, status, payment_channel, paid_at, created_at '
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
            'payment_channel': r.get('payment_channel'),
            'paid_at': r['paid_at'].strftime('%Y-%m-%d %H:%M') if r.get('paid_at') else None,
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


@orders_bp.route('/api/orders/wechat-prepay', methods=['POST'])
@login_required
def wechat_prepay():
    if not is_wechat_pay_enabled():
        return v1_error_response('微信支付未配置，请联系管理员')

    body = request.get_json(silent=True) or {}
    order_no = body.get('order_no', '')
    user_id = request.current_user['user_id']

    if not order_no:
        return v1_error_response('缺少订单号')

    order_rows = execute_query(
        'SELECT plan_type, amount, status FROM orders WHERE order_no = %s AND user_id = %s',
        (order_no, user_id)
    )
    if not order_rows:
        return v1_error_response('订单不存在')
    order = order_rows[0]
    if order['status'] == 'paid':
        return v1_error_response('订单已支付')

    plan = get_plan(order['plan_type']) or PLANS['daily']
    client = get_wechat_pay_client()
    try:
        code_url = client.create_native_order(
            order_no=order_no,
            description=f'牛牛股票分析 - {plan["name"]}',
            amount_yuan=order['amount'],
        )
    except WeChatPayError as exc:
        logger.exception('WeChat prepay failed order=%s', order_no)
        return v1_error_response(f'创建支付失败: {exc}')

    return v1_success_response(data={
        'order_no': order_no,
        'code_url': code_url,
        'amount': float(order['amount']),
        'plan_name': plan['name'],
    })


@orders_bp.route('/api/orders/status', methods=['GET'])
@login_required
def order_status():
    order_no = request.args.get('order_no', '')
    user_id = request.current_user['user_id']

    if not order_no:
        return v1_error_response('缺少订单号')

    order_rows = execute_query(
        'SELECT status, plan_type, amount, payment_channel, paid_at FROM orders '
        'WHERE order_no = %s AND user_id = %s',
        (order_no, user_id)
    )
    if not order_rows:
        return v1_error_response('订单不存在')

    order = order_rows[0]
    if order['status'] == 'pending' and is_wechat_pay_enabled():
        client = get_wechat_pay_client()
        try:
            wx_order = client.query_order(order_no)
            if wx_order.get('trade_state') == 'SUCCESS':
                transaction_id = wx_order.get('transaction_id')
                mark_order_paid(order_no, 'wechat', transaction_id)
                order['status'] = 'paid'
                order['payment_channel'] = 'wechat'
                order['paid_at'] = datetime.now()
        except WeChatPayError:
            logger.debug('WeChat query pending for order=%s', order_no, exc_info=True)

    return v1_success_response(data={
        'order_no': order_no,
        'status': order['status'],
        'payment_channel': order.get('payment_channel'),
        'paid_at': order['paid_at'].strftime('%Y-%m-%d %H:%M:%S') if order.get('paid_at') else None,
    })


@orders_bp.route('/api/payments/wechat/notify', methods=['POST'])
def wechat_notify():
    if not is_wechat_pay_enabled():
        return jsonify({'code': 'FAIL', 'message': '微信支付未启用'}), 500

    body = request.get_data(as_text=True)
    client = get_wechat_pay_client()
    try:
        client.verify_notify_signature(request.headers, body)
        payload = request.get_json(silent=True) or {}
        resource = payload.get('resource') or {}
        data = client.decrypt_notify_resource(resource)
    except WeChatPayError as exc:
        logger.warning('WeChat notify verify failed: %s', exc)
        return jsonify({'code': 'FAIL', 'message': str(exc)}), 400

    if data.get('trade_state') != 'SUCCESS':
        return jsonify({'code': 'SUCCESS', 'message': '成功'})

    order_no = data.get('out_trade_no')
    transaction_id = data.get('transaction_id')
    if not order_no:
        return jsonify({'code': 'FAIL', 'message': '缺少订单号'}), 400

    mark_order_paid(order_no, 'wechat', transaction_id)
    return jsonify({'code': 'SUCCESS', 'message': '成功'})


@orders_bp.route('/api/orders/mock-pay', methods=['POST'])
@login_required
def mock_pay():
    if is_wechat_pay_enabled():
        return v1_error_response('生产环境请使用微信支付')

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

    mark_order_paid(order_no, 'mock', None)
    return v1_success_response(message='支付成功，VIP 已激活')
