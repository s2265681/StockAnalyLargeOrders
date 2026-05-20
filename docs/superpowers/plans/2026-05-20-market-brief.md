# 盘前资讯面板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在情绪周期页面顶部加一条横条，每天 8:30 定时生成海外市场夜盘涨跌 + AI 摘要并缓存入库，前端进页面直接读取展示。

**Architecture:** 独立 cron job 每日 8:30 调用 Sina Finance API 拉 5 只指数，再调 Claude 生成摘要，upsert 写入 `market_brief` 表；Flask 提供 `GET /api/market-brief/today`；React 组件在情绪周期页面顶部渲染横条，点击 AI 摘要文字弹出 Modal 展示完整内容。

**Tech Stack:** Python 3 (curl subprocess for external HTTP), Flask Blueprint, MySQL (execute_query / execute_write), `call_claude_for_scenario`, React + Ant Design Modal

---

## 文件结构

| 操作 | 路径 | 说明 |
|------|------|------|
| Create | `backend/migrations/20260520_create_market_brief.sql` | 建表 |
| Create | `backend/services/market_brief_service.py` | 指数拉取 / AI 摘要 / DB 读写 |
| Create | `backend/routes/market_brief.py` | REST 接口 |
| Create | `backend/jobs/market_brief_daily.py` | 定时任务入口 |
| Create | `backend/jobs/run_market_brief.sh` | Shell wrapper |
| Create | `backend/tests/test_market_brief.py` | 单元 + API 测试 |
| Create | `frontend/src/components/MarketBriefBar/index.js` | 横条组件 |
| Create | `frontend/src/components/MarketBriefBar/index.css` | 样式 |
| Modify | `backend/config/ai_config.py` | 新增 market_brief scenario |
| Modify | `backend/routes/__init__.py` | 导出 market_brief_bp |
| Modify | `backend/app.py` | 注册 blueprint |
| Modify | `backend/jobs/crontab.server.txt` | 添加 8:30 cron 条目 |
| Modify | `.github/workflows/deploy.yml` | 迁移列表追加新 sql |
| Modify | `frontend/src/pages/EmotionCycle/index.js` | 引入并渲染 MarketBriefBar |

---

## Task 1: DB 迁移 + deploy.yml

**Files:**
- Create: `backend/migrations/20260520_create_market_brief.sql`
- Modify: `.github/workflows/deploy.yml:91`

- [ ] **Step 1: 创建迁移文件**

```sql
-- backend/migrations/20260520_create_market_brief.sql
CREATE TABLE IF NOT EXISTS market_brief (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    brief_date   DATE     NOT NULL,
    overseas_json TEXT    NOT NULL,
    ai_summary   TEXT     NOT NULL,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_date (brief_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] **Step 2: 在 deploy.yml 追加迁移文件名**

在 `.github/workflows/deploy.yml` 第 91 行（`migrations/20260520_create_alert_rules.sql \` 之后的行 `migrations/20260520_create_page_daily_activity.sql`）前面插入新行，将原来：

```yaml
              migrations/20260520_create_alert_rules.sql \
              migrations/20260520_create_page_daily_activity.sql
```

改为：

```yaml
              migrations/20260520_create_alert_rules.sql \
              migrations/20260520_create_market_brief.sql \
              migrations/20260520_create_page_daily_activity.sql
```

- [ ] **Step 3: 在本地数据库手动建表验证**

```bash
cd backend
MYSQL_PWD=123456 mysql -h127.0.0.1 -P13306 -uroot stock < migrations/20260520_create_market_brief.sql
MYSQL_PWD=123456 mysql -h127.0.0.1 -P13306 -uroot stock -e "DESCRIBE market_brief;"
```

预期输出包含 `brief_date`、`overseas_json`、`ai_summary`、`generated_at` 列。

- [ ] **Step 4: commit**

```bash
git add backend/migrations/20260520_create_market_brief.sql .github/workflows/deploy.yml
git commit -m "feat: add market_brief table migration"
```

---

## Task 2: 后端服务 + AI scenario

**Files:**
- Create: `backend/services/market_brief_service.py`
- Modify: `backend/config/ai_config.py`
- Test: `backend/tests/test_market_brief.py`（部分）

- [ ] **Step 1: 在 ai_config.py 注册新 scenario**

找到 `_SCENARIO_TEMPLATES` 字典，在 `"dragon_tiger"` 行后面添加一行：

```python
    "market_brief": ("sonnet", 1024, 90, "盘前摘要"),
