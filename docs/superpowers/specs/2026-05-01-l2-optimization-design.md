# L2 看板优化设计文档

## 概述

对 NiuNIuNiu L2 大单看盘系统进行四项优化：封单监控、缓存策略、板块联动增强、WebSocket 实时推送。所有新功能集成到现有 L2 Dashboard 统一接口。

---

## 模块一：封单监控

### 目标

为打板决策提供核心指标：封单力度、封单变化趋势、炸板次数。

### 实现

**新增文件**：`backend/services/limit_up_monitor.py`

**`LimitUpMonitor` 类**：
- 内存维护每只股票的状态（封单采样队列、炸板次数、首次涨停时间）
- 单例模式，跨请求保持状态

**核心逻辑**：

| 指标 | 计算方式 |
|------|---------|
| 涨停价 | `round(昨收 * 1.1, 2)`（普通股 10%） |
| is_limit_up | 当前价 == 涨停价 |
| seal_amount | 买一价 == 涨停价时的买一金额（万元） |
| seal_ratio | 封单金额 / 流通市值 |
| seal_trend | 最近 60 个采样点（3分钟）的线性回归斜率 |
| seal_trend_label | 正值="加封中"，负值="减封中"，接近0="封单平稳" |
| break_count | 价格从涨停价回落的次数 |
| first_limit_time | 首次触及涨停价的时间 |
| turnover_at_limit | 涨停时的换手率 |

**输入依赖**：
- `get_realtime_quote()` 返回的 `current_price`、`yesterday_close`、五档盘口
- `order_book` 中的 `bids[0]`（买一价和量）
- 流通市值需通过 akshare 获取（`stock_individual_info_em`），可缓存（日级别）

**返回结构**（嵌入 L2 Dashboard `data` 中）：
```json
{
  "limit_up_monitor": {
    "is_limit_up": true,
    "limit_up_price": 11.00,
    "seal_amount": 5000.0,
    "seal_ratio": 0.035,
    "seal_trend": 0.8,
    "seal_trend_label": "加封中",
    "break_count": 2,
    "first_limit_time": "09:45",
    "turnover_at_limit": 8.5
  }
}
```

### 前端展示

在 `StockBasicInfo` 组件或新增 `LimitUpMonitor` 组件中展示：
- 涨停状态标签（红色高亮）
- 封单量和封单比（进度条）
- 封单趋势（箭头 + 颜色：绿色加封/红色减封）
- 炸板次数（数字徽标，>0 时警示）
- 首次涨停时间

---

## 模块二：缓存策略优化

### 目标

降低盘中数据延迟，适配 3 秒 WebSocket 推送频率。

### 改动

**文件**：`backend/services/data_source_adapter.py`

| 场景 | 原 TTL | 新 TTL |
|------|--------|--------|
| 盘中实时数据 | 5 秒 | 2 秒 |
| 历史数据 | 300 秒 | 300 秒（不变） |

**改动内容**：
- 修改 `CACHE_TTL` 常量从 5 改为 2
- 历史数据 TTL 保持 300 秒不变

---

## 模块三：板块联动看板增强

### 目标

在现有涨停题材基础上增加联动分析，标记独狼涨停，提供市场情绪概览。

### 改动

**文件**：`backend/routes/stock_other.py`（涨停题材接口）

**新增计算**：
- `linkage_score`：同题材涨停数 / 同题材总成分股数
- `linkage_label`：>0.5 "强联动"，>0.2 "中等联动"，否则 "弱联动"
- `follow_count`：同题材涨幅 >3% 的非涨停股数量
- `lone_wolf_stocks`：题材内仅 1 只涨停且 follow_count < 3 的股票

**新增字段** `market_sentiment`：
```json
{
  "limit_up_count": 45,
  "limit_down_count": 3,
  "sentiment_label": "强势",
  "lone_wolf_stocks": ["000xxx"]
}
```

**情绪标签规则**：
- 涨停数 > 跌停数 * 5 → "强势"
- 涨停数 > 跌停数 * 2 → "偏强"
- 涨停数 > 跌停数 → "中性"
- 否则 → "偏弱"

