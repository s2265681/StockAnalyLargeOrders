# 核心游资（龙虎榜）模块设计文档

**日期：** 2026-05-16
**状态：** 已确认

---

## 概述

新增"核心游资"页面，调用 akshare 龙虎榜接口，展示每日龙虎榜股票列表及买卖席位详情，支持日期切换，识别并高亮游资席位，每只股票配 AI 分析按钮对龙虎榜资金意图进行解读。数据统一入库，避免重复拉取和重复分析。

---

## 数据库设计

### 1. `dragon_tiger_daily` — 龙虎榜每日股票列表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT PK | |
| date | VARCHAR(8) | 格式 YYYYMMDD |
| code | VARCHAR(6) | 股票代码 |
| name | VARCHAR(20) | 股票名称 |
| change_pct | DECIMAL(6,2) | 涨跌幅 |
| total_amount | BIGINT | 成交额（分） |
| lhb_amount | BIGINT | 龙虎榜成交额 |
| net_buy | BIGINT | 净买入额 |
| buy_seat_count | INT | 买入席位数 |
| sell_seat_count | INT | 卖出席位数 |
| reason | VARCHAR(200) | 上榜原因 |
| sectors | VARCHAR(200) | 板块/题材（逗号分隔） |
| created_at | DATETIME | |
| UNIQUE KEY | (date, code) | |

### 2. `dragon_tiger_seats` — 席位明细

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT PK | |
| date | VARCHAR(8) | |
| code | VARCHAR(6) | |
| direction | ENUM('buy','sell') | 买入/卖出方向 |
| rank | INT | 席位排名（1-5） |
| seat_name | VARCHAR(100) | 席位名称 |
| buy_amount | BIGINT | 买入额（分） |
| sell_amount | BIGINT | 卖出额（分） |
| net_amount | BIGINT | 净额 |
| is_hot_money | TINYINT(1) | 是否游资席位 |
| created_at | DATETIME | |
| INDEX | (date, code, direction) | |

### 3. `dragon_tiger_ai` — AI 分析结果

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT PK | |
| date | VARCHAR(8) | |
| code | VARCHAR(6) | |
| analysis | TEXT | AI 解读内容 |
| created_at | DATETIME | |
| updated_at | DATETIME | |
| UNIQUE KEY | (date, code) | 避免重复分析 |

---

## 后端设计

### 新文件：`backend/routes/dragon_tiger.py`

#### 接口 1：获取龙虎榜列表

```
GET /api/v1/dragon-tiger?date=20260515
```

**逻辑：**
1. 查询 `dragon_tiger_daily` 是否有当日数据
2. 有则直接返回（含 `dragon_tiger_seats` 席位数据）
3. 无则调用 akshare：
   - `ak.stock_lhb_detail_em(trade_date=date)` → 获取股票列表
   - 逐一调用 `ak.stock_lhb_stock_detail_date_em(symbol, start_date, end_date)` → 获取席位明细
   - 游资识别，写入 DB
4. 返回完整数据（包含所有股票及其席位）

**游资识别规则（席位名关键词匹配）：**
```python
HOT_MONEY_KEYWORDS = [
    "知春路", "成都", "东方财富", "佛山", "宁波", "营业部",
    "上海浦东", "深圳益田", "绍兴", "杭州", "拉萨",
    "游资", "华鑫", "财通", "中信建投",
]
```
席位名包含任一关键词则标记 `is_hot_money=1`。

#### 接口 2：AI 分析

```
POST /api/v1/dragon-tiger/ai-analysis
Body: { "date": "20260515", "code": "002031" }
```

**逻辑：**
1. 查询 `dragon_tiger_ai` 是否已有该 (date, code) 的分析
2. 有则直接返回，不重新调用 Claude
3. 无则构建 prompt（含买卖席位数据、游资标记、净额等），调用 Claude API
4. 将结果写入 `dragon_tiger_ai`，返回分析内容

**AI Prompt 方向：**
- 分析买卖席位构成（游资 vs 机构 vs 散户）
- 判断资金意图（主动买入 vs 对倒 vs 出货）
- 结合净额判断主力立场
- 给出简洁的操作参考

**注册：** 在 `backend/routes/__init__.py` 和 `backend/app.py` 中注册 Blueprint。

---

## 前端设计

### 新目录：`frontend/src/pages/DragonTiger/`
- `index.js` — 主组件
- `index.css` — 样式

### 布局

```
┌─────────────────────────────────────────────────────┐
│ 导航栏  ...  核心游资  ...             [前一天][日期][后一天] │
├──────────────┬──────────────────────────────────────┤
│ 股票列表      │  巨轮智能 (002031) 板块: 机器人  净额: 4.32亿  [AI分析] │
│              │                                      │
│ 巨轮智能      │  ┌── 买入席位 ────┬── 卖出席位 ────┐  │
│ 002031       │  │ 席位名  买入  净│ 席位名  买入  净│  │
│ 机器人/工业   │  │ 深股通  ...    │ 国泰知春路 ... │  │
│              │  │ 国泰知春路(游资)│ ...            │  │
│ 多氟多        │  └───────────────┴────────────────┘  │
│ 002407       │                                      │
│ 氢氟酸/电解液 │  [AI分析结果展示区 - 点击按钮后出现]       │
│              │                                      │
└──────────────┴──────────────────────────────────────┘
```

### 组件状态
- `currentDate` — 当前日期（默认最近交易日）
- `stocks` — 龙虎榜股票列表
- `selectedCode` — 当前选中股票代码
- `aiResults` — Map<code, analysis>（内存缓存，已分析的不重复请求）
- `aiLoading` — Set<code>（正在分析中的股票）

### 游资高亮
- `is_hot_money=true` 的席位名称渲染为粉色（`#ff69b4` 或 `#e91e8c`）

### 日期导航
- 复用现有 `offsetDate` / `getLastTradingDayStr` 工具函数逻辑
- "后一天"按钮在当日时 disabled

### 导航集成
- `App.js` 的 `navItems` 新增 `{ key: '/dragon-tiger', label: '核心游资' }`
- 新增路由 `<Route path="/dragon-tiger" element={<DragonTiger />} />`

---

## 数据流

```
用户访问 /dragon-tiger
  → 前端 GET /api/v1/dragon-tiger?date=YYYYMMDD
  → 后端检查 DB → 有则返回 / 无则调 akshare → 写 DB → 返回
  → 前端渲染左侧列表，默认选中第一只股票
  → 用户点击 [AI分析]
  → 前端 POST /api/v1/dragon-tiger/ai-analysis
  → 后端检查 dragon_tiger_ai → 有则返回 / 无则调 Claude → 写 DB → 返回
  → 前端展示分析结果（内存缓存，切换日期后清空）
```

---

## 不在范围内

- 龙虎榜席位历史统计（胜率、跟单分析）
- 实时刷新（当日数据拉取一次即可）
- 游资席位列表的动态配置界面