```

- [ ] **Step 2: 写失败测试（解析函数 + 服务读写）**

新建 `backend/tests/test_market_brief.py`：

```python
import json
import unittest
from unittest.mock import patch
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


SINA_SAMPLE = (
    'var hq_str_b_INDEXDOW="道琼斯指数,34061.32,33941.54,119.78,0.35,0.35%,05/20/2026,16:01:08";\n'
    'var hq_str_b_INDEXNASDAQ="纳斯达克,13456.78,13338.81,117.97,0.88,0.88%,05/20/2026,16:01:08";\n'
    'var hq_str_b_INDEXSP="标准普尔500,4321.00,4293.93,27.07,0.63,0.63%,05/20/2026,16:01:08";\n'
    'var hq_str_b_INDEXHK="恒生指数,18234.56,18293.00,-58.44,-0.32,-0.32%,05/20/2026,16:02:00";\n'
    'var hq_str_b_INDEXNK225="日经225,33567.00,33058.14,508.86,1.54,1.54%,05/20/2026,15:30:00";\n'
)


class TestParseSinaResponse(unittest.TestCase):
    def test_parses_five_indices(self):
        from services.market_brief_service import _parse_sina_response
        result = _parse_sina_response(SINA_SAMPLE)
        self.assertEqual(len(result), 5)

    def test_dow_values(self):
        from services.market_brief_service import _parse_sina_response
        result = _parse_sina_response(SINA_SAMPLE)
        dow = next(r for r in result if r['symbol'] == 'b_INDEXDOW')
        self.assertEqual(dow['name'], '道指')
        self.assertAlmostEqual(dow['close'], 34061.32)
        self.assertAlmostEqual(dow['change_pct'], 0.35)

    def test_negative_change(self):
        from services.market_brief_service import _parse_sina_response
        result = _parse_sina_response(SINA_SAMPLE)
        hk = next(r for r in result if r['symbol'] == 'b_INDEXHK')
        self.assertLess(hk['change_pct'], 0)

    def test_empty_response_raises(self):
        from services.market_brief_service import _parse_sina_response
        with self.assertRaises(RuntimeError):
            _parse_sina_response("garbage text no match")


class TestGetTodayBrief(unittest.TestCase):
    def test_returns_none_when_no_row(self):
        with patch('services.market_brief_service.execute_query', return_value=[]):
            from services.market_brief_service import get_today_brief
            self.assertIsNone(get_today_brief())

    def test_returns_dict_when_row_exists(self):
        overseas = [{"symbol": "b_INDEXDOW", "name": "道指", "close": 34061.32, "change_pct": 0.35}]
        fake_row = {
            'brief_date': '2026-05-20',
            'overseas_json': json.dumps(overseas),
            'ai_summary': '美股上涨，关注芯片。',
            'generated_at': '2026-05-20 08:30:12',
        }
        with patch('services.market_brief_service.execute_query', return_value=[fake_row]):
            from services.market_brief_service import get_today_brief
            result = get_today_brief()
        self.assertTrue(result is not None)
        self.assertEqual(result['brief_date'], '2026-05-20')
        self.assertEqual(result['overseas'][0]['name'], '道指')
        self.assertEqual(result['ai_summary'], '美股上涨，关注芯片。')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd backend
python -m pytest tests/test_market_brief.py -v 2>&1 | head -30
```

预期：`ImportError` 或 `ModuleNotFoundError`（service 还不存在）。

- [ ] **Step 4: 创建 `backend/services/market_brief_service.py`**

```python
"""盘前资讯服务：拉取海外指数、生成 AI 摘要、读写 market_brief 表"""
import json
import logging
import re
import subprocess
from datetime import date

from utils.db import execute_query, execute_write

logger = logging.getLogger(__name__)

_NAME_MAP = {
    'b_INDEXDOW':    '道指',
    'b_INDEXNASDAQ': '纳指',
    'b_INDEXSP':     '标普',
    'b_INDEXHK':     '恒指',
    'b_INDEXNK225':  '日经',
}


