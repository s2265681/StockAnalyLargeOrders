# 白天模式 + 用户注册登录 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 NiuNiuNiu 股票分析平台添加白天/黑夜主题切换，以及完整的用户注册、登录、权限管理系统。

**Architecture:** 主题系统使用 CSS 变量 + `data-theme` 属性切换，主题偏好存 localStorage。认证系统使用 JWT + Flask Blueprint，前端通过 React Context 管理认证状态，VIP 页面使用 PermissionGuard 组件保护。

**Tech Stack:** React 18, Jotai, Ant Design, Flask, PyJWT, werkzeug (password hashing), MySQL/pymysql

---

## 文件结构

### 新建文件

**后端：**
- `backend/utils/auth_middleware.py` — JWT 验证装饰器
- `backend/routes/auth.py` — 注册、登录、改密码 API
- `backend/routes/user.py` — 用户信息 API
- `backend/routes/orders.py` — 订单管理 API

**前端：**
- `frontend/src/context/AuthContext.js` — 认证状态管理（user, token, login, logout, register）
- `frontend/src/components/PermissionGuard.js` — VIP 权限守卫组件
- `frontend/src/components/ThemeToggle.js` — 主题切换按钮组件
- `frontend/src/pages/Login/index.js` — 登录页面
- `frontend/src/pages/Login/index.css` — 登录页样式
- `frontend/src/pages/Register/index.js` — 注册页面
- `frontend/src/pages/Register/index.css` — 注册页样式
- `frontend/src/pages/UserCenter/index.js` — 用户中心页面
- `frontend/src/pages/UserCenter/index.css` — 用户中心样式
- `frontend/src/pages/PermissionCenter/index.js` — 权限中心（订阅购买）
- `frontend/src/pages/PermissionCenter/index.css` — 权限中心样式

### 修改文件

- `frontend/src/index.css` — 将硬编码颜色替换为 CSS 变量，添加 light 主题变量
- `frontend/src/pages/LimitUpEchelon/index.css` — 替换硬编码颜色为 CSS 变量
- `frontend/src/pages/AuctionGrab/index.css` — 替换硬编码颜色为 CSS 变量
- `frontend/src/pages/EmotionCycle/index.css` — 替换硬编码颜色为 CSS 变量
- `frontend/src/pages/DragonTiger/index.css` — 替换硬编码颜色为 CSS 变量
- `frontend/src/App.js` — 添加 AuthProvider、主题切换、新路由、Header 用户信息
- `frontend/src/config/api.js` — apiRequest 中自动附加 JWT token header

---

## Part 1: 白天模式主题

### Task 1: 定义 CSS 变量并添加 light 主题

**Files:**
- Modify: `frontend/src/index.css:1-25`

- [ ] **Step 1: 在 index.css 顶部添加 CSS 变量定义**

在 `body` 选择器之前插入 `:root` 变量定义：

```css
/* ===== 主题变量 ===== */
:root,
[data-theme="dark"] {
  --bg-primary: #141213;
  --bg-card: #1a1a1a;
  --bg-card-hover: #2a2a2a;
  --bg-input: #2a2a2a;
  --bg-header: #141213;
  --bg-gradient-start: #1a1a1a;
  --bg-gradient-end: #2a2a2a;
  --bg-tag: rgba(24, 144, 255, 0.15);
  --bg-tooltip: #1e1d1e;

  --text-primary: #fff;
  --text-secondary: rgba(255, 255, 255, 0.65);
  --text-tertiary: rgba(255, 255, 255, 0.45);
  --text-muted: #999;

  --border-primary: #333;
  --border-secondary: #2a2a2a;
  --border-input: #444;

  --color-up: #ff4d4f;
  --color-down: #52c41a;
  --color-accent: #1890ff;
  --color-warning: #ffa940;

  --shadow-card: 0 2px 8px rgba(0, 0, 0, 0.3);
  --menu-theme: dark;
}

[data-theme="light"] {
  --bg-primary: #f0f2f5;
  --bg-card: #ffffff;
  --bg-card-hover: #f5f5f5;
  --bg-input: #ffffff;
  --bg-header: #ffffff;
  --bg-gradient-start: #ffffff;
  --bg-gradient-end: #f5f5f5;
  --bg-tag: rgba(24, 144, 255, 0.08);
  --bg-tooltip: #ffffff;

  --text-primary: #1a1a1a;
  --text-secondary: rgba(0, 0, 0, 0.65);
  --text-tertiary: rgba(0, 0, 0, 0.45);
  --text-muted: #888;

  --border-primary: #e0e0e0;
  --border-secondary: #f0f0f0;
  --border-input: #d9d9d9;

  --color-up: #cf1322;
  --color-down: #389e0d;
  --color-accent: #1890ff;
  --color-warning: #fa8c16;

  --shadow-card: 0 2px 8px rgba(0, 0, 0, 0.08);
  --menu-theme: light;
}
```

- [ ] **Step 2: 将 body 和 #root 的硬编码颜色替换为变量**

```css
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

#root {
  min-height: 100vh;
  background-color: var(--bg-primary);
}

.ant-layout-content {
  background-color: var(--bg-primary);
}
```

- [ ] **Step 3: 逐步替换 index.css 中所有硬编码颜色为 CSS 变量**

主要替换规则：
- `#141213` → `var(--bg-primary)`
- `#1a1a1a` → `var(--bg-card)`
- `#2a2a2a` → `var(--bg-card-hover)` 或 `var(--bg-input)`
- `#333` / `#333333` → `var(--border-primary)`
- `#444` → `var(--border-input)`
- `#fff` / `#ffffff` / `color: white` → `var(--text-primary)`（仅文字颜色处）
- `rgba(255,255,255,0.5~0.8)` → `var(--text-secondary)`
- `#999` → `var(--text-muted)`

