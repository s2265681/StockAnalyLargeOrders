# L2大单系统设计文档

## 概述

基于东方财富数据源，实现实时L2大单监控系统。初期使用免费接口，架构预留L2付费接口升级通道。

## 目标

实现与参考截图一致的股票大单系统，包含：
- 分时走势图 + 大单标注
- 分级统计面板（>300万/100万/50万/30万/<30万）
- 复选框筛选器
- 大单明细列表（时间/状态/价格/手数/金额）

## 数据源

### 东方财富免费API（当前阶段）

| 接口 | URL | 用途 |
|------|-----|------|
| 实时行情 | `push2.eastmoney.com/api/qt/stock/get` | 当前价、买一/卖一价 |
| 成交明细 | `push2.eastmoney.com/api/qt/stock/details/get` | 逐笔成交记录 |
| 分时走势 | `push2his.eastmoney.com/api/qt/stock/trends2/get` | 分时价格+成交量 |

### 买卖方向推算逻辑（免费阶段）

```
成交价 >= 卖一价  → 主买
成交价 <= 买一价  → 主卖
买一价 < 成交价 < 卖一价 → 中性盘（取上一笔方向）
```

开通L2后直接获取精确的主买/被买/主卖/被卖标识，替换推算逻辑。

### 东方财富L2接口（预留，后续升级）

与免费接口实现相同的方法签名，开通L2（约30元/月）后切换配置即可启用。

## 架构

```
前端 React (端口9000)
  ├─ StockChart.js (分时图+大单标注+统计面板)
  ├─ StockOrderDetails.js (复选框筛选+明细列表)
  └─ atoms.js (统一 fetchL2DashboardAtom)
       │
       │ 轮询 5秒 (交易时间 9:30-15:00)
       ▼
后端 Flask (端口9001)
  └─ /api/v1/l2_dashboard?code=000001
       │
       ├─ l2_dashboard.py (API路由)
       ├─ data_source_adapter.py (数据源切换)
       ├─ eastmoney_free.py (免费数据获取+方向推算)
       └─ eastmoney_l2.py (L2付费接口预留空壳)
```

## 统一API格式

`GET /api/v1/l2_dashboard?code=000001`

```json
{
  "success": true,
  "data": {
    "stock_info": {
      "code": "000001",
      "name": "平安银行",
      "price": 4.46,
      "yesterday_close": 4.42,
      "change_percent": 0.90
    },
    "timeshare": [
      { "time": "09:30", "price": 4.45, "avg_price": 4.44, "volume": 12000 }
    ],
    "statistics": {
      "above_300": { "buy_count": 25, "sell_count": 336, "buy_amount": 8675.60, "sell_amount": 143448.33 },
      "above_100": { "buy_count": 139, "sell_count": 380, "buy_amount": 20959.18, "sell_amount": 66978.33 },
      "above_50":  { "buy_count": 259, "sell_count": 348, "buy_amount": 18724.14, "sell_amount": 24795.51 },
      "above_30":  { "buy_count": 374, "sell_count": 567, "buy_amount": 14348.35, "sell_amount": 21813.36 },
      "below_30":  { "buy_count": 35230, "sell_count": 34170, "buy_amount": 98613.42, "sell_amount": 102163.39 }
    },
    "large_orders": [
      {
        "time": "15:00:00",
        "direction": "被买",
        "price": 4.46,
        "volume_lots": 9916,
        "amount": 442.25
      }
    ],
    "big_map": {
      "09:35": [{ "type": "主买", "volume": 414, "amount": 185.5 }]
    },
    "data_source": "eastmoney_free",
    "update_time": "2026-04-30 14:30:05"
  }
}
```

字段说明：
- `statistics` 中金额单位为万元
- `large_orders` 中 `amount` 为万元，`volume_lots` 为手数
- `big_map` 按时间分组，用于分时图上标注大单
- `data_source` 标识当前使用的数据源（`eastmoney_free` 或 `eastmoney_l2`）

## 后端新增文件

### `backend/services/eastmoney_free.py`

```python
class EastMoneyFreeSource:
    def get_realtime_quote(self, code) -> dict       # 实时行情(含买一卖一)
    def get_tick_details(self, code) -> list          # 逐笔成交明细
    def get_timeshare(self, code) -> list             # 分时走势
    def infer_direction(self, price, bid, ask) -> str # 推算买卖方向
```

### `backend/services/eastmoney_l2.py`

```python
class EastMoneyL2Source:
    # 与 FreeSource 相同的方法签名
    # 当前全部 raise NotImplementedError
    # 开通L2后实现
```

### `backend/services/data_source_adapter.py`

```python
class DataSourceAdapter:
    def __init__(self):
        self.source = EastMoneyFreeSource()

    def get_l2_dashboard(self, code) -> dict
        # 1. 获取实时行情
        # 2. 获取逐笔成交明细
        # 3. 获取分时走势
        # 4. 识别大单并分级统计
        # 5. 生成 big_map
        # 6. 返回统一格式
```

### `backend/routes/l2_dashboard.py`

```python
@bp.route('/api/v1/l2_dashboard')
def l2_dashboard():
    code = request.args.get('code', '000001')
    data = adapter.get_l2_dashboard(code)
    return jsonify(data)
```

### `backend/app.py` 改动

注册新蓝图 `l2_dashboard_bp`。

## 前端改动

### `atoms.js`

- 新增 `fetchL2DashboardAtom`，调用 `/api/v1/l2_dashboard`，一次获取所有数据
- 保留现有 atom 不删，新 atom 负责填充 `timeshareDataAtom`、`largeOrdersDataAtom`、`realtimeDataAtom`

### `StockChart.js`

- 分级统计区域增加金额列（当前只有笔数）
- 数据源改为从 `fetchL2DashboardAtom` 获取

### `StockOrderDetails.js`

- 新增复选框筛选器（300/100/50/30 可多选）
- 列格式调整为：时间 | 状态(被买/被卖) | 价格 | 手数 | 金额(万)
- 买入行红色，卖出行绿色

### `StockDashboard/index.js`

- 增加轮询逻辑：交易时间内每5秒调用 `fetchL2DashboardAtom`
- 非交易时间不轮询
- 组件卸载时清理定时器

## 缓存策略

| 数据 | 缓存TTL |
|------|---------|
| 实时行情 | 3秒 |
| 成交明细 | 5秒 |
| 分时走势 | 10秒 |
| `/api/v1/l2_dashboard` 整体 | 5秒 |

## 大单分级标准

| 级别 | 阈值 | 标签 |
|------|------|------|
| 超大单 | >= 300万元 | D300 |
| 大单 | >= 100万元 | D100 |
| 中单 | >= 50万元 | D50 |
| 小单 | >= 30万元 | D30 |
| 散单 | < 30万元 | under_D30 |

## 不改动的部分

- 现有 `/api/l2/tick`、`/api/v1/dadan` 等接口保持不动
- `stock_data_manager.py` 不改
- `StockBasicInfo.js` 不改
- 不新建页面/路由，在现有 StockDashboard 上改
- 现有 routes/ 下其他文件不改
