# L2 看板优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 NiuNIuNiu 看盘系统增加封单监控、缓存优化、板块联动增强、WebSocket 实时推送四项功能。

**Architecture:** 后端新增 LimitUpMonitor 服务和 WebSocketManager，集成到现有 Flask 应用；前端新增 WebSocket 客户端服务，替代交易时间内的 HTTP 轮询。所有新数据通过现有 L2 Dashboard 统一接口传输。

**Tech Stack:** Flask-SocketIO + eventlet (后端 WebSocket)、socket.io-client (前端)、numpy (线性回归)

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 新增 | `backend/services/limit_up_monitor.py` | 封单监控：涨停检测、封单采样、炸板计数 |
| 新增 | `backend/websocket_manager.py` | WebSocket 连接管理、定时推送 |
| 新增 | `frontend/src/services/websocket.js` | 前端 WS 客户端封装 |
| 新增 | `frontend/src/pages/StockDashboard/components/LimitUpMonitorPanel.js` | 封单监控 UI 组件 |
| 修改 | `backend/requirements.txt` | 新增 flask-socketio、eventlet |
| 修改 | `backend/services/data_source_adapter.py` | 集成封单监控 + 缓存 TTL 调整 |
| 修改 | `backend/app.py` | 集成 SocketIO |
| 修改 | `backend/routes/stock_other.py` | 涨停题材联动增强 |
| 修改 | `frontend/package.json` | 新增 socket.io-client |
| 修改 | `frontend/src/store/atoms.js` | WS 状态 atom + L2 数据解析提取 |
| 修改 | `frontend/src/pages/StockDashboard/index.js` | WS 连接逻辑替代轮询 |
| 修改 | `frontend/src/pages/StockDashboard/components/StockBasicInfo.js` | 展示封单监控数据 |
| 修改 | `frontend/src/pages/StockDashboard/components/ThemeLimitUpPanel.js` | 联动度 + 市场情绪展示 |

---

### Task 1: 安装后端依赖

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 添加 flask-socketio 和 eventlet 到 requirements.txt**

在 `backend/requirements.txt` 末尾追加：

```
flask-socketio>=5.3.0
eventlet>=0.35.0
```

- [ ] **Step 2: 安装依赖**

Run: `cd /Users/mac/Github/NiuNIuNiu/backend && pip install flask-socketio eventlet`

- [ ] **Step 3: 提交**

```bash
git add backend/requirements.txt
git commit -m "chore: 添加flask-socketio和eventlet依赖"
```

---

### Task 2: 实现封单监控服务 (LimitUpMonitor)

**Files:**
- Create: `backend/services/limit_up_monitor.py`

- [ ] **Step 1: 创建 LimitUpMonitor 类**