def _parse_sina_response(text: str) -> list[dict]:
    """解析新浪财经海外指数响应文本，返回指数列表。"""
    indices = []
    pattern = re.compile(r'var hq_str_(b_INDEX\w+)="([^"]+)"')
    for m in pattern.finditer(text):
        sym = m.group(1)
        fields = m.group(2).split(',')
        if len(fields) < 5:
            continue
        try:
            close = float(fields[1])
            change_pct = float(fields[4])
        except (ValueError, IndexError):
            continue
        indices.append({
            'symbol': sym,
            'name': _NAME_MAP.get(sym, sym),
            'close': close,
            'change_pct': round(change_pct, 2),
        })
    if not indices:
        raise RuntimeError('未从新浪财经解析到任何指数数据')
    return indices


def fetch_overseas_indices() -> list[dict]:
    """用 curl 子进程拉取新浪财经海外指数（eventlet 安全）。"""
    symbols = 'b_INDEXDOW,b_INDEXNASDAQ,b_INDEXSP,b_INDEXHK,b_INDEXNK225'
    url = f'https://hq.sinajs.cn/list={symbols}'
    result = subprocess.run(
        ['curl', '-s', '--max-time', '15',
         '-H', 'Referer: https://finance.sina.com.cn', url],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f'curl 拉取指数失败: {result.stderr.strip()}')
    return _parse_sina_response(result.stdout)


def generate_ai_summary(overseas: list[dict]) -> str:
    """调用 Claude 生成摘要文本。"""
    lines = []
    for idx in overseas:
        sign = '+' if idx['change_pct'] >= 0 else ''
        lines.append(f"- {idx['name']}：{sign}{idx['change_pct']}%")

    prompt = (
        '今日盘前海外市场数据（昨夜收盘）：\n'
        + '\n'.join(lines)
        + '\n\n请生成一份简洁的今日A股盘前参考摘要，包含：'
        '\n1. 海外市场简评（1-2句）'
        '\n2. 今日A股值得关注的板块方向（2-3个，结合海外表现推断）'
        '\n3. 风险提示（1句）'
        '\n\n要求：纯中文，总字数不超过200字，不需要任何标题，直接正文。'
    )

    from utils.claude_client import call_claude_for_scenario
    text = call_claude_for_scenario('market_brief', prompt)
    if not text:
        raise RuntimeError('Claude 返回空摘要')
    return text


def save_brief(brief_date: str, overseas: list[dict], ai_summary: str) -> None:
    """upsert 当日盘前资讯到 market_brief 表。"""
    overseas_json = json.dumps(overseas, ensure_ascii=False)
    execute_write(
        'INSERT INTO market_brief (brief_date, overseas_json, ai_summary, generated_at) '
        'VALUES (%s, %s, %s, NOW()) '
        'ON DUPLICATE KEY UPDATE overseas_json=%s, ai_summary=%s, generated_at=NOW()',
        (brief_date, overseas_json, ai_summary, overseas_json, ai_summary),
    )
    logger.info('已保存 market_brief date=%s', brief_date)


def get_today_brief() -> dict | None:
    """读取今日盘前资讯，无数据时返回 None。"""
    today = date.today().isoformat()
    rows = execute_query(
        'SELECT brief_date, overseas_json, ai_summary, generated_at '
        'FROM market_brief WHERE brief_date = %s',
        (today,),
    )
    if not rows:
        return None
    r = rows[0]
    return {
        'brief_date': str(r['brief_date']),
        'overseas': json.loads(r['overseas_json']),
        'ai_summary': r['ai_summary'],
        'generated_at': str(r['generated_at']),
    }
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd backend
python -m pytest tests/test_market_brief.py -v
```

预期：7 个测试全部 PASS。

- [ ] **Step 6: commit**

```bash
git add backend/config/ai_config.py backend/services/market_brief_service.py backend/tests/test_market_brief.py
git commit -m "feat: market_brief service + AI scenario + tests"
```

---

## Task 3: Flask 路由

**Files:**
- Create: `backend/routes/market_brief.py`
- Modify: `backend/routes/__init__.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_market_brief.py`（追加 API 测试）

- [ ] **Step 1: 在 test_market_brief.py 追加 API 测试类**

在文件末尾（`if __name__ == '__main__':` 前）追加：

```python
def _make_app():
    from utils.env import load_env
    load_env()
    import eventlet
    eventlet.monkey_patch()
    from flask import Flask
    from flask_cors import CORS
    app = Flask(__name__)
    CORS(app)
    from routes.market_brief import market_brief_bp
    app.register_blueprint(market_brief_bp)
    return app


