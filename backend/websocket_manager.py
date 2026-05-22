"""
WebSocket 管理器
使用 Flask-SocketIO 管理客户端订阅和数据推送。

实时推送策略：
  - 交易时间：使用 LiveFeedManager 订阅东财 SSE 流，有新帧 (~1秒) 立即推送
  - 非交易时间：LiveFeed 停止，回退到 30 秒轮询（健康检查用）
  - 客户端订阅/取消时自动管理 LiveFeed 生命周期
"""
import logging
from datetime import datetime

from flask import request
from flask_socketio import emit, join_room, leave_room

from utils.auth_middleware import decode_token
from services.data_source_adapter import DataSourceAdapter
from services.eastmoney_playwright import LiveFeedManager, EastMoneyPlaywrightSource

logger = logging.getLogger(__name__)

# 模块级状态
_subscriptions = {}    # sid -> {code, room}
_alert_rooms = {}      # sid -> alert_user_{id} 房间
_active_rooms = set()  # 当前有订阅者的房间名
ALERT_MONITOR_ROOM = 'alert_monitor'

POLL_INTERVAL_TRADING = 8    # 交易时间轮询间隔（秒），LiveFeed 的保底
POLL_INTERVAL_CLOSED = 30    # 非交易时间轮询间隔（秒）

# 共享实例
adapter = DataSourceAdapter(use_l2=False)
live_feed = LiveFeedManager()


def is_trade_time() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 + 30 <= t <= 11 * 60 + 30) or (13 * 60 <= t <= 15 * 60)


def _make_callback(socketio_ref):
    """生成 LiveFeed 回调闭包，收到新 SSE 帧后构建完整看板并推送"""
    def _callback(code: str, _raw_data: dict):
        room = f'stock_{code}'
        if room not in _active_rooms:
            return
        try:
            # _raw_data 已由 LiveFeedManager 写入 Playwright 缓存
            # adapter.get_l2_dashboard 会直接命中缓存（0ms），只做数据加工
            result = adapter.get_l2_dashboard(code)
            socketio_ref.emit('l2_update', result, room=room)
            logger.debug(f"LiveFeed 推送 {code}: {len(result.get('data', {}).get('large_orders', []))} 大单")
        except Exception as e:
            logger.error(f"LiveFeed 推送失败 {code}: {e}")
    return _callback


def register_websocket_events(socketio):
    """注册 WebSocket 事件处理器"""

    @socketio.on('connect')
    def handle_connect(auth=None):
        sid = request.sid
        token = (auth or {}).get('token')
        if token:
            payload = decode_token(token)
            if payload and payload.get('user_id'):
                room = f"alert_user_{payload['user_id']}"
                join_room(room)
                _alert_rooms[sid] = room
                join_room(ALERT_MONITOR_ROOM)
                logger.info(f"客户端 {sid} 加入预警房间: {room}")
                try:
                    from services.alert_monitor import build_monitor_status_payload
                    emit('alert_monitor_status', build_monitor_status_payload())
                except Exception as e:
                    logger.warning(f"推送监控状态失败 sid={sid}: {e}")
        logger.info(f"客户端已连接: {sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        sid = request.sid
        if sid in _alert_rooms:
            leave_room(_alert_rooms.pop(sid))
            leave_room(ALERT_MONITOR_ROOM)
        if sid in _subscriptions:
            info = _subscriptions.pop(sid)
            room = info['room']
            leave_room(room)
            code = info['code']
            # 若该房间已无订阅者，移除房间并停止对应 LiveFeed
            if not any(v['room'] == room for v in _subscriptions.values()):
                _active_rooms.discard(room)
                live_feed.unsubscribe(code)
                logger.info(f"房间 {room} 无订阅者，LiveFeed 已停止")
            logger.info(f"客户端已断开: {sid}，离开房间: {room}")
        else:
            logger.info(f"客户端已断开: {sid}")

    @socketio.on('subscribe')
    def handle_subscribe(data):
        sid = request.sid
        code = data.get('code', '').strip()
        if not code:
            emit('error', {'message': '股票代码不能为空'})
            return

        # 若之前已订阅其他股票，先离开旧房间
        if sid in _subscriptions:
            old_info = _subscriptions[sid]
            old_room = old_info['room']
            leave_room(old_room)
            if not any(v['room'] == old_room for k, v in _subscriptions.items() if k != sid):
                _active_rooms.discard(old_room)
                live_feed.unsubscribe(old_info['code'])

        room = f'stock_{code}'
        join_room(room)
        _subscriptions[sid] = {'code': code, 'room': room}
        _active_rooms.add(room)
        logger.info(f"客户端 {sid} 订阅: {code}")

        # 立即推送一次数据
        try:
            result = adapter.get_l2_dashboard(code)
            emit('l2_update', result)
        except Exception as e:
            logger.error(f"立即推送失败 code={code}: {e}")
            emit('error', {'message': str(e)})

        # 交易时间：启动 LiveFeed（已启动则忽略）
        if is_trade_time() and code not in live_feed.active_codes:
            live_feed.subscribe(code, _make_callback(socketio))
            logger.info(f"LiveFeed 订阅: {code}")

    @socketio.on('unsubscribe')
    def handle_unsubscribe(data):
        sid = request.sid
        if sid in _subscriptions:
            info = _subscriptions.pop(sid)
            room = info['room']
            leave_room(room)
            if not any(v['room'] == room for v in _subscriptions.values()):
                _active_rooms.discard(room)
                live_feed.unsubscribe(info['code'])
            logger.info(f"客户端 {sid} 取消订阅")


def start_push_loop(socketio):
    """启动后台任务：管理 LiveFeed 生命周期 + 轮询推送"""

    def _manage_loop():
        logger.info("WebSocket 管理循环已启动")
        while True:
            trading = is_trade_time()
            socketio.sleep(POLL_INTERVAL_TRADING if trading else POLL_INTERVAL_CLOSED)

            if not _active_rooms:
                continue

            for room in list(_active_rooms):
                if not room.startswith('stock_'):
                    continue
                code = room[len('stock_'):]

                if trading:
                    # 交易时间：确保 LiveFeed 在运行 + 主动轮询推送（LiveFeed 的保底）
                    if code not in live_feed.active_codes:
                        live_feed.subscribe(code, _make_callback(socketio))
                        logger.info(f"管理循环补启 LiveFeed: {code}")
                    try:
                        result = adapter.get_l2_dashboard(code)
                        socketio.emit('l2_update', result, room=room)
                    except Exception as e:
                        logger.error(f"交易时间推送失败 {code}: {e}")
                else:
                    # 非交易时间：停止 LiveFeed，低频轮询
                    if code in live_feed.active_codes:
                        live_feed.unsubscribe(code)
                    try:
                        result = adapter.get_l2_dashboard(code)
                        socketio.emit('l2_update', result, room=room)
                    except Exception as e:
                        logger.error(f"回退轮询失败 {code}: {e}")

    socketio.start_background_task(_manage_loop)
    logger.info("WebSocket 管理任务已提交")