```python
"""
封单监控服务
跟踪涨停股的封单量、封单变化趋势、炸板次数
"""
import logging
import time
from collections import deque
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)

# 流通市值缓存（日级别）
_float_market_cap_cache = {}


def _get_float_market_cap(code):
    """获取流通市值（元），日级别缓存"""
    today = datetime.now().strftime('%Y-%m-%d')
    cache_key = f'{code}_{today}'
    if cache_key in _float_market_cap_cache:
        return _float_market_cap_cache[cache_key]

    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=code)
        info = dict(zip(df['item'], df['value']))
        # 流通市值，单位：元
        cap = float(info.get('流通市值', 0) or 0)
        _float_market_cap_cache[cache_key] = cap
        return cap
    except Exception as e:
        logger.warning(f"获取流通市值失败({code}): {e}")
        return 0


class _StockLimitState:
    """单只股票的涨停跟踪状态"""

    def __init__(self):
        self.seal_samples = deque(maxlen=60)  # 最近60个采样点
        self.break_count = 0
        self.first_limit_time = None
        self.was_limit_up = False  # 上一次采样是否涨停


class LimitUpMonitor:
    """封单监控器（单例，跨请求保持状态）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._states = {}
            cls._instance._last_reset_date = None
        return cls._instance

    def _get_state(self, code):
        """获取/创建股票状态，每日自动重置"""
        today = datetime.now().strftime('%Y-%m-%d')
        if self._last_reset_date != today:
            self._states.clear()
            self._last_reset_date = today

        if code not in self._states:
            self._states[code] = _StockLimitState()
        return self._states[code]

    def analyze(self, code, quote, order_book):
        """
        分析封单状态

        Args:
            code: 股票代码
            quote: get_realtime_quote() 返回的 dict
            order_book: get_order_book() 返回的 dict

        Returns:
            dict: limit_up_monitor 数据
        """
        if not quote or not quote.get('yesterday_close'):
            return self._empty_result()

        yesterday_close = quote['yesterday_close']
        current_price = quote['price']

        # 涨停价计算（普通股10%，ST股5%）
        is_st = 'ST' in (quote.get('name') or '')
        limit_pct = 0.05 if is_st else 0.10
        limit_up_price = round(yesterday_close * (1 + limit_pct), 2)

        is_limit_up = abs(current_price - limit_up_price) < 0.005

        # 封单金额（万元）
        seal_amount = 0
        bids = order_book.get('bids', [])
        if is_limit_up and bids:
            bid1 = bids[0]
            if abs(bid1.get('price', 0) - limit_up_price) < 0.005:
                seal_amount = round(bid1.get('amount', 0) / 10000, 2)

        # 封单比（封单金额/流通市值）
        float_cap = _get_float_market_cap(code)
        seal_ratio = round(seal_amount * 10000 / float_cap, 4) if float_cap > 0 else 0

        # 更新状态
        state = self._get_state(code)

        # 炸板检测：上次涨停 → 本次不涨停 = 炸板一次
        if state.was_limit_up and not is_limit_up:
            state.break_count += 1
        state.was_limit_up = is_limit_up

        # 首次涨停时间
        if is_limit_up and state.first_limit_time is None:
            state.first_limit_time = datetime.now().strftime('%H:%M')

        # 封单采样
        if is_limit_up:
            state.seal_samples.append((time.time(), seal_amount))

        # 封单趋势（线性回归斜率）
        seal_trend = 0.0
        seal_trend_label = '封单平稳'
        if len(state.seal_samples) >= 3:
            times = np.array([s[0] for s in state.seal_samples])
            amounts = np.array([s[1] for s in state.seal_samples])
            times = times - times[0]  # 归零
            if times[-1] > 0:
                # 线性回归: y = a*x + b
                coeffs = np.polyfit(times, amounts, 1)
                seal_trend = round(coeffs[0], 4)  # 斜率（万元/秒）
                if seal_trend > 0.1:
                    seal_trend_label = '加封中'
                elif seal_trend < -0.1:
                    seal_trend_label = '减封中'
                else:
                    seal_trend_label = '封单平稳'

        # 换手率
        turnover_at_limit = quote.get('turnover_rate', 0)
        if not turnover_at_limit and float_cap > 0 and quote.get('turnover'):
            turnover_at_limit = round(quote['turnover'] / float_cap * 100, 2)

        return {
            'is_limit_up': is_limit_up,
            'limit_up_price': limit_up_price,
            'seal_amount': seal_amount,
            'seal_ratio': seal_ratio,
            'seal_trend': seal_trend,
            'seal_trend_label': seal_trend_label,
            'break_count': state.break_count,
            'first_limit_time': state.first_limit_time,
            'turnover_at_limit': turnover_at_limit,
        }

    def _empty_result(self):
        return {
            'is_limit_up': False,
            'limit_up_price': 0,
            'seal_amount': 0,
            'seal_ratio': 0,
            'seal_trend': 0,
            'seal_trend_label': '无数据',
            'break_count': 0,
            'first_limit_time': None,
            'turnover_at_limit': 0,
        }
```

- [ ] **Step 2: 验证模块可导入**

Run: `cd /Users/mac/Github/NiuNIuNiu/backend && python -c "from services.limit_up_monitor import LimitUpMonitor; m = LimitUpMonitor(); print('OK', m._empty_result())"`

Expected: `OK {'is_limit_up': False, ...}`

- [ ] **Step 3: 提交**

```bash
git add backend/services/limit_up_monitor.py
git commit -m "feat: 添加封单监控服务LimitUpMonitor"
```

---

### Task 3: 缓存优化 + 集成封单监控到 DataSourceAdapter

**Files:**
- Modify: `backend/services/data_source_adapter.py:24` (CACHE_TTL)
- Modify: `backend/services/data_source_adapter.py:155-172` (_build_dashboard 返回值)

- [ ] **Step 1: 修改缓存TTL**

在 `data_source_adapter.py` 中将 `CACHE_TTL = 5` 改为 `CACHE_TTL = 2`。

- [ ] **Step 2: 导入 LimitUpMonitor 并在 _build_dashboard 中集成**

在文件顶部导入区域添加：

```python
from .limit_up_monitor import LimitUpMonitor
```

在 `DataSourceAdapter.__init__` 末尾添加：

```python
self.limit_up_monitor = LimitUpMonitor()
```

- [ ] **Step 3: 在 _build_dashboard 返回值中增加 limit_up_monitor**

在 `_build_dashboard` 方法的 return 语句之前（`return {` 前面），添加封单监控调用：