注意：**不替换** `#ff4d4f`（涨）、`#52c41a`（跌）、`#1890ff`（accent）等功能色，这些在两个主题下含义不变。

背景色替换示例：
- `.stock-header { background: linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 100%); }` → `background: linear-gradient(135deg, var(--bg-gradient-start) 0%, var(--bg-gradient-end) 100%);`
- `.ant-table-thead > tr > th { background: #2a2a2a; }` → `background: var(--bg-card-hover);`
- 所有 `border: 1px solid #333` → `border: 1px solid var(--border-primary)`

文字色替换示例：
- `.stock-card .ant-card-head-title { color: #fff; }` → `color: var(--text-primary);`

- [ ] **Step 4: 同样替换 4 个页面级 CSS 文件中的硬编码颜色**

对以下文件执行同样的替换：
- `frontend/src/pages/LimitUpEchelon/index.css`
- `frontend/src/pages/AuctionGrab/index.css`
- `frontend/src/pages/EmotionCycle/index.css`
- `frontend/src/pages/DragonTiger/index.css`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css frontend/src/pages/*/index.css
git commit -m "feat: convert hardcoded colors to CSS variables and add light theme"
```

### Task 2: 主题切换组件和集成

**Files:**
- Create: `frontend/src/components/ThemeToggle.js`
- Modify: `frontend/src/App.js`

- [ ] **Step 1: 创建 ThemeToggle 组件**

```jsx
// frontend/src/components/ThemeToggle.js
import React, { useState, useEffect } from 'react';

const THEME_KEY = 'niuniu_theme';

export function useTheme() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem(THEME_KEY) || 'dark';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  return { theme, toggleTheme };
}

export default function ThemeToggle({ theme, onToggle }) {
  return (
    <span
      onClick={onToggle}
      style={{
        cursor: 'pointer',
        fontSize: 20,
        padding: '0 12px',
        userSelect: 'none',
        lineHeight: '64px',
      }}
      title={theme === 'dark' ? '切换到白天模式' : '切换到黑夜模式'}
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </span>
  );
}
```

- [ ] **Step 2: 在 App.js 中集成主题切换**

在 App.js 的 Header 中添加 ThemeToggle 组件，Header 使用 flex 布局，左侧 Menu + 右侧 ThemeToggle：

```jsx
import ThemeToggle, { useTheme } from './components/ThemeToggle';

function App() {
  const { theme, toggleTheme } = useTheme();
  // ...existing code...

  return (
    <Layout className="layout" style={{ minHeight: '100vh' }}>
      <Header style={{
        padding: 0,
        background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border-secondary)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <Menu
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={navItems}
          onClick={handleMenuClick}
          style={{
            background: 'transparent',
            borderBottom: 'none',
            flex: 1,
          }}
          theme={theme === 'dark' ? 'dark' : 'light'}
        />
        <div style={{ display: 'flex', alignItems: 'center', paddingRight: 16 }}>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
      </Header>
      {/* ...rest unchanged... */}
    </Layout>
  );
}
```

- [ ] **Step 3: 验证主题切换功能**

Run: `cd ~/Github/NiuNIuNiu/frontend && npm start`

手动测试：
1. 页面默认为暗色主题
2. 点击太阳图标切换到白天模式，背景变浅、文字变深
3. 刷新页面后主题保持
4. 各页面（涨停梯队、龙虎榜等）颜色都跟随切换

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ThemeToggle.js frontend/src/App.js
git commit -m "feat: add theme toggle with sun/moon icon in header"
```

---

## Part 2: 后端认证系统

### Task 3: 数据库建表 + JWT 中间件

**Files:**
- Existing: `backend/migrations/create_user_auth_tables.sql` (已存在)
- Create: `backend/utils/auth_middleware.py`

- [ ] **Step 1: 执行数据库迁移**

```bash
cd ~/Github/NiuNIuNiu/backend
mysql -u root -p123456 stock < migrations/create_user_auth_tables.sql
```

验证表已创建：
```bash
mysql -u root -p123456 stock -e "SHOW TABLES LIKE 'users'; SHOW TABLES LIKE 'orders'; SHOW TABLES LIKE 'user_subscriptions';"
```

- [ ] **Step 2: 创建 JWT 中间件**

```python
# backend/utils/auth_middleware.py
"""JWT 认证中间件"""
import os
import logging
from functools import wraps
from flask import request, jsonify
import jwt
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get('JWT_SECRET', 'niuniu-secret')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_DAYS = 7


def generate_token(user_id, username, role='user'):
    """生成 JWT token"""
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'exp': datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token):
    """解码 JWT token，成功返回 payload，失败返回 None"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning('Token 已过期')
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f'Token 无效: {e}')
        return None


def login_required(f):
    """需要登录的接口装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': '未登录'}), 401
        token = auth_header[7:]
        payload = decode_token(token)
        if payload is None:
            return jsonify({'success': False, 'message': '登录已过期，请重新登录'}), 401
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated
```

- [ ] **Step 3: Commit**

```bash
git add backend/utils/auth_middleware.py
git commit -m "feat: add JWT auth middleware with token generation and validation"
```

### Task 4: 注册和登录 API

**Files:**
- Create: `backend/routes/auth.py`

- [ ] **Step 1: 创建 auth.py**

