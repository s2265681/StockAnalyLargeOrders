"""股票条件预警监控服务，作为 eventlet greenlet 在交易时段每 3 秒轮询"""
import logging
from datetime import datetime

from utils.db import execute_query, execute_write
from utils.alert_notify import send_stock_alert

logger = logging.getLogger(__name__)

POLL_INTERVAL_TRADING = 3    # 交易时段轮询间隔（秒）
POLL_INTERVAL_CLOSED = 60    # 非交易时段休眠间隔（秒）


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
        if yesterday_close > 0:
            limit_down_price = round(yesterday_close * 0.9, 2)
            return price <= limit_down_price + 0.01
        return pct <= -9.9

    if alert_type == 'seal_order':
        if not limit_up_data.get('is_limit_up', False):
            return False
        seal_amount = limit_up_data.get('seal_amount', 0) or 0
        return threshold is not None and seal_amount < threshold

    return False


def _get_active_rules() -> list:
    return execute_query(
        "SELECT id, user_id, code, stock_name, alert_type, threshold, direction, email "
        "FROM alert_rules WHERE status = 'active'",
        ()
    )


def _mark_triggered(rule_id: int) -> None:
    execute_write(
        "UPDATE alert_rules SET status = 'triggered', triggered_at = NOW() WHERE id = %s",
        (rule_id,)
    )


def _run_check_cycle(adapter) -> None:
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

            order_book = (adapter.source.get_order_book(code)
                          if hasattr(adapter.source, 'get_order_book') else {})
            limit_up_data = adapter.limit_up_monitor.analyze(code, quote, order_book)

            for rule in code_rules:
                if check_rule_condition(rule, quote, limit_up_data):
                    send_stock_alert(rule, quote, limit_up_data, to_email=rule['email'])
                    logger.info("预警触发: rule_id=%s code=%s type=%s -> %s",
                                rule['id'], code, rule['alert_type'], rule['email'])
                    _mark_triggered(rule['id'])
        except Exception as e:
            logger.error("预警检查失败 code=%s: %s", code, e)


def start_alert_monitor(socketio, adapter) -> None:
    """在 Flask-SocketIO eventlet 上下文中启动预警监控 greenlet"""

    def _monitor_loop():
        logger.info("预警监控服务已启动")
        while True:
            try:
                if _is_trade_time():
                    _run_check_cycle(adapter)
                    socketio.sleep(POLL_INTERVAL_TRADING)
                else:
                    socketio.sleep(POLL_INTERVAL_CLOSED)
            except Exception as e:
                logger.error("预警监控循环异常: %s", e)
                socketio.sleep(10)

    socketio.start_background_task(_monitor_loop)
    logger.info("预警监控任务已提交")
