# 用户中心 + 权限管理 + 微信支付 设计规格

**日期：** 2026-05-16
**状态：** 已批准

---

## 1. 背景

当前系统是纯股票分析平台，完全没有用户认证、权限管理和支付系统。本次新增：
- 用户注册/登录/改密码（账户管理）
- 会员权限体系（VIP/免费）
- 微信支付（Mock实现，测试购买发1天会员）
- AI功能权限拦截（非VIP显示升级提示）

---

## 2. 数据库设计

### 2.1 users 用户表

```sql
CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  role ENUM('admin', 'user') DEFAULT 'user',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_username (username)
);
```

### 2.2 orders 订单表

```sql
CREATE TABLE orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_no VARCHAR(26) NOT NULL UNIQUE,   -- 26位唯一单号
  user_id INT NOT NULL,
  plan_type ENUM('daily','monthly','quarterly','semi','annual') NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  status ENUM('pending','paid') DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  INDEX idx_order_no (order_no)
);
```

### 2.3 user_subscriptions 订阅表

```sql
CREATE TABLE user_subscriptions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL UNIQUE,
  plan_type ENUM('daily','monthly','quarterly','semi','annual') NOT NULL,
  start_time DATETIME NOT NULL,
  end_time DATETIME NOT NULL,
  is_active TINYINT(1) DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id)
);
```

---

## 3. 后端 API 设计

**认证方式：** JWT，存于 localStorage，请求头 `Authorization: Bearer <token>`

### 3.1 认证路由 `/api/auth`

| 方法 | 路径 | 鉴权 | 功能 |
|------|------|------|------|
| POST | `/api/auth/login` | 无 | 用户名+密码登录，返回JWT |
| POST | `/api/auth/logout` | 需要 | 退出（前端清除token） |
| POST | `/api/auth/change-password` | 需要 | 修改密码（旧密码验证） |

### 3.2 用户路由 `/api/user`

| 方法 | 路径 | 鉴权 | 功能 |
|------|------|------|------|
| GET | `/api/user/profile` | 需要 | 返回用户信息+订阅到期时间 |

### 3.3 订单路由 `/api/orders`

| 方法 | 路径 | 鉴权 | 功能 |
|------|------|------|------|
| GET | `/api/orders` | 需要 | 订单列表，分页，page/page_size参数 |
| POST | `/api/orders/create` | 需要 | 创建订单，返回order_no |
| POST | `/api/orders/mock-pay` | 需要 | 测试用：直接激活1天会员，更新订单为paid |

### 3.4 套餐配置（后端常量）

```python
PLANS = {
    'monthly':   {'name': '月度VIP',  'amount': 380.00, 'days': 30},
    'quarterly': {'name': '季度VIP',  'amount': 900.00, 'days': 90},
    'semi':      {'name': '半年VIP',  'amount': 1600.00, 'days': 180},
    'annual':    {'name': '年度VIP',  'amount': 2500.00, 'days': 365},
    'daily':     {'name': '日度VIP',  'amount': 0.01,   'days': 1},   # 测试用
}
```

### 3.5 JWT Middleware

- `backend/utils/auth_middleware.py`
- 装饰器 `@require_auth` 保护需要登录的接口
- Token 有效期 7 天，密钥从环境变量 `JWT_SECRET` 读取（默认值 `niuniu-secret`）

### 3.6 密码安全

- 使用 `werkzeug.security.generate_password_hash` / `check_password_hash`
- 算法：pbkdf2:sha256

---

## 4. 前端设计

### 4.1 新增页面

| 路由 | 组件 | 功能 |
|------|------|------|
| `/login` | `Login` | 登录表单（用户名+密码） |
| `/user-center` | `UserCenter` | 用户信息、改密码、订单列表 |
| `/permission-center` | `PermissionCenter` | 套餐卡片、购买流程 |

### 4.2 AuthContext

- `frontend/src/context/AuthContext.js`
- 提供：`user`, `isVip`, `login()`, `logout()`, `refreshUser()`
- token 存 localStorage key `niuniu_token`
- 页面刷新时自动从 localStorage 恢复状态，请求 `/api/user/profile` 验证

### 4.3 路由保护

- 未登录访问任意受保护路由 → 重定向 `/login`
- 登录后访问 `/login` → 重定向 `/stock-dashboard`
- 登录页不需要鉴权

### 4.4 Header 修改

- 右侧追加：`用户名` + `退出` 按钮
- 点击用户名 → `/user-center`
- `退出` → 清除 token，跳转 `/login`

### 4.5 权限中心页面流程

```
套餐列表 → 点击「立即开通」 → 确认弹窗（套餐+价格）
→ 确认 → 后端创建订单 → 显示微信支付弹窗（假二维码图片）
→ 点击「已完成支付」 → 调用 mock-pay → 后端激活1天会员
→ Toast成功提示 → 刷新用户状态
```

**假二维码：** 使用固定的 placeholder 图片（`/fake-qrcode.png`）放在 `public/`

### 4.6 AI功能权限拦截

需要VIP的页面/功能：
- 情绪周期（`EmotionCycle`）
- 竞价抢筹（`AuctionGrab`）

非VIP用户看到内容区域遮罩：
```
┌────────────────────────────────┐
│  🔒 此功能需要VIP权限           │
│  升级权限后解锁全部分析功能      │
│  [立即升级]                     │
└────────────────────────────────┘
```
点击「立即升级」→ 跳转 `/permission-center`

### 4.7 用户中心页面结构

```
用户信息卡片：
  - 用户名
  - 手机号（如有）
  - VIP到期时间（无则显示"未开通"）

修改密码区域：
  - 旧密码 / 新密码 / 确认新密码

订单列表：
  - 权限名称 / 单号 / 金额 / 状态 / 创建时间
  - 分页（10条/页）
```

---

## 5. 权限级别

| 功能 | 免费用户 | VIP用户 |
|------|----------|---------|
| 股票基本分析 | ✓ | ✓ |
| L2大单看板 | ✓ | ✓ |
| 情绪周期 | 遮罩提示 | ✓ |
| 竞价抢筹 | 遮罩提示 | ✓ |
| 涨停梯队 | ✓ | ✓ |

---

## 6. 迁移策略

新增迁移文件：`backend/migrations/create_user_auth_tables.sql`

包含 `users`、`orders`、`user_subscriptions` 三张表的 CREATE TABLE 语句。

初始管理员账户由迁移脚本插入（username: `admin`，password: `admin123`）。

---

## 7. 文件结构变更

### 后端新增文件
```
backend/
├── routes/
│   ├── auth.py              # 登录、登出、改密码
│   ├── user.py              # 用户信息
│   └── orders.py            # 订单管理
├── utils/
│   └── auth_middleware.py   # JWT验证装饰器
└── migrations/
    └── create_user_auth_tables.sql
```

### 前端新增文件
```
frontend/src/
├── context/
│   └── AuthContext.js       # 全局认证状态
├── components/
│   └── PermissionGuard.js   # 权限遮罩组件
├── pages/
│   ├── Login/
│   │   └── index.js
│   ├── UserCenter/
│   │   ├── index.js
│   │   └── index.css
│   └── PermissionCenter/
│       ├── index.js
│       └── index.css
└── services/
    └── auth.js              # 认证相关API调用
```

### 修改的文件
- `backend/app.py` — 注册新路由蓝图
- `backend/routes/__init__.py` — 导出新路由
- `frontend/src/App.js` — 添加新路由、AuthProvider、Header修改
- `frontend/src/store/atoms.js` — 可能添加userAtom