```python
# backend/routes/auth.py
"""认证相关 API：注册、登录、修改密码"""
import logging
from flask import Blueprint, request
from werkzeug.security import generate_password_hash, check_password_hash
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query, execute_write
from utils.auth_middleware import generate_token, login_required

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    body = request.get_json(silent=True) or {}
    username = (body.get('username') or '').strip()
    password = body.get('password', '')
    phone = (body.get('phone') or '').strip() or None

    if not username or len(username) < 2 or len(username) > 20:
        return v1_error_response('用户名需要2-20个字符')
    if not password or len(password) < 6:
        return v1_error_response('密码至少6个字符')

    # 检查用户名是否已存在
    existing = execute_query(
        'SELECT id FROM users WHERE username = %s', (username,)
    )
    if existing:
        return v1_error_response('用户名已存在')

    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    try:
        execute_write(
            'INSERT INTO users (username, password_hash, phone) VALUES (%s, %s, %s)',
            (username, password_hash, phone)
        )
    except Exception as e:
        logger.error(f'注册失败: {e}')
        return v1_error_response('注册失败，请稍后重试')

    # 注册成功后自动登录
    user = execute_query(
        'SELECT id, username, role FROM users WHERE username = %s', (username,)
    )
    if user:
        u = user[0]
        token = generate_token(u['id'], u['username'], u['role'])
        return v1_success_response(data={
            'token': token,
            'user': {'id': u['id'], 'username': u['username'], 'role': u['role']}
        }, message='注册成功')

    return v1_error_response('注册异常')


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    body = request.get_json(silent=True) or {}
    username = (body.get('username') or '').strip()
    password = body.get('password', '')

    if not username or not password:
        return v1_error_response('请输入用户名和密码')

    user = execute_query(
        'SELECT id, username, password_hash, role FROM users WHERE username = %s',
        (username,)
    )
    if not user:
        return v1_error_response('用户名或密码错误')

    u = user[0]
    if not check_password_hash(u['password_hash'], password):
        return v1_error_response('用户名或密码错误')

    token = generate_token(u['id'], u['username'], u['role'])
    return v1_success_response(data={
        'token': token,
        'user': {'id': u['id'], 'username': u['username'], 'role': u['role']}
    }, message='登录成功')


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    """修改密码"""
    body = request.get_json(silent=True) or {}
    old_password = body.get('old_password', '')
    new_password = body.get('new_password', '')

    if not old_password or not new_password:
        return v1_error_response('请输入旧密码和新密码')
    if len(new_password) < 6:
        return v1_error_response('新密码至少6个字符')

    user_id = request.current_user['user_id']
    user = execute_query(
        'SELECT password_hash FROM users WHERE id = %s', (user_id,)
    )
    if not user:
        return v1_error_response('用户不存在')

    if not check_password_hash(user[0]['password_hash'], old_password):
        return v1_error_response('旧密码错误')

    new_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    execute_write(
        'UPDATE users SET password_hash = %s WHERE id = %s',
        (new_hash, user_id)
    )
    return v1_success_response(message='密码修改成功')
```

- [ ] **Step 2: Commit**

```bash
git add backend/routes/auth.py
git commit -m "feat: add auth routes - register, login, change password"
```

### Task 5: 用户信息和订单 API

**Files:**
- Create: `backend/routes/user.py`
- Create: `backend/routes/orders.py`

- [ ] **Step 1: 创建 user.py**

```python
# backend/routes/user.py
"""用户信息 API"""
import logging
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query
from utils.auth_middleware import login_required

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__)


@user_bp.route('/api/user/profile', methods=['GET'])
@login_required
def get_profile():
    """获取用户信息及 VIP 状态"""
    user_id = request.current_user['user_id']

    user = execute_query(
        'SELECT id, username, phone, role, created_at FROM users WHERE id = %s',
        (user_id,)
    )
    if not user:
        return v1_error_response('用户不存在')

    u = user[0]

    # 查询有效订阅
    sub = execute_query(
        'SELECT plan_type, end_time FROM user_subscriptions '
        'WHERE user_id = %s AND is_active = 1 AND end_time > NOW() '
        'ORDER BY end_time DESC LIMIT 1',
        (user_id,)
    )

    vip_info = None
    if sub:
        vip_info = {
            'plan_type': sub[0]['plan_type'],
            'end_time': sub[0]['end_time'].strftime('%Y-%m-%d %H:%M:%S') if sub[0]['end_time'] else None,
        }

    return v1_success_response(data={
        'id': u['id'],
        'username': u['username'],
        'phone': u['phone'],
        'role': u['role'],
        'created_at': u['created_at'].strftime('%Y-%m-%d %H:%M:%S') if u['created_at'] else None,
        'vip': vip_info,
    })
```

- [ ] **Step 2: 创建 orders.py**

