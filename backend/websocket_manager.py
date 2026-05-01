"""
WebSocket 管理器
使用 Flask-SocketIO 管理客户端订阅和定时推送 L2 数据
"""
import logging
from datetime import datetime

from flask import request
from flask_socketio import emit, join_room, leave_room

from services.data_source_adapter import DataSourceAdapter

logger = logging.getLogger(__name__)

# 模块级状态
_subscriptions = {}   # sid -> {code, room}
_active_rooms = set() # 当前有订阅者的房间名

PUSH_INTERVAL = 3  # 推送间隔（秒）

# 共享适配器实例
adapter = DataSourceAdapter(use_l2=False)


def is_trade_time() -> bool:
    """判断当前是否处于交易时段（周一至周五 09:30-11:30 或 13:00-15:00）"""
    now = datetime.now()
    # 0=周一 ... 4=周五
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    morning = (9 * 60 + 30 <= t <= 11 * 60 + 30)
    afternoon = (13 * 60 <= t <= 15 * 60)
    return morning or afternoon


def register_websocket_events(socketio):
    """注册 WebSocket 事件处理器"""

    @socketio.on('connect')
    def handle_connect():
        sid = request.sid
        logger.info(f"客户端已连接: {sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        sid = request.sid
        if sid in _subscriptions:
            info = _subscriptions.pop(sid)
            room = info['room']
            leave_room(room)
            # 若该房间已无订阅者则从活跃房间集合移除
            if not any(v['room'] == room for v in _subscriptions.values()):
                _active_rooms.discard(room)
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
            # 若旧房间无其他订阅者则移除
            if not any(v['room'] == old_room for k, v in _subscriptions.items() if k != sid):
                _active_rooms.discard(old_room)

        room = f'stock_{code}'
        join_room(room)
        _subscriptions[sid] = {'code': code, 'room': room}
        _active_rooms.add(room)
        logger.info(f"客户端 {sid} 订阅股票: {code}，加入房间: {room}")

        # 立即推送一次数据给该客户端
        try:
            result = adapter.get_l2_dashboard(code)
            emit('l2_update', result)
        except Exception as e:
            logger.error(f"立即推送失败 code={code}: {e}")
            emit('error', {'message': str(e)})

    @socketio.on('unsubscribe')
    def handle_unsubscribe(data):
        sid = request.sid
        if sid in _subscriptions:
            info = _subscriptions.pop(sid)
            room = info['room']
            leave_room(room)
            if not any(v['room'] == room for v in _subscriptions.values()):
                _active_rooms.discard(room)
            logger.info(f"客户端 {sid} 取消订阅，离开房间: {room}")


def start_push_loop(socketio):
    """启动后台定时推送循环"""

    def _push_loop():
        logger.info("WebSocket 推送循环已启动")
        while True:
            socketio.sleep(PUSH_INTERVAL)

            if not _active_rooms:
                continue

            if not is_trade_time():
                continue

            for room in list(_active_rooms):
                # 从房间名称解析股票代码
                if not room.startswith('stock_'):
                    continue
                code = room[len('stock_'):]
                try:
                    result = adapter.get_l2_dashboard(code)
                    socketio.emit('l2_update', result, room=room)
                except Exception as e:
                    logger.error(f"推送失败 room={room} code={code}: {e}")
                    socketio.emit('error', {'message': str(e)}, room=room)

    socketio.start_background_task(_push_loop)
    logger.info("WebSocket 后台推送任务已提交")