```python
# 6. 封单监控
limit_up_data = self.limit_up_monitor.analyze(code, quote, order_book)
```

然后在返回值的 `data` 字典中添加字段（在 `'update_time'` 之前）：

```python
'limit_up_monitor': limit_up_data,
```

- [ ] **Step 4: 验证集成**

Run: `cd /Users/mac/Github/NiuNIuNiu/backend && python -c "from services.data_source_adapter import DataSourceAdapter; a = DataSourceAdapter(); r = a.get_l2_dashboard('000001'); print('limit_up_monitor' in r.get('data', {}))"`

Expected: `True`

- [ ] **Step 5: 提交**

```bash
git add backend/services/data_source_adapter.py
git commit -m "feat: 缓存TTL降至2秒，集成封单监控到L2看板"
```

---

### Task 4: 板块联动看板增强

**Files:**
- Modify: `backend/routes/stock_other.py`

- [ ] **Step 1: 增强 build_limit_up_theme_summary 函数**

在 `stock_other.py` 的 `build_limit_up_theme_summary` 函数中，在 `themes = sorted(...)` 之后、`return` 之前，增加联动分析逻辑：

```python
    # 联动分析
    for theme_item in themes:
        stock_count = len(theme_item['stocks'])
        # linkage_score：涨停数越多，联动越强
        # 用涨停数量本身打分：1家=弱，2-3家=中等，4+家=强
        if stock_count >= 4:
            theme_item['linkage_score'] = round(min(stock_count / 5, 1.0), 2)
            theme_item['linkage_label'] = '强联动'
        elif stock_count >= 2:
            theme_item['linkage_score'] = round(stock_count / 5, 2)
            theme_item['linkage_label'] = '中等联动'
        else:
            theme_item['linkage_score'] = 0.1
            theme_item['linkage_label'] = '弱联动'

    # 独狼股识别
    lone_wolf_stocks = []
    for theme_item in themes:
        if theme_item['count'] == 1:
            lone_wolf_stocks.extend([s['code'] for s in theme_item['stocks']])

    # 市场情绪
    total_limit_up = sum(t['count'] for t in themes)
```

- [ ] **Step 2: 在 get_limit_up_themes 路由中添加跌停统计和情绪标签**

在 `get_limit_up_themes` 函数中，在 `data = build_limit_up_theme_summary(rows, code)` 之后、`data = _enrich_current_stock_info(...)` 之前，添加跌停统计：

```python
        # 获取跌停数据
        limit_down_count = 0
        try:
            dt_df = ak.stock_zt_pool_dtgc_em(date=trade_date)
            limit_down_count = len(dt_df) if dt_df is not None else 0
        except Exception:
            pass

        # 情绪标签
        limit_up_count = sum(t['count'] for t in data.get('themes', []))
        if limit_up_count > limit_down_count * 5:
            sentiment_label = '强势'
        elif limit_up_count > limit_down_count * 2:
            sentiment_label = '偏强'
        elif limit_up_count > limit_down_count:
            sentiment_label = '中性'
        else:
            sentiment_label = '偏弱'

        data['market_sentiment'] = {
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'sentiment_label': sentiment_label,
            'lone_wolf_stocks': data.get('lone_wolf_stocks', []),
        }
```

- [ ] **Step 3: 在 build_limit_up_theme_summary 的 return 中添加 lone_wolf_stocks**

在函数返回值字典中添加：

```python
'lone_wolf_stocks': lone_wolf_stocks,
```

- [ ] **Step 4: 验证接口**

Run: `cd /Users/mac/Github/NiuNIuNiu/backend && python -c "
from app import app
with app.test_client() as c:
    r = c.get('/api/v1/limit_up_themes?code=000001')
    d = r.get_json()
    print('market_sentiment' in d.get('data', {}))
    themes = d.get('data', {}).get('themes', [])
    if themes:
        print('linkage_label' in themes[0])
"`

Expected: `True` (both)

- [ ] **Step 5: 提交**

```bash
git add backend/routes/stock_other.py
git commit -m "feat: 涨停题材增加联动分析和市场情绪指标"
```

---

### Task 5: 实现 WebSocket 管理器

**Files:**
- Create: `backend/websocket_manager.py`

- [ ] **Step 1: 创建 WebSocketManager**