```python
# backend/routes/orders.py
"""订单管理 API"""
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query, execute_write
from utils.auth_middleware import login_required

logger = logging.getLogger(__name__)

orders_bp = Blueprint('orders', __name__)

PLANS = {
    'daily':     {'name': '日度VIP',  'amount': 0.01,   'days': 1},
    'monthly':   {'name': '月度VIP',  'amount': 380.00, 'days': 30},
    'quarterly': {'name': '季度VIP',  'amount': 900.00, 'days': 90},
    'semi':      {'name': '半年VIP',  'amount': 1600.00, 'days': 180},
    'annual':    {'name': '年度VIP',  'amount': 2500.00, 'days': 365},
}


def _gen_order_no():
    """生成订单号: NN + 年月日时分秒 + 6位随机数"""
    import random
    now = datetime.now().strftime('%Y%m%d%H%M%S')
    rand = f'{random.randint(0, 999999):06d}'
    return f'NN{now}{rand}'


@orders_bp.route('/api/orders', methods=['GET'])
@login_required
def list_orders():
    """订单列表（分页）"""
    user_id = request.current_user['user_id']
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    offset = (page - 1) * page_size

    total_row = execute_query(
        'SELECT COUNT(*) as cnt FROM orders WHERE user_id = %s', (user_id,)
    )
    total = total_row[0]['cnt'] if total_row else 0

    rows = execute_query(
        'SELECT order_no, plan_type, amount, status, created_at '
        'FROM orders WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s',
        (user_id, page_size, offset)
    )
    items = []
    for r in rows:
        plan = PLANS.get(r['plan_type'], {})
        items.append({
            'order_no': r['order_no'],
            'plan_name': plan.get('name', r['plan_type']),
            'plan_type': r['plan_type'],
            'amount': float(r['amount']),
            'status': r['status'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M') if r['created_at'] else None,
        })

    return v1_success_response(data={
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
    })


@orders_bp.route('/api/orders/create', methods=['POST'])
@login_required
def create_order():
    """创建订单"""
    body = request.get_json(silent=True) or {}
    plan_type = body.get('plan_type', '')
    user_id = request.current_user['user_id']

    if plan_type not in PLANS:
        return v1_error_response('无效的套餐类型')

    plan = PLANS[plan_type]
    order_no = _gen_order_no()

    execute_write(
        'INSERT INTO orders (order_no, user_id, plan_type, amount, status) VALUES (%s, %s, %s, %s, %s)',
        (order_no, user_id, plan_type, plan['amount'], 'pending')
    )

    return v1_success_response(data={
        'order_no': order_no,
        'plan_name': plan['name'],
        'amount': plan['amount'],
    }, message='订单创建成功')


@orders_bp.route('/api/orders/mock-pay', methods=['POST'])
@login_required
def mock_pay():
    """模拟支付（测试用）：激活 1 天 VIP"""
    body = request.get_json(silent=True) or {}
    order_no = body.get('order_no', '')
    user_id = request.current_user['user_id']

    if not order_no:
        return v1_error_response('缺少订单号')

    order = execute_query(
        'SELECT id, plan_type, status FROM orders WHERE order_no = %s AND user_id = %s',
        (order_no, user_id)
    )
    if not order:
        return v1_error_response('订单不存在')
    if order[0]['status'] == 'paid':
        return v1_error_response('订单已支付')

    plan_type = order[0]['plan_type']
    plan = PLANS.get(plan_type, PLANS['daily'])

    # 更新订单状态
    execute_write(
        'UPDATE orders SET status = %s WHERE order_no = %s',
        ('paid', order_no)
    )

    # 创建/延长订阅
    now = datetime.now()
    existing_sub = execute_query(
        'SELECT id, end_time FROM user_subscriptions '
        'WHERE user_id = %s AND is_active = 1 AND end_time > NOW() '
        'ORDER BY end_time DESC LIMIT 1',
        (user_id,)
    )
    if existing_sub:
        # 在现有订阅基础上延长
        start = existing_sub[0]['end_time']
        end = start + timedelta(days=plan['days'])
        execute_write(
            'UPDATE user_subscriptions SET end_time = %s, plan_type = %s WHERE id = %s',
            (end, plan_type, existing_sub[0]['id'])
        )
    else:
        end = now + timedelta(days=plan['days'])
        execute_write(
            'INSERT INTO user_subscriptions (user_id, plan_type, start_time, end_time) VALUES (%s, %s, %s, %s)',
            (user_id, plan_type, now, end)
        )

    return v1_success_response(message='支付成功，VIP 已激活')
```

- [ ] **Step 3: Commit**

```bash
git add backend/routes/user.py backend/routes/orders.py
git commit -m "feat: add user profile and order management APIs"
```

### Task 6: 安装后端依赖 + 验证后端启动

- [ ] **Step 1: 安装 PyJWT**

```bash
cd ~/Github/NiuNIuNiu/backend
pip install PyJWT
```

- [ ] **Step 2: 执行数据库迁移**

```bash
mysql -u root -p123456 stock < migrations/create_user_auth_tables.sql
```

- [ ] **Step 3: 重启后端并验证 API**

```bash
cd ~/Github/NiuNIuNiu && bash start.sh
```

测试注册：
```bash
curl -s -X POST http://localhost:9001/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"testuser","password":"123456"}' | python3 -m json.tool
```

测试登录：
```bash
curl -s -X POST http://localhost:9001/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"testuser","password":"123456"}' | python3 -m json.tool
```

测试 profile（使用返回的 token）：
```bash
TOKEN="<上一步返回的token>"
curl -s http://localhost:9001/api/user/profile \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

- [ ] **Step 4: Commit** (如有 requirements.txt 更新)

```bash
pip freeze | grep -i pyjwt >> requirements.txt
git add requirements.txt
git commit -m "chore: add PyJWT dependency"
```

---

## Part 3: 前端认证系统

### Task 7: API 层添加 Token 支持

**Files:**
- Modify: `frontend/src/config/api.js`

- [ ] **Step 1: 修改 apiRequest 自动附加 Authorization header**

在 `apiRequest` 函数的 `config` 构建处，添加 token：

```javascript
// 在 const config = { ... } 之前添加：
const token = localStorage.getItem('niuniu_token');
const authHeaders = token ? { 'Authorization': `Bearer ${token}` } : {};