class TestMarketBriefAPI(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.client = self.app.test_client()

    def test_today_returns_unavailable_when_no_data(self):
        with patch('services.market_brief_service.execute_query', return_value=[]):
            resp = self.client.get('/api/market-brief/today')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.data)
        self.assertTrue(body['success'])
        self.assertFalse(body['data']['available'])

    def test_today_returns_data_when_available(self):
        overseas = [{"symbol": "b_INDEXDOW", "name": "道指", "close": 34061.32, "change_pct": 0.35}]
        fake_row = {
            'brief_date': '2026-05-20',
            'overseas_json': json.dumps(overseas),
            'ai_summary': '美股上涨。',
            'generated_at': '2026-05-20 08:30:00',
        }
        with patch('services.market_brief_service.execute_query', return_value=[fake_row]):
            resp = self.client.get('/api/market-brief/today')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.data)
        self.assertTrue(body['data']['available'])
        self.assertEqual(body['data']['brief_date'], '2026-05-20')
        self.assertEqual(len(body['data']['overseas']), 1)
        self.assertEqual(body['data']['ai_summary'], '美股上涨。')
```

- [ ] **Step 2: 运行新增测试，确认失败（路由不存在）**

```bash
cd backend
python -m pytest tests/test_market_brief.py::TestMarketBriefAPI -v 2>&1 | head -20
```

预期：`ImportError` 或 404。

- [ ] **Step 3: 创建 `backend/routes/market_brief.py`**

```python
"""盘前资讯 API"""
import logging
from flask import Blueprint
from utils.response import v1_success_response
from services.market_brief_service import get_today_brief

logger = logging.getLogger(__name__)

market_brief_bp = Blueprint('market_brief', __name__)


@market_brief_bp.route('/api/market-brief/today', methods=['GET'])
def today_brief():
    brief = get_today_brief()
    if brief is None:
        return v1_success_response({'available': False})
    return v1_success_response({'available': True, **brief})
```

- [ ] **Step 4: 在 `backend/routes/__init__.py` 导出**

在 `from .analytics import analytics_bp` 下面加一行：

```python
from .market_brief import market_brief_bp
```

在 `__all__` 列表的 `'analytics_bp',` 后面加一项：

```python
    'market_brief_bp',
