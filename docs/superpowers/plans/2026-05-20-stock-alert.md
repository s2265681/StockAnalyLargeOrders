# Stock Alert Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「条件预警」模块，允许用户对股票设置涨跌幅/涨跌停/封单量条件，触发时发邮件至规则绑定的收件箱。

**Architecture:** 后端新增 `alert_rules` 表存储规则，`services/alert_monitor.py` 作为 eventlet greenlet 每 3 秒轮询 active 规则并检查条件，命中后发邮件（复用现有 SMTP 配置）并将规则状态改为 `triggered`。前端新增 `StockAlert` 页面，布局为列表 + 底部内嵌新增区，最多同时批量添加 3 条规则。

**Tech Stack:** Python/Flask, eventlet, pymysql, smtplib（复用现有），React, Ant Design

---

## File Map

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/migrations/20260520_create_alert_rules.sql` | 新建 | DB 表 |
| `backend/utils/db.py` | 修改 | 新增 `execute_insert()` 返回 lastrowid |
| `backend/utils/alert_notify.py` | 新建 | 预警邮件发送 |
| `backend/services/alert_monitor.py` | 新建 | 预警监控服务 + 条件检查 |
| `backend/routes/alert_rules.py` | 新建 | REST API Blueprint |
| `backend/routes/__init__.py` | 修改 | 注册 `alert_rules_bp` |
| `backend/app.py` | 修改 | 注册 blueprint + 启动监控 |
| `backend/tests/test_alert_notify.py` | 新建 | 邮件单元测试 |
| `backend/tests/test_alert_monitor.py` | 新建 | 条件检查单元测试 |
| `backend/tests/test_alert_rules_api.py` | 新建 | API 集成测试 |
| `frontend/src/pages/StockAlert/index.js` | 新建 | 预警页面组件 |
| `frontend/src/pages/StockAlert/index.css` | 新建 | 样式 |
| `frontend/src/App.js` | 修改 | 路由 + 导航菜单 |

---

### Task 1: DB Migration

**Files:**
- Create: `backend/migrations/20260520_create_alert_rules.sql`

- [ ] **Step 1: 创建迁移文件**

```sql
CREATE TABLE IF NOT EXISTS alert_rules (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT          NOT NULL,
    code          VARCHAR(10)  NOT NULL,
    stock_name    VARCHAR(20)  NOT NULL DEFAULT '',
    alert_type    VARCHAR(20)  NOT NULL COMMENT 'change_pct / limit_up / limit_down / seal_order',
    threshold     FLOAT        DEFAULT NULL,
    direction     VARCHAR(5)   DEFAULT NULL COMMENT 'above / below，仅 change_pct 使用',
    email         VARCHAR(100) NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active / triggered / disabled',
    triggered_at  DATETIME     DEFAULT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_status (user_id, status),
    INDEX idx_code_status (code, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] **Step 2: 应用迁移**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
mysql -u root -p123456 stock < migrations/20260520_create_alert_rules.sql
mysql -u root -p123456 stock -e "DESCRIBE alert_rules;"
```

Expected: 表结构包含 11 列（id, user_id, code, stock_name, alert_type, threshold, direction, email, status, triggered_at, created_at）

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/20260520_create_alert_rules.sql
git commit -m "feat: add alert_rules table migration"
```

---

### Task 2: `execute_insert` DB Helper

**Files:**
- Modify: `backend/utils/db.py`

- [ ] **Step 1: 在 `execute_write` 函数之后添加 `execute_insert`**

在 `backend/utils/db.py` 中 `execute_write` 函数结束之后，插入以下代码：

```python
def execute_insert(sql, params=None):
    """执行 INSERT，返回 lastrowid"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            conn.commit()
            return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/utils/db.py
git commit -m "feat: add execute_insert helper returning lastrowid"
```

---

### Task 3: 邮件通知工具

**Files:**
- Create: `backend/utils/alert_notify.py`
- Test: `backend/tests/test_alert_notify.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_alert_notify.py`：

```python
import unittest
from unittest.mock import patch, MagicMock


class TestAlertNotify(unittest.TestCase):

    def test_build_alert_email_change_pct_above(self):
        from utils.alert_notify import build_alert_email
        rule = {'code': '600519', 'stock_name': '贵州茅台', 'alert_type': 'change_pct',
                'threshold': 5.0, 'direction': 'above'}
        quote = {'change_percent': 6.2, 'price': 1800.0}
        subject, body = build_alert_email(rule, quote, {})
        self.assertIn('600519', subject)
        self.assertIn('涨跌幅', subject)
        self.assertIn('6.2', body)
        self.assertIn('涨超5.0%', body)

    def test_build_alert_email_change_pct_below(self):
        from utils.alert_notify import build_alert_email
        rule = {'code': '000001', 'stock_name': '平安银行', 'alert_type': 'change_pct',
                'threshold': 3.0, 'direction': 'below'}
        quote = {'change_percent': -4.0, 'price': 9.6}
        subject, body = build_alert_email(rule, quote, {})
        self.assertIn('跌超3.0%', body)

    def test_build_alert_email_limit_up(self):
        from utils.alert_notify import build_alert_email
        rule = {'code': '000001', 'stock_name': '平安银行', 'alert_type': 'limit_up',
                'threshold': None, 'direction': None}
        quote = {'change_percent': 10.01, 'price': 12.50}
        subject, body = build_alert_email(rule, quote, {'is_limit_up': True})
        self.assertIn('涨停', subject)
        self.assertIn('000001', subject)

    def test_build_alert_email_seal_order(self):
        from utils.alert_notify import build_alert_email
        rule = {'code': '300001', 'stock_name': '特锐德', 'alert_type': 'seal_order',
                'threshold': 500.0, 'direction': None}
        quote = {'change_percent': 10.01, 'price': 5.50}
        subject, body = build_alert_email(rule, quote, {'is_limit_up': True, 'seal_amount': 300.0})
        self.assertIn('封单', subject)
        self.assertIn('300.0', body)
        self.assertIn('500.0', body)

    @patch('utils.alert_notify._smtp_config')
    @patch('smtplib.SMTP_SSL')
    def test_send_stock_alert_calls_smtp(self, mock_smtp_cls, mock_config):
        mock_config.return_value = {
            'host': 'smtp.163.com', 'port': 465, 'user': 'a@163.com',
            'password': 'pass', 'use_ssl': True, 'sender': 'a@163.com',
        }
        mock_smtp_instance = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_smtp_instance
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        from utils.alert_notify import send_stock_alert
        rule = {'code': '600519', 'stock_name': '贵州茅台', 'alert_type': 'limit_up',
                'threshold': None, 'direction': None}
        result = send_stock_alert(rule, {'change_percent': 10.0, 'price': 1800.0},
                                  {'is_limit_up': True}, to_email='test@qq.com')
        self.assertTrue(result)
        mock_smtp_instance.sendmail.assert_called_once()

    @patch('utils.alert_notify._smtp_config')
    def test_send_stock_alert_no_smtp_returns_false(self, mock_config):
        mock_config.return_value = None
        from utils.alert_notify import send_stock_alert
        result = send_stock_alert({'code': '600519', 'stock_name': '茅台',
                                   'alert_type': 'limit_up', 'threshold': None, 'direction': None},
                                  {}, {}, to_email='test@qq.com')
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -m pytest tests/test_alert_notify.py -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'build_alert_email' from 'utils.alert_notify'`（文件不存在）

- [ ] **Step 3: 创建 `backend/utils/alert_notify.py`**

```python
"""股票条件预警邮件通知，复用 job_notify 的 SMTP 配置"""
import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils.job_notify import _smtp_config

logger = logging.getLogger(__name__)

_ALERT_TYPE_LABELS = {
    'change_pct': '涨跌幅',
    'limit_up': '涨停',
    'limit_down': '跌停',
    'seal_order': '涨停封单',
}


def build_alert_email(rule: dict, quote: dict, limit_up_data: dict) -> tuple:
    """构建预警邮件主题和正文，返回 (subject, body)"""
    code = rule['code']
    name = rule.get('stock_name') or code
    alert_type = rule['alert_type']
    threshold = rule.get('threshold')
    direction = rule.get('direction')
    pct = quote.get('change_percent', 0) or 0
    price = quote.get('price', 0) or 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    label = _ALERT_TYPE_LABELS.get(alert_type, alert_type)

    if alert_type == 'change_pct':
        direction_label = f"涨超{threshold}%" if direction == 'above' else f"跌超{threshold}%"
        subject = f"[预警] {name}({code}) {label}触发 · {direction_label}"
        body = (f"【NiuNIuNiu 预警】\n"
                f"{name}({code}) 当前涨跌幅 {pct:+.2f}%，已触发{direction_label}预警\n"
                f"当前价：{price}  触发时间：{now}")
    elif alert_type == 'limit_up':
        subject = f"[预警] {name}({code}) 已涨停"
        body = (f"【NiuNIuNiu 预警】\n"
                f"{name}({code}) 已涨停\n"
                f"当前价：{price}  涨幅：{pct:+.2f}%  触发时间：{now}")
    elif alert_type == 'limit_down':
        subject = f"[预警] {name}({code}) 已跌停"
        body = (f"【NiuNIuNiu 预警】\n"
                f"{name}({code}) 已跌停\n"
                f"当前价：{price}  涨幅：{pct:+.2f}%  触发时间：{now}")
    elif alert_type == 'seal_order':
        seal = limit_up_data.get('seal_amount', 0) or 0
        subject = f"[预警] {name}({code}) 涨停封单不足"
        body = (f"【NiuNIuNiu 预警】\n"
                f"{name}({code}) 涨停封单 {seal:.1f} 万元，低于设定阈值 {threshold} 万元\n"
                f"当前价：{price}  触发时间：{now}")
    else:
        subject = f"[预警] {name}({code}) {label}触发"
        body = f"【NiuNIuNiu 预警】\n{name}({code}) 预警条件已触发  触发时间：{now}"

    return subject, body


def send_stock_alert(rule: dict, quote: dict, limit_up_data: dict, to_email: str) -> bool:
    """发送股票预警邮件，返回是否成功"""
    cfg = _smtp_config()
    if not cfg:
        logger.warning("未配置 SMTP，跳过预警邮件: %s %s", rule.get('code'), rule.get('alert_type'))
        return False

    subject, body = build_alert_email(rule, quote, limit_up_data)
    msg = MIMEMultipart()
    msg['From'] = cfg['sender']
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        if cfg['use_ssl']:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg['host'], cfg['port'], context=context) as smtp:
                smtp.login(cfg['user'], cfg['password'])
                smtp.sendmail(cfg['sender'], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg['host'], cfg['port']) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(cfg['user'], cfg['password'])
                smtp.sendmail(cfg['sender'], [to_email], msg.as_string())
        logger.info("预警邮件已发送 -> %s [%s %s]", to_email, rule.get('code'), rule.get('alert_type'))
        return True
    except Exception as e:
        logger.error("预警邮件发送失败: %s", e)
        return False
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -m pytest tests/test_alert_notify.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/utils/alert_notify.py backend/tests/test_alert_notify.py
git commit -m "feat: add alert_notify utility with SMTP email sending"
```

---

### Task 4: 预警条件检查 + 监控服务

**Files:**
- Create: `backend/services/alert_monitor.py`
- Test: `backend/tests/test_alert_monitor.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_alert_monitor.py`：

```python
import unittest


class TestCheckRuleCondition(unittest.TestCase):

    def _check(self, rule, quote, limit_up_data):
        from services.alert_monitor import check_rule_condition
        return check_rule_condition(rule, quote, limit_up_data)

    def test_change_pct_above_triggered(self):
        rule = {'alert_type': 'change_pct', 'threshold': 5.0, 'direction': 'above'}
        self.assertTrue(self._check(rule, {'change_percent': 6.2, 'price': 100.0, 'yesterday_close': 94.2}, {}))

    def test_change_pct_above_not_triggered(self):
        rule = {'alert_type': 'change_pct', 'threshold': 5.0, 'direction': 'above'}
        self.assertFalse(self._check(rule, {'change_percent': 3.1, 'price': 100.0, 'yesterday_close': 96.9}, {}))

    def test_change_pct_above_exact_boundary(self):
        rule = {'alert_type': 'change_pct', 'threshold': 5.0, 'direction': 'above'}
        self.assertTrue(self._check(rule, {'change_percent': 5.0, 'price': 100.0, 'yesterday_close': 95.0}, {}))

    def test_change_pct_below_triggered(self):
        rule = {'alert_type': 'change_pct', 'threshold': 3.0, 'direction': 'below'}
        self.assertTrue(self._check(rule, {'change_percent': -4.0, 'price': 96.0, 'yesterday_close': 100.0}, {}))

    def test_change_pct_below_not_triggered(self):
        rule = {'alert_type': 'change_pct', 'threshold': 3.0, 'direction': 'below'}
        self.assertFalse(self._check(rule, {'change_percent': -1.5, 'price': 98.5, 'yesterday_close': 100.0}, {}))

    def test_limit_up_triggered(self):
        rule = {'alert_type': 'limit_up', 'threshold': None, 'direction': None}
        self.assertTrue(self._check(rule, {}, {'is_limit_up': True}))

    def test_limit_up_not_triggered(self):
        rule = {'alert_type': 'limit_up', 'threshold': None, 'direction': None}
        self.assertFalse(self._check(rule, {}, {'is_limit_up': False}))

    def test_limit_down_triggered(self):
        rule = {'alert_type': 'limit_down', 'threshold': None, 'direction': None}
        quote = {'change_percent': -10.01, 'price': 8.99, 'yesterday_close': 10.0}
        self.assertTrue(self._check(rule, quote, {'is_limit_up': False}))

    def test_limit_down_not_triggered(self):
        rule = {'alert_type': 'limit_down', 'threshold': None, 'direction': None}
        quote = {'change_percent': -3.0, 'price': 9.7, 'yesterday_close': 10.0}
        self.assertFalse(self._check(rule, quote, {'is_limit_up': False}))

    def test_seal_order_triggered(self):
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': None}
        self.assertTrue(self._check(rule, {}, {'is_limit_up': True, 'seal_amount': 300.0}))

    def test_seal_order_not_limit_up(self):
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': None}
        self.assertFalse(self._check(rule, {}, {'is_limit_up': False, 'seal_amount': 300.0}))

    def test_seal_order_above_threshold_not_triggered(self):
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': None}
        self.assertFalse(self._check(rule, {}, {'is_limit_up': True, 'seal_amount': 800.0}))

    def test_quote_none_returns_false(self):
        rule = {'alert_type': 'change_pct', 'threshold': 5.0, 'direction': 'above'}
        self.assertFalse(self._check(rule, None, {}))

    def test_change_pct_missing_threshold_returns_false(self):
        rule = {'alert_type': 'change_pct', 'threshold': None, 'direction': 'above'}
        self.assertFalse(self._check(rule, {'change_percent': 10.0}, {}))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -m pytest tests/test_alert_monitor.py -v 2>&1 | head -10
```

Expected: `ImportError`（文件不存在）

- [ ] **Step 3: 创建 `backend/services/alert_monitor.py`**

```python
"""股票条件预警监控服务，作为 eventlet greenlet 在交易时段每 3 秒轮询"""
import logging
from datetime import datetime

from utils.db import execute_query, execute_write
from utils.alert_notify import send_stock_alert

logger = logging.getLogger(__name__)

POLL_INTERVAL_TRADING = 3    # 交易时段轮询间隔（秒）
POLL_INTERVAL_CLOSED = 60    # 非交易时段休眠间隔（秒）


def _is_trade_time() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 + 25 <= t <= 11 * 60 + 30) or (13 * 60 <= t <= 15 * 60)


def check_rule_condition(rule: dict, quote, limit_up_data: dict) -> bool:
    """纯函数：判断规则是否触发，不访问网络/DB"""
    if not quote:
        return False

    alert_type = rule.get('alert_type')
    threshold = rule.get('threshold')
    direction = rule.get('direction')
    pct = quote.get('change_percent', 0) or 0

    if alert_type == 'change_pct':
        if threshold is None:
            return False
        return pct >= threshold if direction == 'above' else pct <= -threshold

    if alert_type == 'limit_up':
        return bool(limit_up_data.get('is_limit_up', False))

    if alert_type == 'limit_down':
        yesterday_close = quote.get('yesterday_close', 0) or 0
        price = quote.get('price', 0) or 0
        if yesterday_close > 0:
            limit_down_price = round(yesterday_close * 0.9, 2)
            return price <= limit_down_price + 0.01
        return pct <= -9.9

    if alert_type == 'seal_order':
        if not limit_up_data.get('is_limit_up', False):
            return False
        seal_amount = limit_up_data.get('seal_amount', 0) or 0
        return threshold is not None and seal_amount < threshold

    return False


def _get_active_rules() -> list:
    return execute_query(
        "SELECT id, user_id, code, stock_name, alert_type, threshold, direction, email "
        "FROM alert_rules WHERE status = 'active'",
        ()
    )


def _mark_triggered(rule_id: int) -> None:
    execute_write(
        "UPDATE alert_rules SET status = 'triggered', triggered_at = NOW() WHERE id = %s",
        (rule_id,)
    )


def _run_check_cycle(adapter) -> None:
    """执行一轮预警检查"""
    rules = _get_active_rules()
    if not rules:
        return

    by_code: dict = {}
    for rule in rules:
        by_code.setdefault(rule['code'], []).append(rule)

    for code, code_rules in by_code.items():
        try:
            quote = adapter.source.get_realtime_quote(code)
            if not quote:
                continue

            order_book = (adapter.source.get_order_book(code)
                          if hasattr(adapter.source, 'get_order_book') else {})
            limit_up_data = adapter.limit_up_monitor.analyze(code, quote, order_book)

            for rule in code_rules:
                if check_rule_condition(rule, quote, limit_up_data):
                    send_stock_alert(rule, quote, limit_up_data, to_email=rule['email'])
                    logger.info("预警触发: rule_id=%s code=%s type=%s -> %s",
                                rule['id'], code, rule['alert_type'], rule['email'])
                    _mark_triggered(rule['id'])
        except Exception as e:
            logger.error("预警检查失败 code=%s: %s", code, e)


def start_alert_monitor(socketio, adapter) -> None:
    """在 Flask-SocketIO eventlet 上下文中启动预警监控 greenlet"""

    def _monitor_loop():
        logger.info("预警监控服务已启动")
        while True:
            try:
                if _is_trade_time():
                    _run_check_cycle(adapter)
                    socketio.sleep(POLL_INTERVAL_TRADING)
                else:
                    socketio.sleep(POLL_INTERVAL_CLOSED)
            except Exception as e:
                logger.error("预警监控循环异常: %s", e)
                socketio.sleep(10)

    socketio.start_background_task(_monitor_loop)
    logger.info("预警监控任务已提交")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -m pytest tests/test_alert_monitor.py -v
```

Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/services/alert_monitor.py backend/tests/test_alert_monitor.py
git commit -m "feat: add alert monitor service with condition checker"
```

---

### Task 5: REST API

**Files:**
- Create: `backend/routes/alert_rules.py`
- Modify: `backend/routes/__init__.py`
- Test: `backend/tests/test_alert_rules_api.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_alert_rules_api.py`：

```python
import unittest
from unittest.mock import patch
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _make_app():
    from utils.env import load_env
    load_env()
    import eventlet
    eventlet.monkey_patch()
    from flask import Flask
    from flask_cors import CORS
    app = Flask(__name__)
    CORS(app)
    from routes.alert_rules import alert_rules_bp
    app.register_blueprint(alert_rules_bp)
    return app


class TestAlertRulesAPI(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.client = self.app.test_client()
        self.auth_header = {'Authorization': 'Bearer test-token'}

    def _mock_auth(self, user_id=1):
        return patch('utils.auth_middleware.decode_token',
                     return_value={'user_id': user_id, 'username': 'test', 'role': 'user'})

    @patch('routes.alert_rules.execute_query', return_value=[])
    def test_list_rules_returns_empty(self, _mock_q):
        with self._mock_auth():
            resp = self.client.get('/api/alert-rules', headers=self.auth_header)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['items'], [])

    @patch('routes.alert_rules.execute_query', return_value=[])
    @patch('routes.alert_rules.execute_insert', return_value=42)
    @patch('routes.alert_rules.get_stock_name_by_code', return_value='贵州茅台')
    def test_batch_create_single_rule(self, _mock_name, _mock_insert, _mock_q):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [{'code': '600519', 'alert_type': 'limit_up',
                                                     'threshold': None, 'direction': None,
                                                     'email': 'test@qq.com'}]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['created_ids'], [42])

    def test_batch_create_exceeds_limit(self):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [
                                        {'code': '600519', 'alert_type': 'limit_up', 'email': 'a@b.com'},
                                        {'code': '000001', 'alert_type': 'limit_up', 'email': 'a@b.com'},
                                        {'code': '300001', 'alert_type': 'limit_up', 'email': 'a@b.com'},
                                        {'code': '600000', 'alert_type': 'limit_up', 'email': 'a@b.com'},
                                    ]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('3', data['message'])

    def test_batch_create_missing_email(self):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [{'code': '600519', 'alert_type': 'limit_up'}]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('邮箱', data['message'])

    def test_batch_create_change_pct_missing_threshold(self):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [{'code': '600519', 'alert_type': 'change_pct',
                                                     'email': 'a@b.com'}]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('阈值', data['message'])

    @patch('routes.alert_rules.execute_write', return_value=1)
    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 1, 'status': 'triggered'}])
    def test_reactivate_rule(self, _mock_q, _mock_w):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/1/reactivate', headers=self.auth_header)
        data = resp.get_json()
        self.assertTrue(data['success'])

    @patch('routes.alert_rules.execute_write', return_value=1)
    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 1}])
    def test_delete_rule(self, _mock_q, _mock_w):
        with self._mock_auth():
            resp = self.client.delete('/api/alert-rules/1', headers=self.auth_header)
        data = resp.get_json()
        self.assertTrue(data['success'])

    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 99}])
    def test_delete_other_users_rule_rejected(self, _mock_q):
        with self._mock_auth(user_id=1):
            resp = self.client.delete('/api/alert-rules/1', headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('权限', data['message'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -m pytest tests/test_alert_rules_api.py -v 2>&1 | head -10
```

Expected: `ImportError`（routes/alert_rules 不存在）

- [ ] **Step 3: 创建 `backend/routes/alert_rules.py`**

```python
"""条件预警规则管理 API"""
import logging
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query, execute_write, execute_insert
from utils.auth_middleware import login_required
from utils.stock_utils import get_stock_name_by_code

logger = logging.getLogger(__name__)

alert_rules_bp = Blueprint('alert_rules', __name__)

VALID_ALERT_TYPES = {'change_pct', 'limit_up', 'limit_down', 'seal_order'}
TYPES_WITH_THRESHOLD = {'change_pct', 'seal_order'}


@alert_rules_bp.route('/api/alert-rules', methods=['GET'])
@login_required
def list_rules():
    user_id = request.current_user['user_id']
    rows = execute_query(
        "SELECT id, code, stock_name, alert_type, threshold, direction, email, "
        "status, triggered_at, created_at FROM alert_rules "
        "WHERE user_id = %s ORDER BY created_at DESC",
        (user_id,)
    )
    items = []
    for r in rows:
        items.append({
            'id': r['id'],
            'code': r['code'],
            'stock_name': r['stock_name'],
            'alert_type': r['alert_type'],
            'threshold': r['threshold'],
            'direction': r['direction'],
            'email': r['email'],
            'status': r['status'],
            'triggered_at': r['triggered_at'].strftime('%Y-%m-%d %H:%M:%S') if r['triggered_at'] else None,
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else None,
        })
    return v1_success_response(data={'items': items})


@alert_rules_bp.route('/api/alert-rules/batch', methods=['POST'])
@login_required
def batch_create_rules():
    user_id = request.current_user['user_id']
    body = request.get_json(silent=True) or {}
    rules = body.get('rules', [])

    if not rules:
        return v1_error_response('规则列表不能为空')
    if len(rules) > 3:
        return v1_error_response('一次最多添加3条规则')

    for rule in rules:
        if not rule.get('code', '').strip():
            return v1_error_response('股票代码不能为空')
        if rule.get('alert_type') not in VALID_ALERT_TYPES:
            return v1_error_response(f"预警类型无效: {rule.get('alert_type')}")
        if not rule.get('email', '').strip():
            return v1_error_response('收件邮箱不能为空')
        if rule.get('alert_type') in TYPES_WITH_THRESHOLD and rule.get('threshold') is None:
            return v1_error_response(f"{rule.get('alert_type')} 类型需要设置阈值")

    created_ids = []
    for rule in rules:
        code = rule['code'].strip().zfill(6)
        stock_name = get_stock_name_by_code(code) or ''
        new_id = execute_insert(
            "INSERT INTO alert_rules (user_id, code, stock_name, alert_type, threshold, direction, email) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, code, stock_name, rule['alert_type'],
             rule.get('threshold'), rule.get('direction'), rule['email'].strip())
        )
        created_ids.append(new_id)

    return v1_success_response(data={'created_ids': created_ids},
                               message=f'成功创建 {len(created_ids)} 条规则')


@alert_rules_bp.route('/api/alert-rules/<int:rule_id>', methods=['PUT'])
@login_required
def update_rule(rule_id):
    user_id = request.current_user['user_id']
    existing = execute_query("SELECT user_id FROM alert_rules WHERE id = %s", (rule_id,))
    if not existing or existing[0]['user_id'] != user_id:
        return v1_error_response('规则不存在或无权限')

    body = request.get_json(silent=True) or {}
    email = body.get('email', '').strip()
    if not email:
        return v1_error_response('收件邮箱不能为空')

    execute_write(
        "UPDATE alert_rules SET threshold = %s, direction = %s, email = %s WHERE id = %s",
        (body.get('threshold'), body.get('direction'), email, rule_id)
    )
    return v1_success_response(message='更新成功')


@alert_rules_bp.route('/api/alert-rules/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_rule(rule_id):
    user_id = request.current_user['user_id']
    existing = execute_query("SELECT user_id FROM alert_rules WHERE id = %s", (rule_id,))
    if not existing or existing[0]['user_id'] != user_id:
        return v1_error_response('规则不存在或无权限')

    execute_write("DELETE FROM alert_rules WHERE id = %s", (rule_id,))
    return v1_success_response(message='删除成功')


@alert_rules_bp.route('/api/alert-rules/<int:rule_id>/reactivate', methods=['POST'])
@login_required
def reactivate_rule(rule_id):
    user_id = request.current_user['user_id']
    existing = execute_query("SELECT user_id FROM alert_rules WHERE id = %s", (rule_id,))
    if not existing or existing[0]['user_id'] != user_id:
        return v1_error_response('规则不存在或无权限')

    execute_write(
        "UPDATE alert_rules SET status = 'active', triggered_at = NULL WHERE id = %s",
        (rule_id,)
    )
    return v1_success_response(message='已重新激活')


@alert_rules_bp.route('/api/alert-rules/<int:rule_id>/disable', methods=['POST'])
@login_required
def disable_rule(rule_id):
    user_id = request.current_user['user_id']
    existing = execute_query("SELECT user_id FROM alert_rules WHERE id = %s", (rule_id,))
    if not existing or existing[0]['user_id'] != user_id:
        return v1_error_response('规则不存在或无权限')

    execute_write(
        "UPDATE alert_rules SET status = 'disabled' WHERE id = %s",
        (rule_id,)
    )
    return v1_success_response(message='已停用')
```

- [ ] **Step 4: 更新 `backend/routes/__init__.py`**

在文件末尾 import 列表中添加：

```python
from .alert_rules import alert_rules_bp
```

在 `__all__` 列表中添加 `'alert_rules_bp'`

- [ ] **Step 5: 运行测试确认通过**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -m pytest tests/test_alert_rules_api.py -v
```

Expected: `8 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/routes/alert_rules.py backend/routes/__init__.py backend/tests/test_alert_rules_api.py
git commit -m "feat: add alert rules CRUD REST API"
```

---

### Task 6: 注册 Blueprint + 启动监控

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: 在 `app.py` 的 `register_blueprints` 中注册 `alert_rules_bp`**

在 `from routes import (` 的导入列表末尾添加 `alert_rules_bp,`，并在 `register_blueprints` 函数中添加：

```python
app.register_blueprint(alert_rules_bp)
```

- [ ] **Step 2: 启动预警监控服务**

在 `start_push_loop(socketio)` 调用之后追加：

```python
from services.alert_monitor import start_alert_monitor
from websocket_manager import adapter as _ws_adapter
start_alert_monitor(socketio, _ws_adapter)
```

- [ ] **Step 3: 重启后端并验证**

```bash
cd /Users/mac/Github/NiuNIuNiu && bash start.sh
sleep 3
curl -s http://localhost:9001/health
curl -s -X GET http://localhost:9001/api/alert-rules
```

Expected: health 返回 `{"status":"healthy",...}`，alert-rules 返回 `{"success":false,"message":"...token..."}` (未认证)

- [ ] **Step 4: 运行全部后端测试**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -m pytest tests/test_alert_notify.py tests/test_alert_monitor.py tests/test_alert_rules_api.py -v
```

Expected: 全部通过，无 FAIL

- [ ] **Step 5: Commit**

```bash
git add backend/app.py
git commit -m "feat: register alert blueprint and start alert monitor greenlet"
```

---

### Task 7: 前端页面

**Files:**
- Create: `frontend/src/pages/StockAlert/index.css`
- Create: `frontend/src/pages/StockAlert/index.js`

- [ ] **Step 1: 创建 `frontend/src/pages/StockAlert/index.css`**

```css
.alert-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 16px;
}

.alert-page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.alert-page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary, #1a1a1a);
  margin: 0;
}

.alert-table-wrap {
  background: var(--bg-card, #fff);
  border-radius: 8px;
  border: 1px solid var(--border-color, #e8e8e8);
  overflow: hidden;
  margin-bottom: 20px;
}

.alert-empty {
  text-align: center;
  padding: 40px;
  color: var(--text-muted, #aaa);
  font-size: 14px;
}

.alert-add-area {
  background: var(--bg-card, #fff);
  border-radius: 8px;
  border: 1px solid var(--border-color, #e8e8e8);
  padding: 20px;
}

.alert-add-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1a1a1a);
  margin-bottom: 16px;
}

.alert-add-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.alert-add-row {
  display: grid;
  grid-template-columns: 120px 130px 200px 1fr 32px;
  gap: 8px;
  align-items: center;
}

.alert-add-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  gap: 8px;
}

.alert-type-tag {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}
.alert-type-tag.change_pct  { background: #fff7e6; color: #d46b08; }
.alert-type-tag.limit_up    { background: #fff1f0; color: #cf1322; }
.alert-type-tag.limit_down  { background: #f6ffed; color: #389e0d; }
.alert-type-tag.seal_order  { background: #fff0f6; color: #c41d7f; }

.alert-status-tag {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 12px;
}
.alert-status-tag.active    { background: #f6ffed; color: #389e0d; }
.alert-status-tag.triggered { background: #fff7e6; color: #d46b08; }
.alert-status-tag.disabled  { background: #f5f5f5; color: #999; }

@media (max-width: 768px) {
  .alert-add-row {
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
}
```

- [ ] **Step 2: 创建 `frontend/src/pages/StockAlert/index.js`**

```jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Table, Button, Select, Input, InputNumber, Popconfirm, message, Tooltip, Space } from 'antd';
import { PlusOutlined, DeleteOutlined, ReloadOutlined, BellOutlined, PauseOutlined } from '@ant-design/icons';
import { apiRequest } from '../../config/api';
import './index.css';

const { Option } = Select;

const ALERT_TYPE_OPTIONS = [
  { value: 'limit_up',   label: '涨停' },
  { value: 'limit_down', label: '跌停' },
  { value: 'change_pct', label: '涨跌幅' },
  { value: 'seal_order', label: '涨停封单' },
];

const TYPE_LABELS   = { limit_up: '涨停', limit_down: '跌停', change_pct: '涨跌幅', seal_order: '涨停封单' };
const STATUS_LABELS = { active: '监控中', triggered: '已触发', disabled: '已停用' };

const EMPTY_ROW = () => ({ code: '', alert_type: 'limit_up', threshold: null, direction: 'above', email: '' });

export default function StockAlert() {
  const [rules, setRules]     = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [addRows, setAddRows] = useState([EMPTY_ROW()]);
  const [saving, setSaving]   = useState(false);

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiRequest('/api/alert-rules');
      if (res.success) setRules(res.data.items || []);
    } catch { message.error('加载失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchRules(); }, [fetchRules]);

  const handleAction = async (url, method = 'POST', successMsg = '操作成功') => {
    try {
      const res = await apiRequest(url, { method });
      if (res.success) { message.success(successMsg); fetchRules(); }
      else message.error(res.message);
    } catch { message.error('操作失败'); }
  };

  const updateRow = (idx, field, value) =>
    setAddRows(rows => rows.map((r, i) => i === idx ? { ...r, [field]: value } : r));

  const handleSave = async () => {
    for (const row of addRows) {
      if (!row.code.trim())  { message.warning('请填写股票代码'); return; }
      if (!row.email.trim()) { message.warning('请填写收件邮箱'); return; }
      if (['change_pct', 'seal_order'].includes(row.alert_type) && row.threshold === null) {
        message.warning('请填写阈值'); return;
      }
    }
    setSaving(true);
    try {
      const res = await apiRequest('/api/alert-rules/batch', {
        method: 'POST',
        body: JSON.stringify({ rules: addRows }),
      });
      if (res.success) {
        message.success(res.message || '保存成功');
        setAddRows([EMPTY_ROW()]);
        setShowAdd(false);
        fetchRules();
      } else {
        message.error(res.message || '保存失败');
      }
    } catch { message.error('保存失败'); }
    finally { setSaving(false); }
  };

  const thresholdCell = (row, idx) => {
    if (row.alert_type === 'change_pct') return (
      <Space.Compact style={{ width: '100%' }}>
        <Select value={row.direction} onChange={v => updateRow(idx, 'direction', v)} style={{ width: 80 }}>
          <Option value="above">涨超</Option>
          <Option value="below">跌超</Option>
        </Select>
        <InputNumber value={row.threshold} onChange={v => updateRow(idx, 'threshold', v)}
          min={0.1} max={20} step={0.5} placeholder="%" addonAfter="%" style={{ width: 100 }} />
      </Space.Compact>
    );
    if (row.alert_type === 'seal_order') return (
      <InputNumber value={row.threshold} onChange={v => updateRow(idx, 'threshold', v)}
        min={1} placeholder="封单万元" addonAfter="万元" style={{ width: '100%' }} />
    );
    return <span style={{ color: '#bbb', fontSize: 12, paddingLeft: 4 }}>无需设置</span>;
  };

  const thresholdText = (r) => {
    if (r.alert_type === 'change_pct')
      return `${r.direction === 'above' ? '涨超' : '跌超'}${r.threshold}%`;
    if (r.alert_type === 'seal_order') return `低于 ${r.threshold} 万元`;
    return '—';
  };

  const columns = [
    { title: '股票', dataIndex: 'code', width: 90,
      render: (code, r) => <><span style={{ fontWeight: 600 }}>{code}</span><br />
        <span style={{ fontSize: 11, color: '#888' }}>{r.stock_name}</span></> },
    { title: '类型', dataIndex: 'alert_type', width: 90,
      render: t => <span className={`alert-type-tag ${t}`}>{TYPE_LABELS[t] || t}</span> },
    { title: '阈值', width: 130, render: (_, r) => thresholdText(r) },
    { title: '收件邮箱', dataIndex: 'email', ellipsis: true },
    { title: '状态', dataIndex: 'status', width: 85,
      render: s => <span className={`alert-status-tag ${s}`}>{STATUS_LABELS[s] || s}</span> },
    { title: '触发时间', dataIndex: 'triggered_at', width: 145,
      render: t => t || <span style={{ color: '#bbb' }}>—</span> },
    { title: '操作', width: 110, render: (_, r) => (
      <Space size={4}>
        {r.status === 'triggered' && (
          <Tooltip title="重新激活">
            <Button size="small" icon={<ReloadOutlined />}
              onClick={() => handleAction(`/api/alert-rules/${r.id}/reactivate`, 'POST', '已激活')} />
          </Tooltip>
        )}
        {r.status === 'active' && (
          <Tooltip title="停用">
            <Button size="small" icon={<PauseOutlined />}
              onClick={() => handleAction(`/api/alert-rules/${r.id}/disable`, 'POST', '已停用')} />
          </Tooltip>
        )}
        <Popconfirm title="确认删除此预警规则？" onConfirm={() => handleAction(`/api/alert-rules/${r.id}`, 'DELETE', '已删除')}
          okText="删除" cancelText="取消">
          <Button size="small" icon={<DeleteOutlined />} danger />
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <div className="alert-page">
      <div className="alert-page-header">
        <h1 className="alert-page-title">
          <BellOutlined style={{ marginRight: 8 }} />条件预警
        </h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowAdd(v => !v)}>
          {showAdd ? '收起' : '新增预警'}
        </Button>
      </div>

      <div className="alert-table-wrap">
        {!loading && rules.length === 0
          ? <div className="alert-empty">暂无预警规则，点击「新增预警」开始设置</div>
          : <Table rowKey="id" columns={columns} dataSource={rules}
              loading={loading} pagination={false} size="small" />}
      </div>

      {showAdd && (
        <div className="alert-add-area">
          <div className="alert-add-title">新增预警规则（最多同时添加 3 条）</div>
          <div className="alert-add-rows">
            {addRows.map((row, idx) => (
              <div className="alert-add-row" key={idx}>
                <Input placeholder="股票代码" value={row.code} maxLength={6}
                  onChange={e => updateRow(idx, 'code', e.target.value.trim())} />
                <Select value={row.alert_type} onChange={v => updateRow(idx, 'alert_type', v)} style={{ width: '100%' }}>
                  {ALERT_TYPE_OPTIONS.map(o => <Option key={o.value} value={o.value}>{o.label}</Option>)}
                </Select>
                {thresholdCell(row, idx)}
                <Input placeholder="收件邮箱" value={row.email}
                  onChange={e => updateRow(idx, 'email', e.target.value.trim())} />
                <Button size="small" danger icon={<DeleteOutlined />}
                  disabled={addRows.length === 1} onClick={() => setAddRows(rows => rows.filter((_, i) => i !== idx))} />
              </div>
            ))}
          </div>
          <div className="alert-add-actions">
            {addRows.length < 3 && (
              <Button icon={<PlusOutlined />} onClick={() => setAddRows(rows => [...rows, EMPTY_ROW()])}>
                再加一条
              </Button>
            )}
            <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/StockAlert/
git commit -m "feat: add StockAlert frontend page with inline batch add"
```

---

### Task 8: 前端路由 + 导航

**Files:**
- Modify: `frontend/src/App.js`

- [ ] **Step 1: 添加 import**

在现有页面 import 列表末尾（`import PermissionCenter` 之后）添加：

```js
import StockAlert from './pages/StockAlert';
```

在 antd icons import 行中加入 `BellOutlined`。

- [ ] **Step 2: 在 `NAV_ITEMS` 中添加菜单项**

在 `{ key: '/permission-center', ... }` 之前插入：

```js
{ key: '/alert', icon: <BellOutlined />, label: '条件预警' },
```

- [ ] **Step 3: 在 `<Routes>` 中添加路由**

在现有路由列表末尾添加：

```jsx
<Route path="/alert" element={<RequireAuth><StockAlert /></RequireAuth>} />
```

- [ ] **Step 4: 启动前端验证**

```bash
cd /Users/mac/Github/NiuNIuNiu/frontend && npm start
```

验证清单：
- 导航栏出现「条件预警」菜单项
- 点击跳转到 `/alert`，页面标题「条件预警」正常显示
- 列表为空时显示引导文案
- 点「新增预警」展开表单，默认 1 行
- 点「再加一条」可加到 3 行，超过后按钮消失
- 切换类型为「涨跌幅」时出现方向选择 + 百分比输入
- 切换类型为「涨停封单」时出现万元输入
- 切换类型为「涨停/跌停」时阈值区显示「无需设置」
- 保存后列表刷新，可见新建规则

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.js
git commit -m "feat: add StockAlert route and nav menu item"
```

---

## 完整测试命令

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -m pytest tests/test_alert_notify.py tests/test_alert_monitor.py tests/test_alert_rules_api.py -v
```

Expected: 全部通过（约 28 个测试）