```python
"""
WebSocket 连接管理器
负责客户端订阅、定时推送 L2 数据
"""
import logging
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room, leave_room

from services.data_source_adapter import DataSourceAdapter

logger = logging.getLogger(__name__)

PUSH_INTERVAL = 3  # 秒

# 客户端订阅关系: { sid: { code, room } }
_subscriptions = {}

# 活跃推送的房间集合
_active_rooms = set()

adapter = DataSourceAdapter(use_l2=False)


def is_trade_time():
    """判断当前是否在交易时间"""
    now = datetime.now()
    weekday = now.weekday()  # 0=Mon, 6=Sun
    if weekday >= 5:
        return False
    hour, minute = now.hour, now.minute
    # 09:30-11:30
    if (hour == 9 and minute >= 30) or hour == 10 or (hour == 11 and minute <= 30):
        return True
    # 13:00-15:00
    if hour == 13 or hour == 14 or (hour == 15 and minute == 0):
        return True
    return False


def register_websocket_events(socketio):
    """注册所有 WebSocket 事件处理"""

    @socketio.on('connect')
    def handle_connect():
        from flask import request
        sid = request.sid
        logger.info(f"WebSocket 客户端连接: {sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        from flask import request
        sid = request.sid
        if sid in _subscriptions:
            sub = _subscriptions.pop(sid)
            room = sub['room']
            leave_room(room)
            # 检查房间是否还有人
            remaining = [s for s, info in _subscriptions.items() if info['room'] == room]
            if not remaining:
                _active_rooms.discard(room)
            logger.info(f"WebSocket 客户端断开: {sid}, 移除订阅 {sub['code']}")

    @socketio.on('subscribe')
    def handle_subscribe(data):
        from flask import request
        sid = request.sid
        code = data.get('code', '000001')
        room = f'stock_{code}'

        # 如果之前订阅了其他股票，先离开旧房间
        if sid in _subscriptions:
            old_room = _subscriptions[sid]['room']
            leave_room(old_room)
            remaining = [s for s, info in _subscriptions.items()
                         if info['room'] == old_room and s != sid]
            if not remaining:
                _active_rooms.discard(old_room)

        join_room(room)
        _subscriptions[sid] = {'code': code, 'room': room}
        _active_rooms.add(room)
        logger.info(f"客户端 {sid} 订阅股票 {code}")

        # 立即推送一次当前数据
        try:
            result = adapter.get_l2_dashboard(code)
            emit('l2_update', result, room=sid)
        except Exception as e:
            emit('error', {'message': str(e)}, room=sid)

    @socketio.on('unsubscribe')
    def handle_unsubscribe():
        from flask import request
        sid = request.sid
        if sid in _subscriptions:
            sub = _subscriptions.pop(sid)
            room = sub['room']
            leave_room(room)
            remaining = [s for s, info in _subscriptions.items() if info['room'] == room]
            if not remaining:
                _active_rooms.discard(room)
            logger.info(f"客户端 {sid} 取消订阅 {sub['code']}")


def start_push_loop(socketio):
    """启动后台推送循环"""

    def push_loop():
        while True:
            socketio.sleep(PUSH_INTERVAL)
            if not _active_rooms:
                continue
            if not is_trade_time():
                continue

            # 收集需要推送的股票代码（去重）
            rooms_to_push = set(_active_rooms)
            for room in rooms_to_push:
                code = room.replace('stock_', '')
                try:
                    result = adapter.get_l2_dashboard(code)
                    socketio.emit('l2_update', result, room=room)
                except Exception as e:
                    logger.error(f"推送 {code} 数据失败: {e}")
                    socketio.emit('error', {'message': str(e)}, room=room)

    socketio.start_background_task(push_loop)
```

- [ ] **Step 2: 验证模块可导入**

Run: `cd /Users/mac/Github/NiuNIuNiu/backend && python -c "from websocket_manager import is_trade_time; print('OK', is_trade_time())"`

Expected: `OK False` (或 True，取决于当前时间)

- [ ] **Step 3: 提交**

```bash
git add backend/websocket_manager.py
git commit -m "feat: 添加WebSocket连接管理器和定时推送"
```

---

### Task 6: 集成 SocketIO 到 Flask 应用

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: 在 app.py 中导入并初始化 SocketIO**

在 `from flask_cors import CORS` 之后添加：

```python
from flask_socketio import SocketIO
```

在 `CORS(app)` 之后添加：

```python
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
```

- [ ] **Step 2: 注册 WebSocket 事件并启动推送循环**

在 `register_blueprints(app)` 之后添加：

```python
# 注册 WebSocket 事件
from websocket_manager import register_websocket_events, start_push_loop
register_websocket_events(socketio)
start_push_loop(socketio)
```

- [ ] **Step 3: 修改启动方式**

将文件末尾的：

```python
    app.run(debug=True, host='0.0.0.0', port=9001)
```

改为：

```python
    socketio.run(app, debug=True, host='0.0.0.0', port=9001)
```

- [ ] **Step 4: 验证服务启动**

