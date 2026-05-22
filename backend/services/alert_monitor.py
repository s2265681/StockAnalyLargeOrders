"""股票条件预警监控服务，作为 eventlet greenlet 在交易时段轮询"""
import logging
from datetime import datetime, timedelta

from utils.db import execute_query, execute_write
from utils.alert_notify import send_stock_alert, queue_wechat_notification
from utils.stock_utils import calc_limit_price

logger = logging.getLogger(__name__)

POLL_INTERVAL_TRADING = 8    # 交易时段轮询间隔（秒）
POLL_INTERVAL_CLOSED = 60    # 非交易时段休眠间隔（秒）

# 内存状态，供 /api/alert-rules/monitor-status 接口读取
_status = {
    'running': False,
    'healthy': False,
    'sleeping': False,
    'last_check_at': None,
    'last_error': None,
}


def get_monitor_status() -> dict:
    return dict(_status)


def _is_trade_time() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 + 25 <= t <= 11 * 60 + 30) or (13 * 60 <= t <= 15 * 60)


def check_rule_condition(rule: dict, quote, limit_up_data: dict) -> bool:
    """纯函数：判断规则是否触发，不访问网络/DB"""
    if quote is None:
        return False

    alert_type = rule.get('alert_type')
    threshold = rule.get('threshold')
    direction = rule.get('direction')
    pct = quote.get('change_percent', 0) or 0

    if alert_type == 'change_pct':
        if threshold is None:
            return False
        return pct >= threshold if direction == 'above' else pct <= -threshold

    if alert_type == 'limit_up':
        return bool(limit_up_data.get('is_limit_up', False))

    if alert_type == 'limit_down':
        yesterday_close = quote.get('yesterday_close', 0) or 0
        price = quote.get('price', 0) or 0
        code = rule.get('code', '')
        name = rule.get('stock_name', '')
        if yesterday_close > 0:
            limit_down_price = calc_limit_price(yesterday_close, code, name, 'down')
            return price <= limit_down_price + 0.01
        return pct <= -9.9

    if alert_type == 'seal_order':
        if not limit_up_data.get('is_limit_up', False):
            return False
        if not limit_up_data.get('seal_data_valid', False):
            return False
        if threshold is None:
            return False
        seal_lots = int(limit_up_data.get('seal_volume_lots', 0) or 0)
        if direction == 'above':
            return seal_lots >= threshold
        return seal_lots < threshold  # below（默认）

    return False


def _is_in_cooldown(rule: dict) -> bool:
    """判断规则是否在冷却期内（repeat_minutes > 0 时有效）"""
    repeat_minutes = rule.get('repeat_minutes') or 0
    if repeat_minutes <= 0:
        return False
    last_notified = rule.get('last_notified_at')
    if not last_notified:
        return False
    if isinstance(last_notified, str):
        last_notified = datetime.fromisoformat(last_notified)
    return datetime.now() < last_notified + timedelta(minutes=repeat_minutes)


def _get_active_rules() -> list:
    return execute_query(
        "SELECT id, user_id, code, stock_name, alert_type, threshold, direction, email, "
        "repeat_minutes, last_notified_at "
        "FROM alert_rules WHERE status = 'active'",
        ()
    )


def _mark_triggered(rule_id: int) -> None:
    """一次性规则：标记为已触发"""
    execute_write(
        "UPDATE alert_rules SET status = 'triggered', triggered_at = NOW(), last_notified_at = NOW() WHERE id = %s",
        (rule_id,)
    )


def _mark_notified(rule_id: int) -> None:
    """重复规则：仅更新最近通知时间，保持 active 状态"""
    execute_write(
        "UPDATE alert_rules SET last_notified_at = NOW(), triggered_at = NOW() WHERE id = %s",
        (rule_id,)
    )


def _push_rule_triggered(socketio, rule: dict) -> None:
    """通过 WebSocket 通知对应用户刷新预警列表"""
    user_id = rule.get('user_id')
    if not socketio or not user_id:
        return
    try:
        socketio.emit('alert_rule_triggered', {
            'rule_id': rule['id'],
            'code': rule['code'],
            'stock_name': rule.get('stock_name') or '',
            'alert_type': rule['alert_type'],
        }, room=f'alert_user_{user_id}')
    except Exception as e:
        logger.warning("预警 WebSocket 推送失败 rule_id=%s: %s", rule.get('id'), e)


def _run_check_cycle(adapter, socketio=None) -> None:
    """执行一轮预警检查"""
    rules = _get_active_rules()
    if not rules:
        return

    by_code: dict = {}
    for rule in rules:
        by_code.setdefault(rule['code'], []).append(rule)

    for code, code_rules in by_code.items():
        try:
            quote = adapter.source.get_realtime_quote(code)
            if not quote:
                continue

            needs_seal = any(r['alert_type'] == 'seal_order' for r in code_rules)
            if needs_seal and hasattr(adapter.source, 'get_order_book'):
                order_book = adapter.source.get_order_book(code)
            else:
                order_book = {}
            limit_up_data = adapter.limit_up_monitor.analyze(
                code, quote, order_book, lightweight=not needs_seal,
            )

            for rule in code_rules:
                if not check_rule_condition(rule, quote, limit_up_data):
                    continue
                if _is_in_cooldown(rule):
                    continue

                send_stock_alert(rule, quote, limit_up_data, to_email=rule['email'])
                queue_wechat_notification(rule, quote, limit_up_data)
                logger.info("预警触发: rule_id=%s code=%s type=%s -> %s",
                            rule['id'], code, rule['alert_type'], rule['email'])

                repeat_minutes = rule.get('repeat_minutes') or 0
                if repeat_minutes > 0:
                    _mark_notified(rule['id'])
                else:
                    _mark_triggered(rule['id'])

                _push_rule_triggered(socketio, rule)
        except Exception as e:
            logger.error("预警检查失败 code=%s: %s", code, e)


def start_alert_monitor(socketio, adapter) -> None:
    """在 Flask-SocketIO eventlet 上下文中启动预警监控 greenlet"""

    def _monitor_loop():
        _status['running'] = True
        _status['healthy'] = True
        logger.info("预警监控服务已启动")
        while True:
            try:
                if _is_trade_time():
                    _status['sleeping'] = False
                    _run_check_cycle(adapter, socketio)
                    _status['healthy'] = True
                    _status['last_check_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    _status['last_error'] = None
                    socketio.sleep(POLL_INTERVAL_TRADING)
                else:
                    _status['sleeping'] = True
                    socketio.sleep(POLL_INTERVAL_CLOSED)
            except Exception as e:
                _status['healthy'] = False
                _status['last_error'] = str(e)
                logger.error("预警监控循环异常: %s", e)
                socketio.sleep(10)

    socketio.start_background_task(_monitor_loop)
    logger.info("预警监控任务已提交")