const config = {
  timeout: apiConfig.timeout,
  headers: {
    'Content-Type': 'application/json',
    ...authHeaders,
    ...options.headers,
  },
  ...options,
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/config/api.js
git commit -m "feat: auto-attach JWT token to API requests"
```

### Task 8: AuthContext 认证状态管理

**Files:**
- Create: `frontend/src/context/AuthContext.js`

- [ ] **Step 1: 创建 AuthContext**

```jsx
// frontend/src/context/AuthContext.js
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../config/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem('niuniu_token');
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await api.get('/api/user/profile');
      if (res.success && res.data) {
        setUser(res.data);
      } else {
        localStorage.removeItem('niuniu_token');
        setUser(null);
      }
    } catch {
      localStorage.removeItem('niuniu_token');
      setUser(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (username, password) => {
    const res = await api.post('/api/auth/login', { username, password });
    if (res.success && res.data?.token) {
      localStorage.setItem('niuniu_token', res.data.token);
      await refreshUser();
      return { success: true };
    }
    return { success: false, message: res.message || '登录失败' };
  };

  const register = async (username, password, phone) => {
    const res = await api.post('/api/auth/register', { username, password, phone });
    if (res.success && res.data?.token) {
      localStorage.setItem('niuniu_token', res.data.token);
      await refreshUser();
      return { success: true };
    }
    return { success: false, message: res.message || '注册失败' };
  };

  const logout = () => {
    localStorage.removeItem('niuniu_token');
    setUser(null);
  };

  const isVip = !!(user?.vip?.end_time && new Date(user.vip.end_time) > new Date());

  return (
    <AuthContext.Provider value={{ user, loading, isVip, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/context/AuthContext.js
git commit -m "feat: add AuthContext with login, register, logout, VIP status"
```

### Task 9: 注册页面

**Files:**
- Create: `frontend/src/pages/Register/index.js`
- Create: `frontend/src/pages/Register/index.css`

- [ ] **Step 1: 创建注册页面样式**

```css
/* frontend/src/pages/Register/index.css */
.register-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 64px);
  background: var(--bg-primary);
}

.register-card {
  width: 400px;
  padding: 40px;
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.register-title {
  text-align: center;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.register-subtitle {
  text-align: center;
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 32px;
}

.register-card .ant-input {
  background: var(--bg-input);
  border-color: var(--border-input);
  color: var(--text-primary);
  height: 42px;
}

.register-card .ant-input:focus,
.register-card .ant-input-focused {
  border-color: var(--color-accent);
}

.register-card .ant-input::placeholder {
  color: var(--text-tertiary);
}

.register-btn {
  width: 100%;
  height: 42px;
  font-size: 16px;
}

.register-footer {
  text-align: center;
  margin-top: 16px;
  color: var(--text-muted);
  font-size: 14px;
}

.register-footer a {
  color: var(--color-accent);
}
```

- [ ] **Step 2: 创建注册页面组件**

```jsx
// frontend/src/pages/Register/index.js
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Input, Button, message } from 'antd';
import { useAuth } from '../../context/AuthContext';
import './index.css';

export default function Register() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleRegister = async () => {
    if (!username.trim() || username.trim().length < 2) {
      return message.error('用户名至少2个字符');
    }
    if (!password || password.length < 6) {
      return message.error('密码至少6个字符');
    }
    if (password !== confirmPwd) {
      return message.error('两次密码不一致');
    }

    setLoading(true);
    const result = await register(username.trim(), password, phone.trim() || undefined);
    setLoading(false);

    if (result.success) {
      message.success('注册成功');
      navigate('/stock-dashboard');
    } else {
      message.error(result.message);
    }
  };

  return (
    <div className="register-container">
      <div className="register-card">
        <div className="register-title">创建账号</div>
        <div className="register-subtitle">注册 NiuNiuNiu 股票分析平台</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Input
            placeholder="用户名（2-20个字符）"
            value={username}
            onChange={e => setUsername(e.target.value)}
            onPressEnter={handleRegister}
          />
          <Input.Password
            placeholder="密码（至少6个字符）"
            value={password}
            onChange={e => setPassword(e.target.value)}
          />
          <Input.Password
            placeholder="确认密码"
            value={confirmPwd}
            onChange={e => setConfirmPwd(e.target.value)}
          />
          <Input
            placeholder="手机号（可选）"
            value={phone}
            onChange={e => setPhone(e.target.value)}
            onPressEnter={handleRegister}
          />
          <Button
            type="primary"
            className="register-btn"
            loading={loading}
            onClick={handleRegister}
          >
            注册
          </Button>
          <div className="register-footer">
            已有账号？<Link to="/login">去登录</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Register/
git commit -m "feat: add register page with username, password, phone fields"
```

### Task 10: 登录页面

**Files:**
- Create: `frontend/src/pages/Login/index.js`
- Create: `frontend/src/pages/Login/index.css`

- [ ] **Step 1: 创建登录页样式**

```css
/* frontend/src/pages/Login/index.css */
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 64px);
  background: var(--bg-primary);
}

.login-card {
  width: 400px;
  padding: 40px;
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.login-title {
  text-align: center;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.login-subtitle {
  text-align: center;
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 32px;
}

.login-card .ant-input {
  background: var(--bg-input);
  border-color: var(--border-input);
  color: var(--text-primary);
  height: 42px;
}

.login-card .ant-input:focus,
.login-card .ant-input-focused {
  border-color: var(--color-accent);
}

.login-card .ant-input::placeholder {
  color: var(--text-tertiary);
}

.login-btn {
  width: 100%;
  height: 42px;
  font-size: 16px;
}

.login-footer {
  text-align: center;
  margin-top: 16px;
  color: var(--text-muted);
  font-size: 14px;
}

.login-footer a {
  color: var(--color-accent);
}
```

- [ ] **Step 2: 创建登录页组件**

```jsx
// frontend/src/pages/Login/index.js
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Input, Button, message } from 'antd';
import { useAuth } from '../../context/AuthContext';
import './index.css';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      return message.error('请输入用户名和密码');
    }

    setLoading(true);
    const result = await login(username.trim(), password);
    setLoading(false);

    if (result.success) {
      message.success('登录成功');
      navigate('/stock-dashboard');
    } else {
      message.error(result.message);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-title">登录</div>
        <div className="login-subtitle">NiuNiuNiu 股票分析平台</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Input
            placeholder="用户名"
            value={username}
            onChange={e => setUsername(e.target.value)}
            onPressEnter={handleLogin}
          />
          <Input.Password
            placeholder="密码"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onPressEnter={handleLogin}
          />
          <Button
            type="primary"
            className="login-btn"
            loading={loading}
            onClick={handleLogin}
          >
            登录
          </Button>
          <div className="login-footer">
            没有账号？<Link to="/register">立即注册</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Login/
git commit -m "feat: add login page"
```

### Task 11: PermissionGuard 组件

**Files:**
- Create: `frontend/src/components/PermissionGuard.js`

- [ ] **Step 1: 创建 VIP 权限守卫组件**

```jsx
// frontend/src/components/PermissionGuard.js
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from 'antd';
import { useAuth } from '../context/AuthContext';

export default function PermissionGuard({ children }) {
  const { user, isVip } = useAuth();
  const navigate = useNavigate();

  if (!user) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: 'calc(100vh - 64px)',
        background: 'var(--bg-primary)', color: 'var(--text-primary)',
      }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔒</div>
        <div style={{ fontSize: 18, marginBottom: 8 }}>请先登录</div>
        <div style={{ color: 'var(--text-muted)', marginBottom: 24 }}>登录后即可使用此功能</div>
        <Button type="primary" onClick={() => navigate('/login')}>去登录</Button>
      </div>
    );
  }

  if (!isVip) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: 'calc(100vh - 64px)',
        background: 'var(--bg-primary)', color: 'var(--text-primary)',
      }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔒</div>
        <div style={{ fontSize: 18, marginBottom: 8 }}>此功能需要 VIP 权限</div>
        <div style={{ color: 'var(--text-muted)', marginBottom: 24 }}>
          开通 VIP 后即可解锁全部分析功能
        </div>
        <Button type="primary" onClick={() => navigate('/permission-center')}>
          立即开通
        </Button>
      </div>
    );
  }

  return children;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/PermissionGuard.js