### 前端展示

**文件**：`frontend/src/pages/StockDashboard/components/ThemeLimitUpPanel.js`

- 每个题材行增加联动度色标（绿/黄/红）
- 独狼股标记警示图标
- 顶部增加市场情绪条（涨停/跌停家数 + 情绪标签）

---

## 模块四：WebSocket 实时推送

### 目标

用 Flask-SocketIO 替代前端 HTTP 轮询，3 秒全量推送 L2 Dashboard 数据。

### 后端

**新增依赖**：`flask-socketio`、`eventlet`

**新增文件**：`backend/websocket_manager.py`

**`WebSocketManager` 类**：
- 维护客户端订阅关系：`{ sid: { code, room } }`
- 每个股票代码一个 room，同一股票多客户端共享推送
- 后台线程每 3 秒为每个活跃 room 获取数据并推送

**事件定义**：

| 事件 | 方向 | 数据 |
|------|------|------|
| `subscribe` | 客户端→服务端 | `{ code: "000001" }` |
| `unsubscribe` | 客户端→服务端 | `{}` |
| `l2_update` | 服务端→客户端 | 完整 L2 Dashboard JSON（含 limit_up_monitor） |
| `error` | 服务端→客户端 | `{ message: "..." }` |

**推送控制**：
- 仅交易时间推送（09:30-11:30, 13:00-15:00，周一至周五）
- 非交易时间发送一次当前状态后停止
- 客户端断开自动清理订阅

**`app.py` 改动**：
```python
from flask_socketio import SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
# 注册 websocket_manager 事件
# socketio.run(app, host='0.0.0.0', port=9001) 替代 app.run()
```

### 前端

**新增依赖**：`socket.io-client`

**新增文件**：`frontend/src/services/websocket.js`

```javascript
// 封装 WebSocket 连接管理
export class StockWebSocket {
  connect(url)          // 建立连接
  disconnect()          // 断开连接
  subscribe(code)       // 订阅股票
  onL2Update(callback)  // 监听数据更新
  onDisconnect(callback) // 监听断线
  isConnected()         // 连接状态
}
```

**`StockDashboard/index.js` 改动**：

```
交易时间 + 非模拟模式:
  1. 连接 WebSocket
  2. subscribe(stockCode)
  3. 监听 l2_update → 更新 atoms
  4. 停止 HTTP 轮询
  5. 断线 → 降级回 10 秒 HTTP 轮询

非交易时间 / 模拟模式:
  保持现有 HTTP 逻辑不变
```

**切换股票**：发送新的 `subscribe` 事件，后端自动切换 room。

### 前端 atoms 适配

**文件**：`frontend/src/store/atoms.js`

新增 `wsConnectedAtom`（boolean）标记 WebSocket 连接状态，供 UI 展示连接状态指示器。

数据更新复用现有的 atom 设置逻辑（与 `fetchL2DashboardAtom` 中的数据解析相同），提取为共享函数。

---

## 文件改动清单

| 操作 | 文件 |
|------|------|
| 新增 | `backend/services/limit_up_monitor.py` |
| 新增 | `backend/websocket_manager.py` |
| 新增 | `frontend/src/services/websocket.js` |
| 修改 | `backend/app.py`（集成 SocketIO） |
| 修改 | `backend/services/data_source_adapter.py`（集成封单监控 + 缓存TTL） |
| 修改 | `backend/routes/l2_dashboard.py`（返回值增加 limit_up_monitor） |
| 修改 | `backend/routes/stock_other.py`（联动分析增强） |
| 修改 | `frontend/src/store/atoms.js`（WS 状态 + 数据解析提取） |
| 修改 | `frontend/src/pages/StockDashboard/index.js`（WS 连接逻辑） |
| 修改 | `frontend/src/pages/StockDashboard/components/StockBasicInfo.js`（封单展示） |
| 修改 | `frontend/src/pages/StockDashboard/components/ThemeLimitUpPanel.js`（联动展示） |
| 修改 | `backend/requirements.txt`（新增 flask-socketio、eventlet） |
| 修改 | `frontend/package.json`（新增 socket.io-client） |