Run: `cd /Users/mac/Github/NiuNIuNiu/backend && timeout 5 python app.py 2>&1 | head -20 || true`

Expected: 看到 "启动股票数据API服务" 的日志，无导入错误

- [ ] **Step 5: 提交**

```bash
git add backend/app.py
git commit -m "feat: 集成Flask-SocketIO到主应用"
```

---

### Task 7: 安装前端 socket.io-client 依赖

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: 安装 socket.io-client**

Run: `cd /Users/mac/Github/NiuNIuNiu/frontend && npm install socket.io-client`

- [ ] **Step 2: 提交**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: 添加socket.io-client前端依赖"
```

---

### Task 8: 创建前端 WebSocket 服务

**Files:**
- Create: `frontend/src/services/websocket.js`

- [ ] **Step 1: 实现 StockWebSocket 类**

```javascript
import { io } from 'socket.io-client';
import { apiConfig } from '../config/api';

class StockWebSocket {
  constructor() {
    this.socket = null;
    this._callbacks = {
      l2Update: [],
      disconnect: [],
      connect: [],
    };
  }

  connect() {
    if (this.socket?.connected) return;

    this.socket = io(apiConfig.baseURL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 10,
    });

    this.socket.on('connect', () => {
      console.log('[WS] 已连接');
      this._callbacks.connect.forEach(cb => cb());
    });

    this.socket.on('disconnect', (reason) => {
      console.log('[WS] 已断开:', reason);
      this._callbacks.disconnect.forEach(cb => cb(reason));
    });

    this.socket.on('l2_update', (data) => {
      this._callbacks.l2Update.forEach(cb => cb(data));
    });

    this.socket.on('error', (data) => {
      console.error('[WS] 服务端错误:', data.message);
    });
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }

  subscribe(code) {
    if (this.socket?.connected) {
      this.socket.emit('subscribe', { code });
    }
  }

  unsubscribe() {
    if (this.socket?.connected) {
      this.socket.emit('unsubscribe');
    }
  }

  onL2Update(callback) {
    this._callbacks.l2Update.push(callback);
    return () => {
      this._callbacks.l2Update = this._callbacks.l2Update.filter(cb => cb !== callback);
    };
  }

  onConnect(callback) {
    this._callbacks.connect.push(callback);
    return () => {
      this._callbacks.connect = this._callbacks.connect.filter(cb => cb !== callback);
    };
  }

  onDisconnect(callback) {
    this._callbacks.disconnect.push(callback);
    return () => {
      this._callbacks.disconnect = this._callbacks.disconnect.filter(cb => cb !== callback);
    };
  }

  isConnected() {
    return this.socket?.connected || false;
  }
}

// 单例
export const stockWS = new StockWebSocket();
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/services/websocket.js
git commit -m "feat: 添加前端WebSocket客户端服务"
```

---

### Task 9: 更新 atoms.js — 提取 L2 数据解析 + WS 状态

**Files:**
- Modify: `frontend/src/store/atoms.js`

- [ ] **Step 1: 添加 wsConnectedAtom 和 limitUpMonitorAtom**

在 `export const dataValidationAtom = atom(null);` 之后添加：

```javascript
// WebSocket 连接状态
export const wsConnectedAtom = atom(false);

// 封单监控数据
export const limitUpMonitorAtom = atom(null);
```

- [ ] **Step 2: 提取 L2 数据解析为共享函数**

在 `fetchL2DashboardAtom` 之前添加一个共享函数：

```javascript
/**
 * 解析 L2 Dashboard 返回数据并更新 atoms
 * 供 HTTP 轮询和 WebSocket 推送共用
 */
