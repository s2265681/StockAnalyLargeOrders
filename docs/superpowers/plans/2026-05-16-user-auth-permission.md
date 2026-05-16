# 用户中心 + 权限管理 + 微信支付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为股票分析平台增加完整的用户认证、会员权限体系和微信支付（Mock）。

**Architecture:** 后端新增 auth/user/orders 三个 Flask Blueprint，用 JWT 鉴权，pymysql 写三张新表。前端用 React Context 管理登录态，新增 Login / UserCenter / PermissionCenter 三个页面，非 VIP 用户访问受保护功能时显示升级遮罩。

**Tech Stack:** Flask, PyJWT, Werkzeug(password_hash), pymysql, React 18, Ant Design 5, React Context API

---

## File Map

### 后端新建
- `backend/migrations/create_user_auth_tables.sql` — 3张新表 + 初始admin账户
- `backend/utils/auth_middleware.py` — `@require_auth` JWT装饰器
- `backend/routes/auth.py` — 登录/登出/改密码
- `backend/routes/user.py` — 用户信息
- `backend/routes/orders.py` — 订单列表/创建/mock-pay

### 后端修改
- `backend/requirements.txt` — 添加 PyJWT
- `backend/routes/__init__.py` — 导出3个新Blueprint
- `backend/app.py` — 注册3个新Blueprint

### 前端新建
- `frontend/src/context/AuthContext.js` — 全局认证状态
- `frontend/src/services/auth.js` — 认证API调用
- `frontend/src/components/PermissionGuard.js` — 权限遮罩
- `frontend/src/pages/Login/index.js` — 登录页
- `frontend/src/pages/UserCenter/index.js` — 用户中心
- `frontend/src/pages/UserCenter/index.css` — 样式
- `frontend/src/pages/PermissionCenter/index.js` — 权限中心
- `frontend/src/pages/PermissionCenter/index.css` — 样式

### 前端修改
- `frontend/src/App.js` — AuthProvider包裹、新路由、Header改造、受保护页面加Guard

---

## Task 1: 数据库迁移 + 初始数据

**Files:**
- Create: `backend/migrations/create_user_auth_tables.sql`

- [ ] **Step 1: 创建迁移SQL文件**

```sql
-- backend/migrations/create_user_auth_tables.sql
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  role ENUM('admin','user') DEFAULT 'user',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_no VARCHAR(26) NOT NULL UNIQUE,
  user_id INT NOT NULL,
  plan_type ENUM('daily','monthly','quarterly','semi','annual') NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  status ENUM('pending','paid') DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  INDEX idx_order_no (order_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_subscriptions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  plan_type ENUM('daily','monthly','quarterly','semi','annual') NOT NULL,
  start_time DATETIME NOT NULL,
  end_time DATETIME NOT NULL,
  is_active TINYINT(1) DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 初始管理员（密码 admin123，werkzeug pbkdf2:sha256 hash）
INSERT IGNORE INTO users (username, password_hash, phone, role)
VALUES ('admin', 'pbkdf2:sha256:260000$salt$hash_placeholder', NULL, 'admin');
```

- [ ] **Step 2: 执行迁移（手动插入admin账户会在Task 2中由Python生成hash后执行）**

注意：admin账户密码hash需在Task 2安装werkzeug后动态生成，此处SQL文件仅建表。

- [ ] **Step 3: 执行建表**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
mysql -u root -p123456 stock < migrations/create_user_auth_tables.sql
```

Expected: 无报错，创建3张表

- [ ] **Step 4: commit**

```bash
git add backend/migrations/create_user_auth_tables.sql
git commit -m "feat: add user auth tables migration"
```

---

## Task 2: 安装 PyJWT + 后端 JWT 中间件

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/utils/auth_middleware.py`

- [ ] **Step 1: 安装 PyJWT**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend && source venv/bin/activate && pip install PyJWT
```

Expected: Successfully installed PyJWT-2.x.x

- [ ] **Step 2: 更新 requirements.txt**

在 `backend/requirements.txt` 末尾追加：
```
PyJWT>=2.8.0
```

- [ ] **Step 3: 创建 auth_middleware.py**

```python
# backend/utils/auth_middleware.py
import os
import jwt
from functools import wraps
from flask import request, jsonify

JWT_SECRET = os.environ.get('JWT_SECRET', 'niuniu-jwt-secret-2026')
JWT_ALGORITHM = 'HS256'
JWT_EXP_DAYS = 7