git commit -m "feat: add PermissionGuard component for VIP-gated pages"
```

### Task 12: 用户中心页面

**Files:**
- Create: `frontend/src/pages/UserCenter/index.js`
- Create: `frontend/src/pages/UserCenter/index.css`

- [ ] **Step 1: 创建用户中心样式**

```css
/* frontend/src/pages/UserCenter/index.css */
.user-center-container {
  padding: 24px;
  background: var(--bg-primary);
  min-height: calc(100vh - 64px);
  max-width: 800px;
  margin: 0 auto;
}

.uc-section {
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 16px;
}

.uc-section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-secondary);
}

.uc-info-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 14px;
}

.uc-info-label {
  color: var(--text-muted);
}

.uc-info-value {
  color: var(--text-primary);
}

.uc-vip-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.uc-vip-active {
  background: rgba(255, 169, 64, 0.15);
  color: #ffa940;
}

.uc-vip-inactive {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-muted);
}

.uc-pwd-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 400px;
}

.uc-pwd-form .ant-input {
  background: var(--bg-input);
  border-color: var(--border-input);
  color: var(--text-primary);
}

.uc-order-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-secondary);
  font-size: 13px;
}

.uc-order-item:last-child {
  border-bottom: none;
}

.uc-order-status-paid {
  color: #52c41a;
}

.uc-order-status-pending {
  color: #ffa940;
}
```

- [ ] **Step 2: 创建用户中心组件**

```jsx
// frontend/src/pages/UserCenter/index.js
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input, Button, message, Spin } from 'antd';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../config/api';
import './index.css';