export const applyL2DashboardData = (set, get, data) => {
  if (!data?.success || !data?.data) return false;

  const d = data.data;

  // 1. 分时图
  const timeshare = d.timeshare || [];
  const alignedTimeshare = alignTimeshareToTradingAxis(timeshare);
  set(timeshareDataAtom, {
    timeAxis: alignedTimeshare.axis,
    fenshi: alignedTimeshare.fenshi,
    volume: alignedTimeshare.volume,
    zhuli: [],
    sanhu: [],
    big_map: d.big_map || {},
    order_book: d.order_book || null,
    base_info: {
      prevClosePrice: d.stock_info.yesterday_close,
      openPrice: d.stock_info.open,
      highPrice: d.stock_info.high,
      lowPrice: d.stock_info.low,
    },
  });

  // 2. 大单数据
  const orders = d.large_orders || d.orders || [];
  const stats = d.statistics || {};
  const buyCount = orders.filter(o => o.direction === '被买' || o.direction === '主买').length;
  const sellCount = orders.filter(o => o.direction === '被卖' || o.direction === '主卖').length;
  const neutralCount = orders.length - buyCount - sellCount;
  const totalAmount = orders.reduce((sum, o) => sum + (o.amount || 0), 0);
  const buyAmount = orders.filter(o => o.direction === '被买' || o.direction === '主买').reduce((sum, o) => sum + (o.amount || 0), 0);
  const netInflow = buyAmount - (totalAmount - buyAmount);

  set(largeOrdersDataAtom, {
    summary: { buyCount, sellCount, neutralCount, totalAmount, netInflow },
    largeOrders: orders.map(order => ({
      time: order.time,
      type: (order.direction === '被买' || order.direction === '主买') ? 'buy' : 'sell',
      price: order.price,
      volume: order.volume_lots,
      amount: order.amount * 10000,
      category: determineCategoryFromWan(order.amount),
      direction: order.direction,
    })),
    levelStats: {
      D300: stats.above_300,
      D100: stats.above_100,
      D50: stats.above_50,
      D30: stats.above_30,
      under_D30: stats.below_30,
    },
  });

  // 3. 股票基础数据
  set(stockBasicDataAtom, d.stock_info);

  // 4. 封单监控
  if (d.limit_up_monitor) {
    set(limitUpMonitorAtom, d.limit_up_monitor);
  }

  return true;
};
```

- [ ] **Step 3: 重构 fetchL2DashboardAtom 使用共享函数**

将 `fetchL2DashboardAtom` 中 `if (data.success === true && data.data) { ... }` 整个 if 块替换为：

```javascript
      if (!applyL2DashboardData(set, get, data)) {
        set(errorAtom, data.message || '获取L2看板数据失败');
      }
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/store/atoms.js
git commit -m "feat: 提取L2数据解析函数，添加WS状态和封单监控atom"
```

---

### Task 10: 重构 StockDashboard — WebSocket 集成

**Files:**
- Modify: `frontend/src/pages/StockDashboard/index.js`

- [ ] **Step 1: 添加 WebSocket 相关导入**

在现有 import 区域添加：

```javascript
import { stockWS } from '../../services/websocket';
import {
  wsConnectedAtom,
  applyL2DashboardData,
  timeshareDataAtom,
  largeOrdersDataAtom,
  stockBasicDataAtom,
  limitUpMonitorAtom,
  errorAtom,
  loadingAtom,
} from '../../store/atoms';
```

更新现有的 atoms 导入，确保包含新增的 atom。

- [ ] **Step 2: 在组件中添加 WebSocket 状态**

在 `StockDashboard` 组件内部，现有的 state 声明之后添加：

```javascript
  const [wsConnected, setWsConnected] = useAtom(wsConnectedAtom);
  const [, setTimeshareData] = useAtom(timeshareDataAtom);
  const [, setLargeOrdersData] = useAtom(largeOrdersDataAtom);
  const [, setStockBasicData] = useAtom(stockBasicDataAtom);
  const [, setLimitUpMonitor] = useAtom(limitUpMonitorAtom);
  const [, setError] = useAtom(errorAtom);
  const [, setLoading] = useAtom(loadingAtom);