def require_auth(f):
    """JWT 鉴权装饰器，从 Authorization: Bearer <token> 中提取用户信息"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': '未登录或token无效'}), 401
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.current_user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'message': 'token已过期，请重新登录'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'message': 'token无效'}), 401
        return f(*args, **kwargs)
    return decorated
```

- [ ] **Step 4: commit**

```bash
git add backend/requirements.txt backend/utils/auth_middleware.py
git commit -m "feat: add JWT auth middleware"
```

---

## Task 3: 后端认证路由 (auth.py)

**Files:**
- Create: `backend/routes/auth.py`

- [ ] **Step 1: 创建 auth.py**

```python
# backend/routes/auth.py
import os
import datetime
import jwt
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from utils.db import execute_query, execute_write
from utils.auth_middleware import JWT_SECRET, JWT_ALGORITHM, JWT_EXP_DAYS, require_auth

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    rows = execute_query('SELECT id, username, password_hash, phone, role FROM users WHERE username=%s', (username,))
    if not rows:
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401
    user = rows[0]

    if not check_password_hash(user['password_hash'], password):
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

    exp = datetime.datetime.utcnow() + datetime.timedelta(days=JWT_EXP_DAYS)
    payload = {
        'user_id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'exp': exp,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return jsonify({
        'success': True,
        'token': token,
        'user': {'id': user['id'], 'username': user['username'], 'phone': user['phone'], 'role': user['role']},
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
@require_auth
def logout():
    # JWT 无状态，前端清除 token 即可
    return jsonify({'success': True, 'message': '已退出登录'})


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@require_auth
def change_password():
    data = request.get_json(silent=True) or {}
    old_password = (data.get('old_password') or '').strip()
    new_password = (data.get('new_password') or '').strip()
    if not old_password or not new_password:
        return jsonify({'success': False, 'message': '旧密码和新密码不能为空'}), 400
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码长度不能少于6位'}), 400

    user_id = request.current_user['user_id']
    rows = execute_query('SELECT password_hash FROM users WHERE id=%s', (user_id,))
    if not rows:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    if not check_password_hash(rows[0]['password_hash'], old_password):
        return jsonify({'success': False, 'message': '旧密码错误'}), 400

    new_hash = generate_password_hash(new_password)
    execute_write('UPDATE users SET password_hash=%s WHERE id=%s', (new_hash, user_id))
    return jsonify({'success': True, 'message': '密码修改成功'})
```

- [ ] **Step 2: 在数据库中为admin创建正确密码hash**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend && source venv/bin/activate && python3 -c "
from werkzeug.security import generate_password_hash
h = generate_password_hash('admin123')
print(h)
import pymysql
conn = pymysql.connect(host='127.0.0.1', user='root', password='123456', database='stock', charset='utf8mb4')
with conn.cursor() as cur:
    cur.execute('INSERT INTO users (username, password_hash, phone, role) VALUES (%s,%s,NULL,\"admin\") ON DUPLICATE KEY UPDATE password_hash=%s', (\"admin\", h, h))
conn.commit()
conn.close()
print('admin用户创建成功')
"
```

Expected: 打印hash字符串，打印"admin用户创建成功"

- [ ] **Step 3: commit**

```bash
git add backend/routes/auth.py
git commit -m "feat: add auth routes (login/logout/change-password)"
```

---

## Task 4: 后端用户信息路由 (user.py)

**Files:**
- Create: `backend/routes/user.py`

- [ ] **Step 1: 创建 user.py**

```python
# backend/routes/user.py
import datetime
from flask import Blueprint, jsonify
from utils.db import execute_query
from utils.auth_middleware import require_auth

user_bp = Blueprint('user', __name__)


@user_bp.route('/api/user/profile', methods=['GET'])
@require_auth
def profile():
    user_id = request.current_user['user_id']
    rows = execute_query('SELECT id, username, phone, role FROM users WHERE id=%s', (user_id,))
    if not rows:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    user = rows[0]

    # 查订阅
    subs = execute_query(
        'SELECT plan_type, end_time FROM user_subscriptions WHERE user_id=%s AND is_active=1 AND end_time > NOW() ORDER BY end_time DESC LIMIT 1',
        (user_id,)
    )
    expire_time = None
    is_vip = False
    if subs:
        sub = subs[0]
        expire_time = sub['end_time'].strftime('%Y/%m/%d %H:%M:%S') if hasattr(sub['end_time'], 'strftime') else str(sub['end_time'])
        is_vip = True

    return jsonify({
        'success': True,
        'data': {
            'id': user['id'],
            'username': user['username'],
            'phone': user['phone'] or '',
            'role': user['role'],
            'is_vip': is_vip,
            'expire_time': expire_time,
        }
    })
```

注意：user.py 需要在函数内 import request：
在文件顶部添加 `from flask import Blueprint, request, jsonify`（替换无 request 的那行）。

- [ ] **Step 2: 完整正确版本（Step 1已包含，确认from flask import request）**

文件完整内容：
```python
# backend/routes/user.py
from flask import Blueprint, request, jsonify
from utils.db import execute_query
from utils.auth_middleware import require_auth

user_bp = Blueprint('user', __name__)


@user_bp.route('/api/user/profile', methods=['GET'])
@require_auth
def profile():
    user_id = request.current_user['user_id']
    rows = execute_query('SELECT id, username, phone, role FROM users WHERE id=%s', (user_id,))
    if not rows:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    user = rows[0]

    subs = execute_query(
        'SELECT plan_type, end_time FROM user_subscriptions WHERE user_id=%s AND is_active=1 AND end_time > NOW() ORDER BY end_time DESC LIMIT 1',
        (user_id,)
    )
    expire_time = None
    is_vip = False
    if subs:
        sub = subs[0]
        expire_time = sub['end_time'].strftime('%Y/%m/%d %H:%M:%S') if hasattr(sub['end_time'], 'strftime') else str(sub['end_time'])
        is_vip = True

    return jsonify({
        'success': True,
        'data': {
            'id': user['id'],
            'username': user['username'],
            'phone': user['phone'] or '',
            'role': user['role'],
            'is_vip': is_vip,
            'expire_time': expire_time,
        }
    })
```

- [ ] **Step 3: commit**

```bash
git add backend/routes/user.py
git commit -m "feat: add user profile route"
```

---

## Task 5: 后端订单路由 (orders.py)

**Files:**
- Create: `backend/routes/orders.py`

- [ ] **Step 1: 创建 orders.py**

```python
# backend/routes/orders.py
import time
import datetime
import random
import string
from flask import Blueprint, request, jsonify
from utils.db import execute_query, execute_write
from utils.auth_middleware import require_auth

orders_bp = Blueprint('orders', __name__)

PLANS = {
    'monthly':   {'name': '月度VIP',  'amount': 380.00, 'days': 30},
    'quarterly': {'name': '季度VIP',  'amount': 900.00, 'days': 90},
    'semi':      {'name': '半年VIP',  'amount': 1600.00, 'days': 180},
    'annual':    {'name': '年度VIP',  'amount': 2500.00, 'days': 365},
    'daily':     {'name': '日度VIP',  'amount': 0.01,   'days': 1},
}


def _gen_order_no():
    """生成26位唯一订单号：时间戳16位 + 随机数10位"""
    ts = int(time.time() * 1000)  # 毫秒时间戳 13位
    rand = ''.join(random.choices(string.digits, k=13))
    return f"{ts}{rand}"[:26]


@orders_bp.route('/api/orders', methods=['GET'])
@require_auth
def list_orders():
    user_id = request.current_user['user_id']
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    offset = (page - 1) * page_size

    total_rows = execute_query('SELECT COUNT(*) AS cnt FROM orders WHERE user_id=%s', (user_id,))
    total = total_rows[0]['cnt'] if total_rows else 0

    rows = execute_query(
        'SELECT id, order_no, plan_type, amount, status, created_at FROM orders WHERE user_id=%s ORDER BY created_at DESC LIMIT %s OFFSET %s',
        (user_id, page_size, offset)
    )

    def fmt_row(r):
        plan = PLANS.get(r['plan_type'], {})
        return {
            'id': r['id'],
            'order_no': r['order_no'],
            'plan_name': plan.get('name', r['plan_type']),
            'amount': float(r['amount']),
            'status': r['status'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(r['created_at'], 'strftime') else str(r['created_at']),
        }

    return jsonify({
        'success': True,
        'data': {
            'list': [fmt_row(r) for r in rows],
            'total': total,
            'page': page,
            'page_size': page_size,
        }
    })


@orders_bp.route('/api/orders/create', methods=['POST'])
@require_auth
def create_order():
    data = request.get_json(silent=True) or {}
    plan_type = data.get('plan_type', '')
    if plan_type not in PLANS:
        return jsonify({'success': False, 'message': '无效的套餐类型'}), 400

    user_id = request.current_user['user_id']
    plan = PLANS[plan_type]
    order_no = _gen_order_no()

    execute_write(
        'INSERT INTO orders (order_no, user_id, plan_type, amount, status) VALUES (%s,%s,%s,%s,"pending")',
        (order_no, user_id, plan_type, plan['amount'])
    )
    return jsonify({
        'success': True,
        'data': {
            'order_no': order_no,
            'plan_name': plan['name'],
            'amount': plan['amount'],
        }
    })


@orders_bp.route('/api/orders/mock-pay', methods=['POST'])
@require_auth
def mock_pay():
    """测试用：直接激活1天会员（不验证order_no真实性）"""
    data = request.get_json(silent=True) or {}
    order_no = data.get('order_no', '')
    if not order_no:
        return jsonify({'success': False, 'message': '订单号不能为空'}), 400

    user_id = request.current_user['user_id']

    # 查订单
    rows = execute_query('SELECT id, plan_type FROM orders WHERE order_no=%s AND user_id=%s', (order_no, user_id))
    if not rows:
        return jsonify({'success': False, 'message': '订单不存在'}), 404

    order = rows[0]
    plan = PLANS.get(order['plan_type'], {'days': 1})

    # 更新订单为已支付
    execute_write('UPDATE orders SET status="paid" WHERE order_no=%s', (order_no,))

    # 激活/续费订阅
    now = datetime.datetime.now()
    # 如果已有有效订阅，从到期时间续费；否则从现在开始
    existing = execute_query(
        'SELECT id, end_time FROM user_subscriptions WHERE user_id=%s AND is_active=1 AND end_time > NOW()',
        (user_id,)
    )
    if existing:
        base_time = existing[0]['end_time']
        end_time = base_time + datetime.timedelta(days=plan['days'])
        execute_write(
            'UPDATE user_subscriptions SET end_time=%s, plan_type=%s WHERE id=%s',
            (end_time, order['plan_type'], existing[0]['id'])
        )
    else:
        end_time = now + datetime.timedelta(days=plan['days'])
        execute_write(
            'INSERT INTO user_subscriptions (user_id, plan_type, start_time, end_time, is_active) VALUES (%s,%s,%s,%s,1)',
            (user_id, order['plan_type'], now, end_time)
        )

    expire_str = end_time.strftime('%Y/%m/%d %H:%M:%S')
    return jsonify({
        'success': True,
        'message': f'支付成功！会员有效期至 {expire_str}',
        'data': {'expire_time': expire_str}
    })
```

- [ ] **Step 2: commit**

```bash
git add backend/routes/orders.py
git commit -m "feat: add orders routes (list/create/mock-pay)"
```

---

## Task 6: 注册新路由到 app.py

**Files:**
- Modify: `backend/routes/__init__.py`
- Modify: `backend/app.py`

- [ ] **Step 1: 更新 routes/__init__.py**

在 `backend/routes/__init__.py` 末尾追加三行导入并更新 `__all__`：

```python
# Routes package initialization
from .stock_basic import stock_basic_bp
from .stock_timeshare import stock_timeshare_bp
from .stock_tick import stock_tick_bp
from .stock_other import stock_other_bp
from .l2_dashboard import l2_dashboard_bp
from .emotion_cycle import emotion_cycle_bp
from .limit_up_echelon import limit_up_echelon_bp
from .theme_manage import theme_manage_bp
from .auction_grab import auction_grab_bp
from .dragon_tiger import dragon_tiger_bp
from .auth import auth_bp
from .user import user_bp
from .orders import orders_bp

__all__ = [
    'stock_basic_bp',
    'stock_timeshare_bp',
    'stock_tick_bp',
    'stock_other_bp',
    'l2_dashboard_bp',
    'emotion_cycle_bp',
    'limit_up_echelon_bp',
    'theme_manage_bp',
    'auction_grab_bp',
    'dragon_tiger_bp',
    'auth_bp',
    'user_bp',
    'orders_bp',
]
```

- [ ] **Step 2: 更新 app.py — 导入和注册新Blueprint**

在 `app.py` 的 import 中添加三个新bp：
```python
from routes import (
    stock_basic_bp,
    stock_timeshare_bp,
    stock_tick_bp,
    stock_other_bp,
    l2_dashboard_bp,
    emotion_cycle_bp,
    limit_up_echelon_bp,
    theme_manage_bp,
    auction_grab_bp,
    dragon_tiger_bp,
    auth_bp,
    user_bp,
    orders_bp,
)
```

在 `register_blueprints` 函数末尾添加：
```python
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(orders_bp)
```

- [ ] **Step 3: 验证后端能启动**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend && source venv/bin/activate && python3 -c "from app import app; print('OK')"
```

Expected: 打印 OK，无报错

- [ ] **Step 4: commit**

```bash
git add backend/routes/__init__.py backend/app.py
git commit -m "feat: register auth/user/orders blueprints"
```

---

## Task 7: 前端认证 Service

**Files:**
- Create: `frontend/src/services/auth.js`

- [ ] **Step 1: 创建 auth.js**

```javascript
// frontend/src/services/auth.js
import { apiConfig } from '../config/api';

const BASE = apiConfig.baseURL;
const TOKEN_KEY = 'niuniu_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const removeToken = () => localStorage.removeItem(TOKEN_KEY);

const authFetch = async (path, options = {}) => {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers };
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  const data = await res.json();
  return data;
};

export const login = (username, password) =>
  authFetch('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });

export const logout = () =>
  authFetch('/api/auth/logout', { method: 'POST' });

export const changePassword = (old_password, new_password) =>
  authFetch('/api/auth/change-password', { method: 'POST', body: JSON.stringify({ old_password, new_password }) });

export const getProfile = () => authFetch('/api/user/profile');

export const getOrders = (page = 1, page_size = 10) =>
  authFetch(`/api/orders?page=${page}&page_size=${page_size}`);

export const createOrder = (plan_type) =>
  authFetch('/api/orders/create', { method: 'POST', body: JSON.stringify({ plan_type }) });

export const mockPay = (order_no) =>
  authFetch('/api/orders/mock-pay', { method: 'POST', body: JSON.stringify({ order_no }) });
```

- [ ] **Step 2: commit**

```bash
git add frontend/src/services/auth.js
git commit -m "feat: add frontend auth service"
```

---

## Task 8: 前端 AuthContext

**Files:**
- Create: `frontend/src/context/AuthContext.js`

- [ ] **Step 1: 创建 AuthContext.js**

```javascript
// frontend/src/context/AuthContext.js
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getToken, setToken, removeToken, login as apiLogin, logout as apiLogout, getProfile } from '../services/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);       // { id, username, phone, role }
  const [isVip, setIsVip] = useState(false);
  const [expireTime, setExpireTime] = useState(null);
  const [loading, setLoading] = useState(true); // 初始化时验证token

  const refreshUser = useCallback(async () => {
    const token = getToken();
    if (!token) { setUser(null); setIsVip(false); setLoading(false); return; }
    try {
      const res = await getProfile();
      if (res.success && res.data) {
        setUser(res.data);
        setIsVip(res.data.is_vip || false);
        setExpireTime(res.data.expire_time || null);
      } else {
        removeToken();
        setUser(null);
        setIsVip(false);
      }
    } catch {
      removeToken();
      setUser(null);
      setIsVip(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refreshUser(); }, [refreshUser]);

  const login = async (username, password) => {
    const res = await apiLogin(username, password);
    if (res.success) {
      setToken(res.token);
      await refreshUser();
    }
    return res;
  };

  const logout = async () => {
    try { await apiLogout(); } catch {}
    removeToken();
    setUser(null);
    setIsVip(false);
    setExpireTime(null);
  };

  return (
    <AuthContext.Provider value={{ user, isVip, expireTime, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

- [ ] **Step 2: commit**

```bash
git add frontend/src/context/AuthContext.js
git commit -m "feat: add AuthContext with JWT support"
```

---

## Task 9: PermissionGuard 权限遮罩组件

**Files:**
- Create: `frontend/src/components/PermissionGuard.js`

- [ ] **Step 1: 创建 PermissionGuard.js**

```javascript
// frontend/src/components/PermissionGuard.js
import React from 'react';
import { Button } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * 权限遮罩：非VIP用户显示升级提示，覆盖在children上
 * 用法：<PermissionGuard><YourComponent /></PermissionGuard>
 */
export default function PermissionGuard({ children }) {
  const { isVip, user, loading } = useAuth();
  const navigate = useNavigate();

  if (loading) return null;
  if (!user) {
    navigate('/login');
    return null;
  }
  if (isVip) return children;

  return (
    <div style={{ position: 'relative', minHeight: 400 }}>
      <div style={{ filter: 'blur(4px)', pointerEvents: 'none', userSelect: 'none' }}>
        {children}
      </div>
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(20,18,19,0.75)',
      }}>
        <div style={{
          background: '#1e1e2e', border: '1px solid #3a3a5c', borderRadius: 12,
          padding: '32px 48px', textAlign: 'center',
        }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🔒</div>
          <div style={{ color: '#fff', fontSize: 18, fontWeight: 600, marginBottom: 8 }}>此功能需要VIP权限</div>
          <div style={{ color: '#aaa', fontSize: 14, marginBottom: 20 }}>升级权限后解锁全部分析功能</div>
          <Button type="primary" size="large" onClick={() => navigate('/permission-center')}>
            立即升级
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: commit**

```bash
git add frontend/src/components/PermissionGuard.js
git commit -m "feat: add PermissionGuard component"
```

---

## Task 10: 登录页

**Files:**
- Create: `frontend/src/pages/Login/index.js`

- [ ] **Step 1: 创建 Login/index.js**

```javascript
// frontend/src/pages/Login/index.js
import React, { useState, useEffect } from 'react';
import { Form, Input, Button, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) navigate('/stock-dashboard', { replace: true });
  }, [user, navigate]);

  const onFinish = async ({ username, password }) => {
    setLoading(true);
    try {
      const res = await login(username, password);
      if (res.success) {
        message.success('登录成功');
        navigate('/stock-dashboard', { replace: true });
      } else {
        message.error(res.message || '登录失败');
      }
    } catch (e) {
      message.error('网络错误，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh', background: '#141213',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#1e1e2e', border: '1px solid #2a2a3a', borderRadius: 12,
        padding: '48px 40px', width: 380,
      }}>
        <h2 style={{ color: '#fff', textAlign: 'center', marginBottom: 32, fontSize: 22 }}>
          牛牛牛 · 登录
        </h2>
        <Form onFinish={onFinish} layout="vertical">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input
              placeholder="用户名"
              size="large"
              style={{ background: '#2a2a3a', border: '1px solid #3a3a5c', color: '#fff' }}
            />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password
              placeholder="密码"
              size="large"
              style={{ background: '#2a2a3a', border: '1px solid #3a3a5c', color: '#fff' }}
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: commit**

```bash
git add frontend/src/pages/Login/index.js
git commit -m "feat: add Login page"
```

---

## Task 11: 用户中心页面

**Files:**
- Create: `frontend/src/pages/UserCenter/index.js`
- Create: `frontend/src/pages/UserCenter/index.css`

- [ ] **Step 1: 创建 UserCenter/index.css**

```css
/* frontend/src/pages/UserCenter/index.css */
.user-center { padding: 24px; max-width: 900px; margin: 0 auto; }
.info-card { background: #1e1e2e; border: 1px solid #2a2a3a; border-radius: 8px; padding: 24px; margin-bottom: 20px; }
.info-card h3 { color: #fff; text-align: center; margin-bottom: 20px; font-size: 16px; }
.info-row { display: flex; padding: 10px 0; border-bottom: 1px solid #2a2a3a; color: #ccc; }
.info-row:last-child { border-bottom: none; }
.info-label { width: 80px; color: #888; }
.info-value { flex: 1; }
.vip-badge { color: #52c41a; font-weight: bold; }
.no-vip { color: #ff4d4f; }
```

- [ ] **Step 2: 创建 UserCenter/index.js**

```javascript
// frontend/src/pages/UserCenter/index.js
import React, { useState, useEffect } from 'react';
import { Table, Button, Form, Input, message, Tag, Pagination } from 'antd';
import { useAuth } from '../../context/AuthContext';
import { getOrders, changePassword } from '../../services/auth';
import './index.css';

const STATUS_MAP = { pending: { color: 'orange', text: '未支付' }, paid: { color: 'green', text: '支付完成' } };

export default function UserCenter() {
  const { user, isVip, expireTime, refreshUser } = useAuth();
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pwdLoading, setPwdLoading] = useState(false);
  const [form] = Form.useForm();

  const fetchOrders = async (p = 1) => {
    const res = await getOrders(p, 10);
    if (res.success) {
      setOrders(res.data.list);
      setTotal(res.data.total);
    }
  };

  useEffect(() => { fetchOrders(page); }, [page]);

  const onChangePwd = async ({ old_password, new_password, confirm }) => {
    if (new_password !== confirm) { message.error('两次密码不一致'); return; }
    setPwdLoading(true);
    try {
      const res = await changePassword(old_password, new_password);
      if (res.success) { message.success('密码修改成功'); form.resetFields(); }
      else message.error(res.message);
    } catch { message.error('网络错误'); }
    finally { setPwdLoading(false); }
  };

  const columns = [
    { title: '权限名称', dataIndex: 'plan_name', key: 'plan_name' },
    { title: '单号', dataIndex: 'order_no', key: 'order_no', ellipsis: true },
    { title: '额度', dataIndex: 'amount', key: 'amount', render: v => `¥${Number(v).toFixed(2)}` },
    { title: '状态', dataIndex: 'status', key: 'status', render: s => <Tag color={STATUS_MAP[s]?.color}>{STATUS_MAP[s]?.text || s}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
  ];

  return (
    <div className="user-center">
      <div className="info-card">
        <h3>用户信息</h3>
        <div className="info-row"><span className="info-label">用户名：</span><span className="info-value">{user?.username}</span></div>
        <div className="info-row"><span className="info-label">手机号：</span><span className="info-value">{user?.phone || '未绑定'}</span></div>
        <div className="info-row">
          <span className="info-label">有效期：</span>
          <span className="info-value">
            {isVip ? <span className="vip-badge">{expireTime}</span> : <span className="no-vip">未开通VIP</span>}
          </span>
        </div>
      </div>

      <div className="info-card">
        <h3>修改密码</h3>
        <Form form={form} onFinish={onChangePwd} layout="vertical" style={{ maxWidth: 360, margin: '0 auto' }}>
          <Form.Item name="old_password" rules={[{ required: true, message: '请输入旧密码' }]}>
            <Input.Password placeholder="旧密码" style={{ background: '#2a2a3a', border: '1px solid #3a3a5c', color: '#fff' }} />
          </Form.Item>
          <Form.Item name="new_password" rules={[{ required: true, message: '请输入新密码' }, { min: 6, message: '至少6位' }]}>
            <Input.Password placeholder="新密码（至少6位）" style={{ background: '#2a2a3a', border: '1px solid #3a3a5c', color: '#fff' }} />
          </Form.Item>
          <Form.Item name="confirm" rules={[{ required: true, message: '请确认新密码' }]}>
            <Input.Password placeholder="确认新密码" style={{ background: '#2a2a3a', border: '1px solid #3a3a5c', color: '#fff' }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={pwdLoading} block>确认修改</Button>
          </Form.Item>
        </Form>
      </div>

      <div className="info-card">
        <h3>订单列表</h3>
        <Table
          dataSource={orders}
          columns={columns}
          rowKey="id"
          pagination={false}
          style={{ background: 'transparent' }}
        />
        <div style={{ textAlign: 'right', marginTop: 12 }}>
          <Pagination current={page} total={total} pageSize={10} onChange={p => setPage(p)} showTotal={t => `共 ${t} 条`} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: commit**

```bash
git add frontend/src/pages/UserCenter/
git commit -m "feat: add UserCenter page"
```

---

## Task 12: 权限中心页面

**Files:**
- Create: `frontend/src/pages/PermissionCenter/index.js`
- Create: `frontend/src/pages/PermissionCenter/index.css`

- [ ] **Step 1: 创建 PermissionCenter/index.css**

```css
/* frontend/src/pages/PermissionCenter/index.css */
.permission-center { padding: 32px 24px; max-width: 1100px; margin: 0 auto; }
.permission-center h2 { color: #fff; text-align: center; margin-bottom: 32px; font-size: 22px; }
.plans-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
@media (max-width: 900px) { .plans-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 500px) { .plans-grid { grid-template-columns: 1fr; } }
.plan-card { background: #1e1e2e; border: 1px solid #2a2a3a; border-radius: 12px; padding: 28px 20px; text-align: center; }
.plan-card.highlight { border-color: #1677ff; }
.plan-name { color: #fff; font-size: 17px; font-weight: 600; margin-bottom: 12px; }
.plan-price { color: #1677ff; font-size: 28px; font-weight: 700; margin-bottom: 16px; }
.plan-features { list-style: none; padding: 0; margin: 0 0 20px; text-align: left; }
.plan-features li { color: #ccc; padding: 5px 0; font-size: 14px; }
.plan-features li::before { content: '✓ '; color: #1677ff; }
.qr-modal-content { text-align: center; }
.qr-modal-content img { width: 200px; height: 200px; margin: 16px auto; display: block; }
.qr-price { color: #1677ff; font-size: 22px; font-weight: 700; margin-top: 12px; }
.qr-hint { color: #aaa; font-size: 13px; margin-top: 8px; }
```

- [ ] **Step 2: 创建 PermissionCenter/index.js**

```javascript
// frontend/src/pages/PermissionCenter/index.js
import React, { useState } from 'react';
import { Button, Modal, message } from 'antd';
import { useAuth } from '../../context/AuthContext';
import { createOrder, mockPay } from '../../services/auth';
import './index.css';

const PLANS = [
  { key: 'monthly',   name: '月度VIP',  price: '¥380/月',   amount: 380, days: 30 },
  { key: 'quarterly', name: '季度VIP',  price: '¥900/季',   amount: 900, days: 90 },
  { key: 'semi',      name: '半年VIP',  price: '¥1600/半年', amount: 1600, days: 180 },
  { key: 'annual',    name: '年度VIP',  price: '¥2500/年',  amount: 2500, days: 365 },
];

const FEATURES = ['level2大单数据', '情绪周期', '竞价抢筹', '板块抢筹', '风险预警'];

export default function PermissionCenter() {
  const { refreshUser } = useAuth();
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [qrVisible, setQrVisible] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [currentOrder, setCurrentOrder] = useState(null);
  const [loading, setLoading] = useState(false);

  const onBuy = (plan) => {
    setSelectedPlan(plan);
    setConfirmVisible(true);
  };

  const onConfirm = async () => {
    setLoading(true);
    try {
      const res = await createOrder(selectedPlan.key);
      if (res.success) {
        setCurrentOrder(res.data);
        setConfirmVisible(false);
        setQrVisible(true);
      } else {
        message.error(res.message || '创建订单失败');
      }
    } catch { message.error('网络错误'); }
    finally { setLoading(false); }
  };

  const onMockPay = async () => {
    if (!currentOrder) return;
    setLoading(true);
    try {
      const res = await mockPay(currentOrder.order_no);
      if (res.success) {
        message.success(res.message || '支付成功！');
        setQrVisible(false);
        await refreshUser();
      } else {
        message.error(res.message || '支付失败');
      }
    } catch { message.error('网络错误'); }
    finally { setLoading(false); }
  };

  return (
    <div className="permission-center">
      <h2>权限中心</h2>
      <div className="plans-grid">
        {PLANS.map((plan, i) => (
          <div key={plan.key} className={`plan-card${i === 0 ? ' highlight' : ''}`}>
            <div className="plan-name">{plan.name}</div>
            <div className="plan-price">{plan.price}</div>
            <ul className="plan-features">
              {FEATURES.map(f => <li key={f}>{f}</li>)}
            </ul>
            <Button type="primary" block size="large" onClick={() => onBuy(plan)}>
              立即开通
            </Button>
          </div>
        ))}
      </div>

      {/* 确认购买弹窗 */}
      <Modal
        title="确认购买"
        open={confirmVisible}
        onCancel={() => setConfirmVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setConfirmVisible(false)}>取消</Button>,
          <Button key="confirm" type="primary" loading={loading} onClick={onConfirm}>确认购买</Button>,
        ]}
      >
        {selectedPlan && (
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <div style={{ color: '#ccc', marginBottom: 8 }}>您选择的是 {selectedPlan.name}</div>
            <div style={{ color: '#1677ff', fontSize: 22, fontWeight: 700 }}>价格：{selectedPlan.price}</div>
          </div>
        )}
      </Modal>

      {/* 微信支付弹窗 */}
      <Modal
        title="微信支付"
        open={qrVisible}
        onCancel={() => setQrVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setQrVisible(false)}>取消</Button>,
          <Button key="pay" type="primary" loading={loading} onClick={onMockPay}>已完成支付</Button>,
        ]}
      >
        {currentOrder && (
          <div className="qr-modal-content">
            <img
              src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=wechat-pay-${currentOrder.order_no}`}
              alt="微信支付二维码"
            />
            <div className="qr-price">¥{Number(currentOrder.amount).toFixed(2)}/{selectedPlan?.name}</div>
            <div className="qr-hint">请使用微信扫码支付</div>
          </div>
        )}
      </Modal>
    </div>
  );
}
```

- [ ] **Step 3: commit**

```bash
git add frontend/src/pages/PermissionCenter/
git commit -m "feat: add PermissionCenter page with mock WeChat payment"
```

---

## Task 13: 修改 App.js — 路由 + AuthProvider + Header

**Files:**
- Modify: `frontend/src/App.js`

- [ ] **Step 1: 替换 App.js 完整内容**

```javascript
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
import Login from './pages/Login';
import UserCenter from './pages/UserCenter';
import PermissionCenter from './pages/PermissionCenter';
import PermissionGuard from './components/PermissionGuard';
import { AuthProvider, useAuth } from './context/AuthContext';
import { errorAtom } from './store/atoms';

const { Content, Header } = Layout;

const NAV_ITEMS = [
  { key: '/stock-dashboard', label: '个股分析' },
  { key: '/limit-up-echelon', label: '涨停梯队' },
  { key: '/emotion-cycle', label: '情绪周期' },
  { key: '/auction-grab', label: '竞价抢筹' },
  { key: '/permission-center', label: '权限中心' },
];

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

function AppInner() {
  const [error, setError] = useAtom(errorAtom);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  const handleMenuClick = ({ key }) => navigate(key);

  const isLoginPage = location.pathname === '/login';

  return (
    <Layout className="layout" style={{ minHeight: '100vh' }}>
      {!isLoginPage && (
        <Header style={{ padding: 0, background: '#141213', borderBottom: '1px solid #2a2a2a', display: 'flex', alignItems: 'center' }}>
          <Menu
            mode="horizontal"
            selectedKeys={[location.pathname]}
            items={NAV_ITEMS}
            onClick={handleMenuClick}
            style={{ background: '#141213', borderBottom: 'none', color: '#fff', flex: 1 }}
            theme="dark"
          />
          {user && (
            <div style={{ display: 'flex', alignItems: 'center', paddingRight: 16, gap: 8, whiteSpace: 'nowrap' }}>
              <span
                style={{ color: '#1677ff', cursor: 'pointer', fontSize: 14 }}
                onClick={() => navigate('/user-center')}
              >
                {user.username}
              </span>
              <Button
                type="text"
                size="small"
                style={{ color: '#aaa' }}
                onClick={async () => { await logout(); navigate('/login'); }}
              >
                退出
              </Button>
            </div>
          )}
        </Header>
      )}
      <Content>
        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
            style={{ position: 'fixed', top: 20, left: '50%', transform: 'translateX(-50%)', zIndex: 9999, maxWidth: '600px' }}
          />
        )}
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Navigate to="/stock-dashboard" replace />} />
          <Route path="/home" element={<RequireAuth><Home /></RequireAuth>} />
          <Route path="/stock-dashboard" element={<RequireAuth><StockDashboard /></RequireAuth>} />
          <Route path="/limit-up-echelon" element={<RequireAuth><LimitUpEchelon /></RequireAuth>} />
          <Route path="/emotion-cycle" element={<RequireAuth><PermissionGuard><EmotionCycle /></PermissionGuard></RequireAuth>} />
          <Route path="/auction-grab" element={<RequireAuth><PermissionGuard><AuctionGrab /></PermissionGuard></RequireAuth>} />
          <Route path="/permission-center" element={<RequireAuth><PermissionCenter /></RequireAuth>} />
          <Route path="/user-center" element={<RequireAuth><UserCenter /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/stock-dashboard" replace />} />
        </Routes>
      </Content>
    </Layout>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}

export default App;
```

- [ ] **Step 2: commit**

```bash
git add frontend/src/App.js
git commit -m "feat: integrate auth routes and permission guards into App"
```

---

## Task 14: 验证整体功能

- [ ] **Step 1: 重启后端**

```bash
cd /Users/mac/Github/NiuNIuNiu && bash start.sh
```

或手动：
```bash
cd /Users/mac/Github/NiuNIuNiu/backend && source venv/bin/activate && python3 app.py
```

- [ ] **Step 2: 重启前端**

```bash
cd /Users/mac/Github/NiuNIuNiu/frontend && npm start
```

- [ ] **Step 3: 测试登录**

```bash
curl -s -X POST http://localhost:9001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -m json.tool
```

Expected: `{"success": true, "token": "eyJ...", "user": {...}}`

- [ ] **Step 4: 用token测试用户信息**

```bash
TOKEN=$(curl -s -X POST http://localhost:9001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s http://localhost:9001/api/user/profile \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: 返回用户信息，`is_vip: false`

- [ ] **Step 5: 测试创建订单 + mock支付**

```bash
# 创建订单
ORDER=$(curl -s -X POST http://localhost:9001/api/orders/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"plan_type":"daily"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['order_no'])")

# mock支付
curl -s -X POST http://localhost:9001/api/orders/mock-pay \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"order_no\":\"$ORDER\"}" | python3 -m json.tool
```

Expected: 支付成功，返回 expire_time

- [ ] **Step 6: 前端浏览器验证**

1. 打开 http://localhost:3000 → 应重定向到 /login
2. 输入 admin/admin123 登录 → 跳转到 /stock-dashboard
3. 点击"情绪周期" → 看到权限遮罩"此功能需要VIP权限"
4. 点击"权限中心" → 看到套餐卡片
5. 点击"立即开通月度VIP" → 确认弹窗 → 确认 → 二维码弹窗
6. 点击"已完成支付" → 成功toast → 刷新后情绪周期可以访问
7. 右上角点用户名 → 进入用户中心，看到订单记录

- [ ] **Step 7: 最终commit**

```bash
git add -A
git commit -m "feat: complete user auth + permission + mock wechat payment system"
```