```

- [ ] **Step 5: 在 `backend/app.py` 注册 blueprint**

在 `from routes import (` 的导入列表中（`analytics_bp,` 后面）加：

```python
    market_brief_bp,
```

在 `register_blueprints` 函数中（`app.register_blueprint(analytics_bp)` 后面）加：

```python
    app.register_blueprint(market_brief_bp)
```

- [ ] **Step 6: 运行全部测试**

```bash
cd backend
python -m pytest tests/test_market_brief.py -v
```

预期：所有测试 PASS（包括 2 个 API 测试）。

- [ ] **Step 7: commit**

```bash
git add backend/routes/market_brief.py backend/routes/__init__.py backend/app.py backend/tests/test_market_brief.py
git commit -m "feat: market_brief REST endpoint"
```

---

## Task 4: 定时任务

**Files:**
- Create: `backend/jobs/market_brief_daily.py`
- Create: `backend/jobs/run_market_brief.sh`
- Modify: `backend/jobs/crontab.server.txt`

- [ ] **Step 1: 创建 `backend/jobs/market_brief_daily.py`**

```python
#!/usr/bin/env python3
"""
盘前资讯定时任务：拉取海外指数 + AI 摘要并写库。

用法：
  python jobs/market_brief_daily.py          # 今日
  python jobs/market_brief_daily.py force    # 强制重跑（同一天再跑一次）

建议 crontab（工作日 8:30）：
  30 8 * * 1-5 /path/to/run_market_brief.sh >> /path/to/logs/market_brief_job.log 2>&1
"""
import logging
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.market_brief_service import (
    fetch_overseas_indices,
    generate_ai_summary,
    save_brief,
    get_today_brief,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('market_brief_daily')


def main():
    force = len(sys.argv) > 1 and sys.argv[1].lower() in ('force', '1', 'yes')
    today = date.today().isoformat()

    if not force and get_today_brief() is not None:
        logger.info('今日 %s 已有摘要，跳过（传 force 强制重跑）', today)
        return

    logger.info('===== 盘前资讯任务 date=%s force=%s =====', today, force)

    logger.info('拉取海外指数...')
    overseas = fetch_overseas_indices()
    summary_parts = [f"{i['name']} {'+' if i['change_pct'] >= 0 else ''}{i['change_pct']}%" for i in overseas]
    logger.info('指数: %s', ', '.join(summary_parts))

    logger.info('生成 AI 摘要...')
    summary = generate_ai_summary(overseas)
    logger.info('摘要（前50字）: %s', summary[:50])

    save_brief(today, overseas, summary)
    logger.info('===== 任务完成 date=%s =====', today)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 创建 `backend/jobs/run_market_brief.sh`**

```bash
#!/bin/bash
# 盘前资讯定时任务：每日 8:30 生成海外指数 + AI 摘要
set -euo pipefail
JOB_NAME=market_brief
# shellcheck source=job_lib.sh
source "$(dirname "$0")/job_lib.sh"
job_setup
job_skip_if_not_trading_day
job_acquire_lock market_brief
job_run "$PYTHON" jobs/market_brief_daily.py
```

- [ ] **Step 3: 给 shell 脚本加可执行权限**

```bash
chmod +x backend/jobs/run_market_brief.sh
```

- [ ] **Step 4: 在 `backend/jobs/crontab.server.txt` 末尾添加 cron 条目**

在文件末尾（`5 15 * * 1-5 ...` 行之后）追加：

```
# --- 4. 盘前资讯 ---
30 8 * * 1-5 ${NIU_ROOT}/backend/jobs/run_market_brief.sh >> ${NIU_LOG}/market_brief_job.log 2>&1
```

- [ ] **Step 5: 本地手动跑一次验证任务可正常执行**

```bash
cd backend
./venv/bin/python jobs/market_brief_daily.py force 2>&1
```

预期：看到"指数: 道指 +x.xx%, 纳指 ..."日志，然后"摘要（前50字）: ..."，最后"任务完成"。

- [ ] **Step 6: 验证数据写入 DB**

```bash
MYSQL_PWD=123456 mysql -h127.0.0.1 -P13306 -uroot stock \
  -e "SELECT brief_date, LEFT(ai_summary, 50), generated_at FROM market_brief ORDER BY id DESC LIMIT 1;"
```

预期：能看到今日日期、摘要前50字、生成时间。

- [ ] **Step 7: commit**

```bash
git add backend/jobs/market_brief_daily.py backend/jobs/run_market_brief.sh backend/jobs/crontab.server.txt
git commit -m "feat: market_brief daily job + shell wrapper + crontab"
```

---

## Task 5: 前端 MarketBriefBar 组件

**Files:**
- Create: `frontend/src/components/MarketBriefBar/index.js`
- Create: `frontend/src/components/MarketBriefBar/index.css`

- [ ] **Step 1: 创建 `frontend/src/components/MarketBriefBar/index.css`**

```css
.market-brief-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  padding: 0 16px;
  height: 36px;
  min-height: 36px;
  font-size: 12px;
  overflow: hidden;
}

.market-brief-label {
  font-size: 11px;
  color: #999;
  margin-right: 12px;
  white-space: nowrap;
}

.market-brief-index {
  margin-right: 16px;
  white-space: nowrap;
}

.market-brief-index b.up   { color: #f5222d; }
.market-brief-index b.down { color: #52c41a; }

.market-brief-divider {
  color: #e0e0e0;
  margin-right: 16px;
}

.market-brief-summary {
  color: #1677ff;
  cursor: pointer;
  white-space: nowrap;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.market-brief-summary:hover { text-decoration: underline; }

.market-brief-time {
  margin-left: auto;
  font-size: 11px;
  color: #bbb;
  white-space: nowrap;
}
```

- [ ] **Step 2: 创建 `frontend/src/components/MarketBriefBar/index.js`**

```jsx
import React, { useState, useEffect } from 'react';
import { Modal } from 'antd';
import { apiRequest } from '../../config/api';
import './index.css';

const FLAG_MAP = {
  b_INDEXDOW:    '🇺🇸',
  b_INDEXNASDAQ: '🇺🇸',
  b_INDEXSP:     '🇺🇸',
  b_INDEXHK:     '🇭🇰',
  b_INDEXNK225:  '🇯🇵',
};

export default function MarketBriefBar() {
  const [brief, setBrief]       = useState(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    apiRequest('/api/market-brief/today')
      .then(res => {
        if (res.success && res.data.available) setBrief(res.data);
      })
      .catch(() => {});
  }, []);

  if (!brief) return null;

  const preview = brief.ai_summary.length > 40
    ? brief.ai_summary.slice(0, 40) + '…'
    : brief.ai_summary;

  return (
    <>
      <div className="market-brief-bar">
        <span className="market-brief-label">盘前参考</span>

        {brief.overseas.map(idx => (
          <span key={idx.symbol} className="market-brief-index">
            {FLAG_MAP[idx.symbol] || ''} {idx.name}{' '}
            <b className={idx.change_pct >= 0 ? 'up' : 'down'}>
              {idx.change_pct >= 0 ? '+' : ''}{idx.change_pct}%
            </b>
          </span>
        ))}

        <span className="market-brief-divider">|</span>

        <span className="market-brief-summary" onClick={() => setModalOpen(true)}>
          📰 AI摘要：{preview} →
        </span>

        <span className="market-brief-time">
          {brief.generated_at.slice(11, 16)} 更新
        </span>
      </div>

      <Modal
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        title="今日盘前 AI 摘要"
        width={560}
      >
        <p style={{ fontSize: 12, color: '#aaa', marginTop: 0, marginBottom: 16 }}>
          {brief.brief_date} {brief.generated_at.slice(11, 16)} 生成
        </p>
        <div style={{ fontSize: 13, lineHeight: 2, color: '#333', whiteSpace: 'pre-wrap' }}>
          {brief.ai_summary}
        </div>
      </Modal>
    </>
  );
}
```

- [ ] **Step 3: commit**

```bash
git add frontend/src/components/MarketBriefBar/
git commit -m "feat: MarketBriefBar component"
```

---

## Task 6: 接入 EmotionCycle 页面

**Files:**
- Modify: `frontend/src/pages/EmotionCycle/index.js:432-433`

- [ ] **Step 1: 在 EmotionCycle/index.js 顶部导入组件**

在文件顶部（其他 import 之后，第 18 行 `import './index.css';` 之前）加：

```js
import MarketBriefBar from '../../components/MarketBriefBar';
```

- [ ] **Step 2: 在 JSX return 内顶部插入组件**

在 `return (` 的 `<div className="emotion-cycle-container">` 标签（第 433 行）之后、`<div className="page-date-nav">` 之前，插入：

```jsx
      <MarketBriefBar />
```

修改后结构：

```jsx
  return (
    <div className="emotion-cycle-container">
      <MarketBriefBar />
      <div className="page-date-nav">
```

- [ ] **Step 3: 启动前端开发服务器验证渲染**

```bash
cd frontend
npm start
```

打开 `http://localhost:3000`，导航到情绪周期页面：

- 若后端有今日数据：顶部应出现 36px 横条，显示道指/纳指等涨跌幅 + 蓝色 AI 摘要入口
- 若后端无数据（`available: false`）：横条不渲染，页面与原来相同（无报错）
- 点击蓝色摘要文字：弹出 Modal 显示完整摘要

- [ ] **Step 4: commit**

```bash
git add frontend/src/pages/EmotionCycle/index.js
git commit -m "feat: wire MarketBriefBar into EmotionCycle page"
```

---

## 完成检查

- [ ] `python -m pytest backend/tests/test_market_brief.py -v` 全部通过
- [ ] `python backend/jobs/market_brief_daily.py force` 运行成功，DB 写入数据
- [ ] `GET /api/market-brief/today` 返回正确 JSON
- [ ] 情绪周期页面顶部横条正常渲染，点击弹窗展示摘要
- [ ] deploy.yml 已包含新迁移文件名