```

- [ ] **Step 3: 添加 WebSocket 连接 useEffect**

在模拟回放的 useEffect 之后，添加 WebSocket 连接逻辑：

```javascript
  // WebSocket 连接管理
  useEffect(() => {
    // 模拟模式不使用 WebSocket
    if (simulationEnabled) {
      stockWS.disconnect();
      setWsConnected(false);
      return;
    }

    if (!isTradeTime()) {
      return;
    }

    stockWS.connect();

    const removeUpdate = stockWS.onL2Update((data) => {
      // 使用共享解析函数更新所有 atom
      const setter = (atom, value) => {
        if (atom === timeshareDataAtom) setTimeshareData(value);
        else if (atom === largeOrdersDataAtom) setLargeOrdersData(value);
        else if (atom === stockBasicDataAtom) setStockBasicData(value);
        else if (atom === limitUpMonitorAtom) setLimitUpMonitor(value);
        else if (atom === errorAtom) setError(value);
        else if (atom === loadingAtom) setLoading(value);
      };
      // 直接解析 WS 推送的数据
      if (data?.success && data?.data) {
        const d = data.data;
        const timeshare = d.timeshare || [];
        const { alignTimeshareToTradingAxis } = require('../../pages/StockDashboard/utils/l2Analysis');
        const alignedTimeshare = alignTimeshareToTradingAxis(timeshare);
        setTimeshareData({
          timeAxis: alignedTimeshare.axis,
          fenshi: alignedTimeshare.fenshi,
          volume: alignedTimeshare.volume,
          zhuli: [],
          sanhu: [],
          big_map: d.big_map || {},
          order_book: d.order_book || null,
          base_info: {
            prevClosePrice: d.stock_info?.yesterday_close,
            openPrice: d.stock_info?.open,
            highPrice: d.stock_info?.high,
            lowPrice: d.stock_info?.low,
          },
        });

        const orders = d.large_orders || d.orders || [];
        const stats = d.statistics || {};
        const buyCount = orders.filter(o => o.direction === '被买' || o.direction === '主买').length;
        const sellCount = orders.filter(o => o.direction === '被卖' || o.direction === '主卖').length;
        const neutralCount = orders.length - buyCount - sellCount;
        const totalAmount = orders.reduce((sum, o) => sum + (o.amount || 0), 0);
        const buyAmount = orders.filter(o => o.direction === '被买' || o.direction === '主买').reduce((sum, o) => sum + (o.amount || 0), 0);
        const netInflow = buyAmount - (totalAmount - buyAmount);

        setLargeOrdersData({
          summary: { buyCount, sellCount, neutralCount, totalAmount, netInflow },
          largeOrders: orders.map(order => ({
            time: order.time,
            type: (order.direction === '被买' || order.direction === '主买') ? 'buy' : 'sell',
            price: order.price,
            volume: order.volume_lots,
            amount: order.amount * 10000,
            direction: order.direction,
          })),
          levelStats: {
            D300: stats.above_300,
            D100: stats.above_100,
            D50: stats.above_50,
            D30: stats.above_30,
            under_D30: stats.below_30,
          },
        });

        setStockBasicData(d.stock_info);

        if (d.limit_up_monitor) {
          setLimitUpMonitor(d.limit_up_monitor);
        }
      }
    });

    const removeConnect = stockWS.onConnect(() => {
      setWsConnected(true);
      // 连接后立即订阅当前股票
      stockWS.subscribe(stockCode);
      // 停止 HTTP 轮询
      if (l2TimerRef.current) {
        clearInterval(l2TimerRef.current);
        l2TimerRef.current = null;
      }
    });

    const removeDisconnect = stockWS.onDisconnect(() => {
      setWsConnected(false);
      // 断线降级：恢复 HTTP 轮询
      if (!l2TimerRef.current && !simulationEnabled) {
        l2TimerRef.current = setInterval(() => {
          if (isTradeTime()) fetchL2Data();
        }, L2_POLL_INTERVAL);
      }
    });

    // 如果已连接，直接订阅
    if (stockWS.isConnected()) {
      stockWS.subscribe(stockCode);
    }

    return () => {
      removeUpdate();
      removeConnect();
      removeDisconnect();
    };
  }, [stockCode, simulationEnabled]);
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/StockDashboard/index.js
git commit -m "feat: StockDashboard集成WebSocket，交易时间自动切换推送"
```

---

### Task 11: 封单监控 UI 组件

**Files:**
- Create: `frontend/src/pages/StockDashboard/components/LimitUpMonitorPanel.js`
- Modify: `frontend/src/pages/StockDashboard/components/StockBasicInfo.js`

- [ ] **Step 1: 创建 LimitUpMonitorPanel 组件**

```javascript
import React from 'react';
import { Tag, Progress } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { useAtom } from 'jotai';
import { limitUpMonitorAtom } from '../../../store/atoms';

const LimitUpMonitorPanel = () => {
  const [data] = useAtom(limitUpMonitorAtom);

  if (!data || !data.is_limit_up) {
    return null;
  }

  const trendIcon = data.seal_trend > 0.1
    ? <ArrowUpOutlined style={{ color: '#52c41a' }} />
    : data.seal_trend < -0.1
      ? <ArrowDownOutlined style={{ color: '#ff4d4f' }} />
      : <MinusOutlined style={{ color: '#faad14' }} />;

  const trendColor = data.seal_trend > 0.1 ? '#52c41a' : data.seal_trend < -0.1 ? '#ff4d4f' : '#faad14';

  return (
    <div className="limit-up-monitor">
      <div className="limit-up-header">
        <Tag color="red">涨停</Tag>
        <span className="limit-up-price">{data.limit_up_price}</span>
        {data.first_limit_time && (
          <span className="limit-up-time">首封 {data.first_limit_time}</span>
        )}
        {data.break_count > 0 && (
          <Tag color="orange">炸板 {data.break_count} 次</Tag>
        )}
      </div>
      <div className="limit-up-stats">
        <div className="seal-info">
          <span className="label">封单</span>
          <span className="value">{data.seal_amount.toFixed(0)}万</span>
          <span className="label" style={{ marginLeft: 12 }}>封单比</span>
          <Progress
            percent={Math.min(data.seal_ratio * 100, 100)}
            size="small"
            format={() => `${(data.seal_ratio * 100).toFixed(2)}%`}
            style={{ width: 120, display: 'inline-flex', marginLeft: 4 }}
          />
        </div>
        <div className="seal-trend">
          <span className="label">趋势</span>
          {trendIcon}
          <span style={{ color: trendColor, marginLeft: 4 }}>{data.seal_trend_label}</span>
        </div>
      </div>
    </div>
  );
};

