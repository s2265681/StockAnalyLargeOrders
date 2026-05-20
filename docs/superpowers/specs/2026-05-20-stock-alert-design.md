# 股票条件预警模块设计文档

**日期：** 2026-05-20  
**状态：** 已确认

---

## 概述

新增「条件预警」模块，允许用户对指定股票设置价格或封单条件，触发时发邮件通知到指定收件箱。多用户场景下每条规则独立配置收件邮箱。

---

## 功能范围

### 预警类型

| 类型 | alert_type | 阈值含义 | 触发条件 |
|------|-----------|---------|---------|
| 涨跌幅预警 | `change_pct` | 百分比（正整数），配合方向：「涨超过 X%」或「跌超过 X%」 | 实时涨跌幅 >= 阈值（above）或 <= -阈值（below） |
| 涨停预警 | `limit_up` | 无 | 股票达到涨停价 |
| 跌停预警 | `limit_down` | 无 | 股票达到跌停价 |
| 封单量预警 | `seal_order` | 手数（正整数） | 涨停状态下封单量 < 阈值（方向固定为 below，无需用户选择） |

### 规则生命周期

- 创建后状态为 `active`（监控中）
- 条件命中 → 发邮件 → 状态改为 `triggered`（已触发，停止监控）
- 用户手动点击「重新激活」→ 状态回到 `active`
- 用户手动点击「停用」→ 状态改为 `disabled`

### 批量新增

- 一次最多同时添加 3 条规则
- 每条规则独立设置：股票代码、预警类型、阈值、收件邮箱
- 选涨停/跌停类型时隐藏阈值输入框

---

## 数据模型

### 表：`alert_rules`

```sql
CREATE TABLE alert_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    code        VARCHAR(10) NOT NULL,
    stock_name  VARCHAR(20) NOT NULL DEFAULT '',
    alert_type  VARCHAR(20) NOT NULL,  -- change_pct / limit_up / limit_down / seal_order
    threshold   REAL,                  -- NULL for limit_up / limit_down
    direction   VARCHAR(5),            -- 'above' / 'below'，仅 change_pct / seal_order 使用
    email       VARCHAR(100) NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'active',  -- active / triggered / disabled
    triggered_at DATETIME,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## 后端架构

### 监控服务（`services/alert_monitor.py`）

- 在 `websocket_manager.py` 的 `start_push_loop` 中启动独立 eventlet greenlet
- 交易时段（9:25–11:30 / 13:00–15:00）每 3 秒执行一次检查
- 非交易时段休眠，不消耗资源
- 逻辑：
  1. 查询所有 `status = 'active'` 的规则，按 code 分组
  2. 对每个 code 调用 `DataSourceAdapter` 获取实时行情
  3. `seal_order` 类型额外调用 L2 数据获取封单量
  4. 逐条检查条件，命中则调用邮件发送 + 更新状态

### 邮件发送（`utils/alert_notify.py`）

复用 `utils/job_notify.py` 的 `_smtp_config()` 和 `_send_email()`，新增：

```python
def send_stock_alert(code: str, name: str, alert_type: str, message: str, to_email: str) -> bool
```

邮件主题格式：`[预警] {name}({code}) {alert_type_label} · {触发时间}`

### REST API（`routes/alert_rules.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/alert-rules` | 获取当前用户所有规则 |
| POST | `/api/alert-rules/batch` | 批量新增（body: list，最多3条） |
| PUT | `/api/alert-rules/<id>` | 编辑单条规则 |
| DELETE | `/api/alert-rules/<id>` | 删除规则 |
| POST | `/api/alert-rules/<id>/reactivate` | 重新激活（triggered → active） |

所有接口需登录态（复用现有 `auth` 装饰器）。

---

## 前端架构

### 新页面：`frontend/src/pages/StockAlert/`

文件结构：
```
StockAlert/
  index.js    — 主页面组件
  index.css   — 样式
```

### 布局（方案 A）

```
┌─────────────────────────────────────────┐
│  条件预警              [+ 新增预警]      │
├─────────────────────────────────────────┤
│  规则列表                               │
│  ┌──────────────────────────────────┐   │
│  │ 股票 │ 类型 │ 阈值 │ 邮箱 │ 状态 │ 操作 │
│  │ 600519│涨停封单│<5000手│xxx@.. │监控中│ 编辑/删除 │
│  │ 000001│涨跌幅│>5%│yyy@..│已触发│ 重新激活/删除 │
│  └──────────────────────────────────┘   │
├─────────────────────────────────────────┤
│  新增预警区（点击展开，最多3行）          │
│  ┌────────┬──────┬──────┬────────────┐  │
│  │股票代码 │类型▾  │阈值  │收件邮箱    │  │
│  │股票代码 │类型▾  │阈值  │收件邮箱    │  │
│  │股票代码 │类型▾  │阈值  │收件邮箱    │  │
│  └────────┴──────┴──────┴────────────┘  │
│                              [保存]      │
└─────────────────────────────────────────┘
```

### 路由

在 `App.js` 中新增路由 `/alert`，侧边栏菜单加入「条件预警」入口。

---

## 关键约束

- 后端跑在 eventlet 下，监控服务用 `eventlet.spawn` 启动 greenlet，不用 threading
- `seal_order` 类型的 L2 数据查询频率与实时行情相同（3s），但 L2 可能有限流，需加 try/except 容错
- SMTP 配置沿用 `.env` 中的 `SMTP_HOST / SMTP_USER / SMTP_PASS`，收件人用规则里的 `email` 字段
- 监控服务不依赖 WebSocket 订阅，独立轮询所有 active 规则

---

## 不在本次范围内

- 推送通知（微信/短信）
- 预警触发历史记录表（只记录 `triggered_at` 时间，不展示历史列表）
- 股票名称自动补全（手动输入代码，后端查询名称填充）