export default function UserCenter() {
  const { user, isVip, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [oldPwd, setOldPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [pwdLoading, setPwdLoading] = useState(false);
  const [orders, setOrders] = useState([]);
  const [ordersLoading, setOrdersLoading] = useState(false);

  useEffect(() => {
    if (!user) {
      navigate('/login');
      return;
    }
    fetchOrders();
  }, [user, navigate]);

  const fetchOrders = async () => {
    setOrdersLoading(true);
    try {
      const res = await api.get('/api/orders?page=1&page_size=20');
      if (res.success) {
        setOrders(res.data?.items || []);
      }
    } catch { /* ignore */ }
    setOrdersLoading(false);
  };

  const handleChangePwd = async () => {
    if (!oldPwd || !newPwd) return message.error('请填写完整');
    if (newPwd.length < 6) return message.error('新密码至少6个字符');
    if (newPwd !== confirmPwd) return message.error('两次密码不一致');

    setPwdLoading(true);
    try {
      const res = await api.post('/api/auth/change-password', {
        old_password: oldPwd,
        new_password: newPwd,
      });
      if (res.success) {
        message.success('密码修改成功');
        setOldPwd(''); setNewPwd(''); setConfirmPwd('');
      } else {
        message.error(res.message);
      }
    } catch {
      message.error('修改失败');
    }
    setPwdLoading(false);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  if (!user) return null;

  return (
    <div className="user-center-container">
      <div className="uc-section">
        <div className="uc-section-title">个人信息</div>
        <div className="uc-info-row">
          <span className="uc-info-label">用户名</span>
          <span className="uc-info-value">{user.username}</span>
        </div>
        <div className="uc-info-row">
          <span className="uc-info-label">手机号</span>
          <span className="uc-info-value">{user.phone || '未设置'}</span>
        </div>
        <div className="uc-info-row">
          <span className="uc-info-label">VIP 状态</span>
          <span className="uc-info-value">
            {isVip ? (
              <span className="uc-vip-badge uc-vip-active">
                VIP · 到期 {user.vip.end_time?.split(' ')[0]}
              </span>
            ) : (
              <span className="uc-vip-badge uc-vip-inactive">未开通</span>
            )}
          </span>
        </div>
        <div className="uc-info-row">
          <span className="uc-info-label">注册时间</span>
          <span className="uc-info-value">{user.created_at}</span>
        </div>
        <div style={{ marginTop: 16 }}>
          <Button danger onClick={handleLogout}>退出登录</Button>
        </div>
      </div>

      <div className="uc-section">
        <div className="uc-section-title">修改密码</div>
        <div className="uc-pwd-form">
          <Input.Password placeholder="旧密码" value={oldPwd} onChange={e => setOldPwd(e.target.value)} />
          <Input.Password placeholder="新密码（至少6位）" value={newPwd} onChange={e => setNewPwd(e.target.value)} />
          <Input.Password placeholder="确认新密码" value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)} />
          <Button type="primary" loading={pwdLoading} onClick={handleChangePwd} style={{ width: 120 }}>
            确认修改
          </Button>
        </div>
      </div>

      <div className="uc-section">
        <div className="uc-section-title">订单记录</div>
        {ordersLoading ? (
          <Spin />
        ) : orders.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 24 }}>暂无订单</div>
        ) : (
          orders.map(o => (
            <div key={o.order_no} className="uc-order-item">
              <div>
                <div style={{ color: 'var(--text-primary)' }}>{o.plan_name}</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{o.order_no}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: 'var(--text-primary)' }}>¥{o.amount}</div>
                <div className={o.status === 'paid' ? 'uc-order-status-paid' : 'uc-order-status-pending'}>
                  {o.status === 'paid' ? '已支付' : '待支付'}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/UserCenter/
git commit -m "feat: add user center page with profile, password change, and order history"
```

### Task 13: 权限中心页面

**Files:**
- Create: `frontend/src/pages/PermissionCenter/index.js`
- Create: `frontend/src/pages/PermissionCenter/index.css`

- [ ] **Step 1: 创建权限中心样式**

```css
/* frontend/src/pages/PermissionCenter/index.css */
.permission-center-container {
  padding: 24px;
  background: var(--bg-primary);
  min-height: calc(100vh - 64px);
  max-width: 900px;
  margin: 0 auto;
}

.pc-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  text-align: center;
  margin-bottom: 8px;
}

.pc-subtitle {
  text-align: center;
  color: var(--text-muted);
  margin-bottom: 32px;
}

.pc-plans {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.pc-plan-card {
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, transform 0.2s;
}

.pc-plan-card:hover {
  border-color: var(--color-accent);
  transform: translateY(-2px);
}

.pc-plan-card.selected {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 1px var(--color-accent);
}

.pc-plan-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.pc-plan-price {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-accent);
  margin-bottom: 4px;
}

.pc-plan-unit {
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 16px;
}

.pc-plan-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 8px;
  font-size: 12px;
  background: rgba(24, 144, 255, 0.1);
  color: var(--color-accent);
}
```

- [ ] **Step 2: 创建权限中心组件**

```jsx
// frontend/src/pages/PermissionCenter/index.js
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Modal, message } from 'antd';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../config/api';
import './index.css';

const PLANS = [
  { key: 'monthly',   name: '月度VIP',  price: 380,   unit: '/月',  days: 30 },
  { key: 'quarterly', name: '季度VIP',  price: 900,   unit: '/季',  days: 90,  badge: '热门' },
  { key: 'semi',      name: '半年VIP',  price: 1600,  unit: '/半年', days: 180 },
  { key: 'annual',    name: '年度VIP',  price: 2500,  unit: '/年',  days: 365, badge: '最划算' },
];