export default LimitUpMonitorPanel;
```

- [ ] **Step 2: 在 StockBasicInfo 中引入 LimitUpMonitorPanel**

在 `StockBasicInfo.js` 的 import 区域添加：

```javascript
import LimitUpMonitorPanel from './LimitUpMonitorPanel';
```

在 `basic-stats` div 之后、闭合 `stock-header-new` div 之前，添加：

```jsx
          <LimitUpMonitorPanel />
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/StockDashboard/components/LimitUpMonitorPanel.js frontend/src/pages/StockDashboard/components/StockBasicInfo.js
git commit -m "feat: 添加封单监控UI面板"
```

---

### Task 12: 增强 ThemeLimitUpPanel 前端展示

**Files:**
- Modify: `frontend/src/pages/StockDashboard/components/ThemeLimitUpPanel.js`

- [ ] **Step 1: 添加市场情绪条和联动度展示**

在 `ThemeLimitUpPanel` 组件中，在 `const currentThemeText = ...` 之后添加：

```javascript
  const sentiment = data.market_sentiment || {};
  const sentimentColor = {
    '强势': '#ff4d4f',
    '偏强': '#faad14',
    '中性': '#1890ff',
    '偏弱': '#52c41a',
  }[sentiment.sentiment_label] || '#999';

  const linkageColor = (label) => {
    if (label === '强联动') return '#52c41a';
    if (label === '中等联动') return '#faad14';
    return '#999';
  };
```

在 `theme-current-box` div 之前，添加市场情绪条：

```jsx
      {sentiment.sentiment_label && (
        <div className="market-sentiment-bar" style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '6px 12px', marginBottom: 8,
          background: 'rgba(255,255,255,0.04)', borderRadius: 4,
        }}>
          <Tag color={sentimentColor}>{sentiment.sentiment_label}</Tag>
          <span style={{ color: '#ff4d4f' }}>涨停 {sentiment.limit_up_count}</span>
          <span style={{ color: '#52c41a' }}>跌停 {sentiment.limit_down_count}</span>
          {(sentiment.lone_wolf_stocks || []).length > 0 && (
            <span style={{ color: '#faad14', fontSize: 12 }}>
              独狼 {sentiment.lone_wolf_stocks.length} 只
            </span>
          )}
        </div>
      )}
```

在 `theme-rank-count` span 旁边添加联动标签：

在 `<span className="theme-rank-count">涨停 {theme.count} 家</span>` 之后添加：

```jsx
                {theme.linkage_label && (
                  <Tag color={linkageColor(theme.linkage_label)} style={{ marginLeft: 4, fontSize: 11 }}>
                    {theme.linkage_label}
                  </Tag>
                )}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/pages/StockDashboard/components/ThemeLimitUpPanel.js
git commit -m "feat: 题材面板增加市场情绪和联动度展示"
```

---

### Task 13: 端到端验证

- [ ] **Step 1: 启动后端并验证 WebSocket**

Run: `cd /Users/mac/Github/NiuNIuNiu/backend && timeout 10 python -c "
from app import app, socketio
print('SocketIO async_mode:', socketio.async_mode)
with app.test_client() as c:
    r = c.get('/api/v1/l2_dashboard?code=000001')
    d = r.get_json()
    print('L2 Dashboard OK:', d.get('success'))
    print('Has limit_up_monitor:', 'limit_up_monitor' in d.get('data', {}))
    r2 = c.get('/api/v1/limit_up_themes?code=000001')
    d2 = r2.get_json()
    print('Has market_sentiment:', 'market_sentiment' in d2.get('data', {}))
" 2>&1 || true`

Expected: 全部输出 True

- [ ] **Step 2: 验证前端编译**

Run: `cd /Users/mac/Github/NiuNIuNiu/frontend && npx react-scripts build 2>&1 | tail -5`

Expected: `Compiled successfully.`

- [ ] **Step 3: 最终提交**

如果有遗漏的改动：

```bash
git add -A
git commit -m "feat: L2看板优化完成 - 封单监控、缓存优化、联动增强、WebSocket推送"
```