export default function PermissionCenter() {
  const { user, isVip, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [selected, setSelected] = useState('quarterly');
  const [loading, setLoading] = useState(false);

  if (!user) {
    navigate('/login');
    return null;
  }

  const handlePurchase = async () => {
    setLoading(true);
    try {
      // 创建订单
      const createRes = await api.post('/api/orders/create', { plan_type: selected });
      if (!createRes.success) {
        message.error(createRes.message);
        setLoading(false);
        return;
      }

      const orderNo = createRes.data.order_no;

      // 弹出确认（模拟支付）
      Modal.confirm({
        title: '确认支付',
        content: `订单号: ${orderNo}\n套餐: ${createRes.data.plan_name}\n金额: ¥${createRes.data.amount}\n\n（测试环境：点击确认将模拟支付）`,
        okText: '确认支付',
        cancelText: '取消',
        onOk: async () => {
          const payRes = await api.post('/api/orders/mock-pay', { order_no: orderNo });
          if (payRes.success) {
            message.success('支付成功，VIP 已激活！');
            await refreshUser();
          } else {
            message.error(payRes.message);
          }
        },
      });
    } catch {
      message.error('操作失败');
    }
    setLoading(false);
  };

  return (
    <div className="permission-center-container">
      <div className="pc-title">开通 VIP</div>
      <div className="pc-subtitle">
        {isVip
          ? `当前 VIP 有效期至 ${user.vip?.end_time?.split(' ')[0]}，可续费延长`
          : '解锁情绪周期、竞价抢筹等高级分析功能'}
      </div>

      <div className="pc-plans">
        {PLANS.map(plan => (
          <div
            key={plan.key}
            className={`pc-plan-card ${selected === plan.key ? 'selected' : ''}`}
            onClick={() => setSelected(plan.key)}
          >
            <div className="pc-plan-name">{plan.name}</div>
            <div className="pc-plan-price">¥{plan.price}</div>
            <div className="pc-plan-unit">{plan.days}天</div>
            {plan.badge && <span className="pc-plan-badge">{plan.badge}</span>}
          </div>
        ))}
      </div>

      <div style={{ textAlign: 'center', marginTop: 32 }}>
        <Button
          type="primary"
          size="large"
          loading={loading}
          onClick={handlePurchase}
          style={{ width: 200, height: 44, fontSize: 16 }}
        >
          立即开通
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/PermissionCenter/
git commit -m "feat: add permission center page with subscription plan selection"
```

### Task 14: 集成到 App.js — 路由、AuthProvider、Header 用户信息

**Files:**
- Modify: `frontend/src/App.js`

- [ ] **Step 1: 更新 App.js 完整代码**

```jsx
// frontend/src/App.js
import React from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Alert, Menu, Button } from 'antd';
import { useAtom } from 'jotai';
import Home from './pages/Home';
import StockDashboard from './pages/StockDashboard';
import EmotionCycle from './pages/EmotionCycle';
import LimitUpEchelon from './pages/LimitUpEchelon';
import AuctionGrab from './pages/AuctionGrab';
import DragonTiger from './pages/DragonTiger';
import Login from './pages/Login';
import Register from './pages/Register';
import UserCenter from './pages/UserCenter';
import PermissionCenter from './pages/PermissionCenter';
import PermissionGuard from './components/PermissionGuard';
import ThemeToggle, { useTheme } from './components/ThemeToggle';
import { useAuth } from './context/AuthContext';
import { errorAtom } from './store/atoms';

const { Content, Header } = Layout;

const navItems = [
  { key: '/stock-dashboard', label: '个股分析' },
  { key: '/limit-up-echelon', label: '涨停梯队' },
  { key: '/dragon-tiger', label: '核心游资' },
  { key: '/emotion-cycle', label: '情绪周期' },
  { key: '/auction-grab', label: '竞价抢筹' },
];

function AppContent() {
  const [error, setError] = useAtom(errorAtom);
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const { user, loading } = useAuth();

  const handleMenuClick = ({ key }) => {
    navigate(key);
  };

  if (loading) return null;

  return (
    <Layout className="layout" style={{ minHeight: '100vh' }}>
      <Header style={{
        padding: 0,
        background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border-secondary)',
        display: 'flex',
        alignItems: 'center',
      }}>
        <Menu
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={navItems}
          onClick={handleMenuClick}
          style={{ background: 'transparent', borderBottom: 'none', flex: 1 }}
          theme={theme === 'dark' ? 'dark' : 'light'}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingRight: 16 }}>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          {user ? (
            <span
              style={{ color: 'var(--text-primary)', cursor: 'pointer', fontSize: 14 }}
              onClick={() => navigate('/user-center')}
            >
              {user.username}
            </span>
          ) : (
            <Button size="small" type="primary" onClick={() => navigate('/login')}>
              登录
            </Button>
          )}
        </div>
      </Header>
      <Content>
        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
            style={{
              position: 'fixed', top: 20, left: '50%',
              transform: 'translateX(-50%)', zIndex: 9999, maxWidth: '600px'
            }}
          />
        )}
        <Routes>
          <Route path="/" element={<Navigate to="/stock-dashboard" replace />} />
          <Route path="/home" element={<Home />} />
          <Route path="/stock-dashboard" element={<StockDashboard />} />
          <Route path="/limit-up-echelon" element={<LimitUpEchelon />} />
          <Route path="/dragon-tiger" element={<DragonTiger />} />
          <Route path="/emotion-cycle" element={
            <PermissionGuard><EmotionCycle /></PermissionGuard>
          } />
          <Route path="/auction-grab" element={
            <PermissionGuard><AuctionGrab /></PermissionGuard>
          } />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/user-center" element={<UserCenter />} />
          <Route path="/permission-center" element={<PermissionCenter />} />
          <Route path="*" element={<Navigate to="/stock-dashboard" replace />} />
        </Routes>
      </Content>
    </Layout>
  );
}

export default function App() {
  return <AppContent />;
}
```

- [ ] **Step 2: 在 index.js 中包裹 AuthProvider**

修改 `frontend/src/index.js`，在 `<BrowserRouter>` 内层添加 `<AuthProvider>`：

```jsx
import { AuthProvider } from './context/AuthContext';

// 在渲染树中:
<BrowserRouter>
  <AuthProvider>
    <App />
  </AuthProvider>
</BrowserRouter>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.js frontend/src/index.js
git commit -m "feat: integrate auth system - routes, AuthProvider, header user info, VIP guards"
```

---

## Part 4: 验证

### Task 15: 端到端验证

- [ ] **Step 1: 重启前后端**

```bash
cd ~/Github/NiuNIuNiu && bash start.sh
cd ~/Github/NiuNIuNiu/frontend && npm start
```

- [ ] **Step 2: 手动测试清单**

1. 主题切换：点击太阳/月亮图标，全站颜色切换，刷新后保持
2. 注册：访问 /register，创建新用户
3. 登录：访问 /login，用刚注册的账号登录
4. Header 显示用户名，点击跳转用户中心
5. 未登录访问情绪周期/竞价抢筹，显示"请先登录"
6. 登录后无 VIP 访问情绪周期/竞价抢筹，显示"需要 VIP"
7. 在权限中心购买 VIP（mock-pay）
8. 购买后再访问情绪周期/竞价抢筹，正常显示
9. 用户中心修改密码、查看订单

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "feat: complete light theme and user auth system implementation"
```
