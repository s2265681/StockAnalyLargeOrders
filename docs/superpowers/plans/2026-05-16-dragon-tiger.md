# 核心游资（龙虎榜）模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增"核心游资"页面，展示龙虎榜买卖席位详情，识别游资高亮，支持日期切换，并提供 AI 资金意图解读（数据统一入库避免重复）。

**Architecture:** 后端新增 `dragon_tiger.py` 路由和 `dragon_tiger_service.py` 服务层，使用 akshare 拉取数据写入 3 张 MySQL 表（daily/seats/ai），有缓存则直接返回。前端新增 `DragonTiger` 页面，两栏布局（左：股票列表，右：席位详情），复用现有暗色主题风格。

**Tech Stack:** Python/Flask, akshare 1.17.20, MySQL/pymysql, React, Ant Design

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/migrations/create_dragon_tiger_tables.sql` | 新建 | 建表 SQL |
| `backend/services/dragon_tiger_service.py` | 新建 | DB CRUD 操作 |
| `backend/routes/dragon_tiger.py` | 新建 | 两个 API 端点 |
| `backend/routes/__init__.py` | 修改 | 注册 Blueprint |
| `backend/app.py` | 修改 | register_blueprints |
| `frontend/src/pages/DragonTiger/index.js` | 新建 | 主页面组件 |
| `frontend/src/pages/DragonTiger/index.css` | 新建 | 暗色主题样式 |
| `frontend/src/App.js` | 修改 | 路由 + 菜单 |

---

## Task 1: 建表 SQL + 执行建表

**Files:**
- Create: `backend/migrations/create_dragon_tiger_tables.sql`

- [ ] **Step 1: 写建表 SQL**

```sql
-- backend/migrations/create_dragon_tiger_tables.sql

CREATE TABLE IF NOT EXISTS dragon_tiger_daily (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL COMMENT '格式YYYYMMDD',
  code VARCHAR(6) NOT NULL,
  name VARCHAR(20) NOT NULL,
  change_pct DECIMAL(8,4) DEFAULT 0 COMMENT '涨跌幅',
  close_price DECIMAL(10,2) DEFAULT 0,
  net_buy DECIMAL(20,2) DEFAULT 0 COMMENT '龙虎榜净买额(元)',
  buy_amount DECIMAL(20,2) DEFAULT 0 COMMENT '龙虎榜买入额',
  sell_amount DECIMAL(20,2) DEFAULT 0 COMMENT '龙虎榜卖出额',
  lhb_amount DECIMAL(20,2) DEFAULT 0 COMMENT '龙虎榜成交额',
  total_amount DECIMAL(20,2) DEFAULT 0 COMMENT '市场总成交额',
  reason VARCHAR(300) DEFAULT '' COMMENT '上榜原因',
  interpret VARCHAR(200) DEFAULT '' COMMENT '解读',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_code (date, code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='龙虎榜每日股票列表';

CREATE TABLE IF NOT EXISTS dragon_tiger_seats (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL,
  code VARCHAR(6) NOT NULL,
  direction ENUM('buy','sell') NOT NULL COMMENT '买入/卖出席位',
  rank_no INT NOT NULL COMMENT '席位排名1-5',
  seat_name VARCHAR(150) DEFAULT '' COMMENT '营业部名称',
  buy_amount DECIMAL(20,2) DEFAULT 0 COMMENT '买入金额',
  sell_amount DECIMAL(20,2) DEFAULT 0 COMMENT '卖出金额',
  net_amount DECIMAL(20,2) DEFAULT 0 COMMENT '净额',
  is_hot_money TINYINT(1) DEFAULT 0 COMMENT '是否游资席位',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_date_code (date, code),
  INDEX idx_date_code_dir (date, code, direction)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='龙虎榜席位明细';

CREATE TABLE IF NOT EXISTS dragon_tiger_ai (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL,
  code VARCHAR(6) NOT NULL,
  analysis TEXT COMMENT 'AI分析内容',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_code (date, code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='龙虎榜AI分析结果';
```

- [ ] **Step 2: 连接数据库执行建表**

```bash
mysql -u root -p123456 stock < backend/migrations/create_dragon_tiger_tables.sql
```

Expected: 无报错，3张表创建成功。验证：
```bash
mysql -u root -p123456 stock -e "SHOW TABLES LIKE 'dragon_tiger%';"
```
Expected output:
```
+------------------------------+
| Tables_in_stock (dragon_tiger%) |
+------------------------------+
| dragon_tiger_ai              |
| dragon_tiger_daily           |
| dragon_tiger_seats           |
+------------------------------+
```

- [ ] **Step 3: 提交**

```bash
git add backend/migrations/create_dragon_tiger_tables.sql
git commit -m "feat: add dragon tiger tables migration SQL"
```

---

## Task 2: 后端服务层

**Files:**
- Create: `backend/services/dragon_tiger_service.py`

- [ ] **Step 1: 写服务层**

```python
# backend/services/dragon_tiger_service.py
"""
龙虎榜数据库存取服务
"""
import logging
from utils.db import execute_query, execute_write, execute_many

logger = logging.getLogger(__name__)


def get_daily_stocks(date: str) -> list:
    """获取指定日期的龙虎榜股票列表（含席位数据）"""
    stocks = execute_query(
        "SELECT * FROM dragon_tiger_daily WHERE date = %s ORDER BY ABS(net_buy) DESC",
        (date,),
    )
    if not stocks:
        return []
    codes = [s["code"] for s in stocks]
    if not codes:
        return stocks
    placeholders = ",".join(["%s"] * len(codes))
    seats = execute_query(
        f"SELECT * FROM dragon_tiger_seats WHERE date = %s AND code IN ({placeholders})"
        f" ORDER BY direction, rank_no",
        [date] + codes,
    )
    seat_map = {}
    for seat in seats:
        key = (seat["code"], seat["direction"])
        seat_map.setdefault(key, []).append(seat)
    for stock in stocks:
        code = stock["code"]
        stock["buy_seats"] = seat_map.get((code, "buy"), [])
        stock["sell_seats"] = seat_map.get((code, "sell"), [])
    return stocks


def save_daily_stocks(date: str, stocks: list) -> None:
    """批量写入龙虎榜股票列表（upsert）"""
    if not stocks:
        return
    sql = """
        INSERT INTO dragon_tiger_daily
          (date, code, name, change_pct, close_price, net_buy, buy_amount, sell_amount,
           lhb_amount, total_amount, reason, interpret)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          name=VALUES(name), change_pct=VALUES(change_pct),
          close_price=VALUES(close_price), net_buy=VALUES(net_buy),
          buy_amount=VALUES(buy_amount), sell_amount=VALUES(sell_amount),
          lhb_amount=VALUES(lhb_amount), total_amount=VALUES(total_amount),
          reason=VALUES(reason), interpret=VALUES(interpret)
    """
    params = [
        (date, s["code"], s["name"], s["change_pct"], s["close_price"],
         s["net_buy"], s["buy_amount"], s["sell_amount"],
         s["lhb_amount"], s["total_amount"], s["reason"], s["interpret"])
        for s in stocks
    ]
    execute_many(sql, params)


def save_seats(date: str, seats: list) -> None:
    """批量写入席位明细（先删后插，保证幂等）"""
    if not seats:
        return
    codes = list({s["code"] for s in seats})
    directions = list({s["direction"] for s in seats})
    if not codes or not directions:
        return
    code_ph = ",".join(["%s"] * len(codes))
    dir_ph = ",".join(["%s"] * len(directions))
    execute_write(
        f"DELETE FROM dragon_tiger_seats WHERE date=%s AND code IN ({code_ph})"
        f" AND direction IN ({dir_ph})",
        [date] + codes + directions,
    )
    sql = """
        INSERT INTO dragon_tiger_seats
          (date, code, direction, rank_no, seat_name, buy_amount, sell_amount,
           net_amount, is_hot_money)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    params = [
        (date, s["code"], s["direction"], s["rank_no"], s["seat_name"],
         s["buy_amount"], s["sell_amount"], s["net_amount"], s["is_hot_money"])
        for s in seats
    ]
    execute_many(sql, params)


def get_ai_analysis(date: str, code: str) -> str | None:
    """获取已有AI分析，无则返回None"""
    rows = execute_query(
        "SELECT analysis FROM dragon_tiger_ai WHERE date=%s AND code=%s",
        (date, code),
    )
    return rows[0]["analysis"] if rows else None


def save_ai_analysis(date: str, code: str, analysis: str) -> None:
    """保存AI分析结果（upsert）"""
    execute_write(
        """
        INSERT INTO dragon_tiger_ai (date, code, analysis)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE analysis=VALUES(analysis), updated_at=CURRENT_TIMESTAMP
        """,
        (date, code, analysis),
    )
```

- [ ] **Step 2: 提交**

```bash
git add backend/services/dragon_tiger_service.py
git commit -m "feat: add dragon tiger DB service layer"
```

---

## Task 3: 后端路由

**Files:**
- Create: `backend/routes/dragon_tiger.py`

- [ ] **Step 1: 写路由文件**

```python
# backend/routes/dragon_tiger.py
"""
龙虎榜接口模块
- GET  /api/v1/dragon-tiger?date=YYYYMMDD   获取龙虎榜列表（含席位）
- POST /api/v1/dragon-tiger/ai-analysis     AI解读（有缓存直接返回）
"""
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime

import requests
from flask import Blueprint, request

from utils.response import v1_success_response, v1_error_response
from services.dragon_tiger_service import (
    get_daily_stocks,
    save_daily_stocks,
    save_seats,
    get_ai_analysis,
    save_ai_analysis,
)

logger = logging.getLogger(__name__)

dragon_tiger_bp = Blueprint("dragon_tiger", __name__)

CLAUDE_API_URL = os.environ.get(
    "CLAUDE_API_URL", "https://token.kalowave.com/v1/chat/completions"
)
CLAUDE_API_KEY = os.environ.get(
    "CLAUDE_API_KEY",
    "sk-9bs6AtWPA7p0vs6Rnz0lxP6VOpufoWSQGV8MAS0i3ncqMGB7",
)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

# 游资席位名称关键词
HOT_MONEY_KEYWORDS = [
    "知春路", "成都", "宁波", "佛山", "拉萨",
    "乐清千帆", "温州", "绍兴", "华鑫证券",
    "财通证券", "游资",
]


def _is_hot_money(seat_name: str) -> bool:
    """根据席位名称关键词识别游资"""
    return any(kw in seat_name for kw in HOT_MONEY_KEYWORDS)


def _fmt_amount(val) -> float:
    """akshare返回的金额可能是 float/NaN，统一处理为 float"""
    try:
        v = float(val)
        return 0.0 if v != v else round(v, 2)  # NaN check
    except (TypeError, ValueError):
        return 0.0


def _fetch_from_akshare(date: str) -> list:
    """从akshare拉取龙虎榜数据（列表+席位），返回股票列表（含 buy_seats/sell_seats）"""
    import akshare as ak
    from concurrent.futures import ThreadPoolExecutor

    # 1. 拉取当日股票列表
    df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
    if df is None or df.empty:
        return []

    stocks = []
    for _, row in df.iterrows():
        code = str(row.get("代码", "")).zfill(6)
        if not code or code == "000000":
            continue
        stocks.append({
            "code": code,
            "name": str(row.get("名称", "")),
            "change_pct": _fmt_amount(row.get("涨跌幅", 0)),
            "close_price": _fmt_amount(row.get("收盘价", 0)),
            "net_buy": _fmt_amount(row.get("龙虎榜净买额", 0)),
            "buy_amount": _fmt_amount(row.get("龙虎榜买入额", 0)),
            "sell_amount": _fmt_amount(row.get("龙虎榜卖出额", 0)),
            "lhb_amount": _fmt_amount(row.get("龙虎榜成交额", 0)),
            "total_amount": _fmt_amount(row.get("市场总成交额", 0)),
            "reason": str(row.get("上榜原因", "") or ""),
            "interpret": str(row.get("解读", "") or ""),
            "buy_seats": [],
            "sell_seats": [],
        })

    if not stocks:
        return []

    # 2. 并行拉取每只股票的买卖席位
    def _fetch_seats(stock):
        code = stock["code"]
        all_seats = []
        for direction, flag in [("buy", "买入"), ("sell", "卖出")]:
            try:
                sdf = ak.stock_lhb_stock_detail_em(symbol=code, date=date, flag=flag)
                if sdf is None or sdf.empty:
                    continue
                for i, srow in sdf.iterrows():
                    seat_name = str(srow.get("交易营业部名称", "") or "").strip()
                    all_seats.append({
                        "code": code,
                        "direction": direction,
                        "rank_no": int(srow.get("序号", i + 1)),
                        "seat_name": seat_name,
                        "buy_amount": _fmt_amount(srow.get("买入金额", 0)),
                        "sell_amount": _fmt_amount(srow.get("卖出金额", 0)),
                        "net_amount": _fmt_amount(srow.get("净额", 0)),
                        "is_hot_money": 1 if _is_hot_money(seat_name) else 0,
                    })
            except Exception as e:
                logger.warning(f"拉取{code} {flag}席位失败: {e}")
        return all_seats

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(_fetch_seats, stocks))

    all_seats = []
    seat_map = {}
    for seat_list in results:
        for seat in seat_list:
            all_seats.append(seat)
            key = (seat["code"], seat["direction"])
            seat_map.setdefault(key, []).append(seat)

    for stock in stocks:
        code = stock["code"]
        stock["buy_seats"] = seat_map.get((code, "buy"), [])
        stock["sell_seats"] = seat_map.get((code, "sell"), [])

    return stocks, all_seats


def _call_claude(prompt: str) -> str:
    """调用 Claude API（复用项目现有模式）"""
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    })
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(payload)
        payload_file = f.name
    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "90", CLAUDE_API_URL,
             "-H", f"Authorization: Bearer {CLAUDE_API_KEY}",
             "-H", "Content-Type: application/json",
             "-d", f"@{payload_file}"],
            capture_output=True, text=True, timeout=95,
        )
        os.unlink(payload_file)
        if proc.returncode != 0:
            return ""
        body = json.loads(proc.stdout)
        if "error" in body:
            logger.error(f"Claude API 错误: {body['error']}")
            return ""
        return (body.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", ""))
    except Exception as e:
        logger.error(f"Claude API调用失败: {e}")
        return ""


def _build_ai_prompt(stock: dict) -> str:
    """构建AI分析prompt"""
    def fmt(val):
        v = float(val or 0)
        if abs(v) >= 1e8:
            return f"{v/1e8:.2f}亿"
        if abs(v) >= 1e4:
            return f"{v/1e4:.0f}万"
        return f"{v:.0f}元"

    def seat_lines(seats, label):
        if not seats:
            return f"{label}：无数据\n"
        lines = [f"{label}："]
        for s in seats:
            hm = "【游资】" if s.get("is_hot_money") else ""
            lines.append(
                f"  {s['rank_no']}. {s['seat_name']}{hm}"
                f"  买入{fmt(s['buy_amount'])} 卖出{fmt(s['sell_amount'])} 净额{fmt(s['net_amount'])}"
            )
        return "\n".join(lines) + "\n"

    return f"""你是A股龙虎榜资深分析师，请对以下龙虎榜数据进行专业解读。

股票：{stock['name']}（{stock['code']}）
涨跌幅：{stock['change_pct']}%
上榜原因：{stock['reason']}
龙虎榜净买额：{fmt(stock['net_buy'])}
龙虎榜买入额：{fmt(stock['buy_amount'])}
龙虎榜卖出额：{fmt(stock['sell_amount'])}

{seat_lines(stock.get('buy_seats', []), '买入席位')}
{seat_lines(stock.get('sell_seats', []), '卖出席位')}

请从以下角度分析（300字以内，简洁明了）：
1. 资金性质：各席位属于游资/机构/北向，主要资金属性是什么
2. 操作意图：主力是净买入还是净卖出，对倒可能性如何
3. 游资行为：游资席位的操作特征和意图
4. 综合判断：当前筹码结构和后市参考

直接输出分析内容，不要分点列表，用自然段落。"""


@dragon_tiger_bp.route("/api/v1/dragon-tiger", methods=["GET"])
def get_dragon_tiger():
    """获取龙虎榜列表（含席位），有DB缓存则直接返回"""
    date = request.args.get("date", datetime.now().strftime("%Y%m%d"))
    date = date.replace("-", "")

    try:
        # 1. 优先从DB加载
        stocks = get_daily_stocks(date)
        if stocks:
            return v1_success_response(data={"date": date, "stocks": stocks, "source": "db"})

        # 2. 无DB数据，调akshare
        result = _fetch_from_akshare(date)
        if not result:
            return v1_success_response(data={"date": date, "stocks": [], "source": "api"})

        stocks, all_seats = result

        # 3. 写入DB
        save_daily_stocks(date, stocks)
        save_seats(date, all_seats)

        return v1_success_response(data={"date": date, "stocks": stocks, "source": "api"})

    except Exception as e:
        logger.error(f"获取龙虎榜失败: {e}", exc_info=True)
        return v1_error_response(message=f"获取龙虎榜失败: {str(e)}")


@dragon_tiger_bp.route("/api/v1/dragon-tiger/ai-analysis", methods=["POST"])
def ai_analysis():
    """AI解读龙虎榜资金意图（有DB缓存则直接返回，不重复分析）"""
    body = request.get_json(silent=True) or {}
    date = (body.get("date", "") or "").replace("-", "")
    code = (body.get("code", "") or "").zfill(6)

    if not date or not code:
        return v1_error_response(message="请提供date和code")

    try:
        # 1. 检查DB缓存
        cached = get_ai_analysis(date, code)
        if cached:
            return v1_success_response(data={"analysis": cached, "cached": True})

        # 2. 加载股票数据构建prompt
        stocks = get_daily_stocks(date)
        stock = next((s for s in stocks if s["code"] == code), None)
        if not stock:
            return v1_error_response(message=f"未找到{date}日{code}的龙虎榜数据")

        prompt = _build_ai_prompt(stock)
        analysis = _call_claude(prompt)
        if not analysis:
            return v1_error_response(message="AI分析失败，请稍后重试")

        # 3. 写入DB
        save_ai_analysis(date, code, analysis)

        return v1_success_response(data={"analysis": analysis, "cached": False})

    except Exception as e:
        logger.error(f"AI分析失败: {e}", exc_info=True)
        return v1_error_response(message=f"AI分析失败: {str(e)}")
```

- [ ] **Step 2: 提交**

```bash
git add backend/routes/dragon_tiger.py
git commit -m "feat: add dragon tiger route with akshare fetch and AI analysis"
```

---

## Task 4: 注册 Blueprint

**Files:**
- Modify: `backend/routes/__init__.py`
- Modify: `backend/app.py`

- [ ] **Step 1: 修改 `backend/routes/__init__.py`**

在文件末尾添加：

```python
# 在现有 imports 末尾追加
from .dragon_tiger import dragon_tiger_bp

# 在 __all__ 列表追加
# 'dragon_tiger_bp',
```

完整修改后文件：
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
from .dragon_tiger import dragon_tiger_bp

__all__ = [
    'stock_basic_bp',
    'stock_timeshare_bp',
    'stock_tick_bp',
    'stock_other_bp',
    'l2_dashboard_bp',
    'emotion_cycle_bp',
    'limit_up_echelon_bp',
    'theme_manage_bp',
    'dragon_tiger_bp',
]
```

- [ ] **Step 2: 修改 `backend/app.py`** — 在 `register_blueprints` 中添加

找到 `register_blueprints` 函数，在 `from routes import (...)` 的 import 里添加 `dragon_tiger_bp`，并在函数体里添加注册行：

```python
# 在 from routes import (...) 中添加：
from routes import (
    stock_basic_bp,
    stock_timeshare_bp,
    stock_tick_bp,
    stock_other_bp,
    l2_dashboard_bp,
    emotion_cycle_bp,
    limit_up_echelon_bp,
    theme_manage_bp,
    dragon_tiger_bp,        # 新增
)

# 在 register_blueprints 函数体中添加：
def register_blueprints(app):
    app.register_blueprint(stock_basic_bp)
    app.register_blueprint(stock_timeshare_bp)
    app.register_blueprint(stock_tick_bp)
    app.register_blueprint(stock_other_bp)
    app.register_blueprint(l2_dashboard_bp)
    app.register_blueprint(emotion_cycle_bp)
    app.register_blueprint(limit_up_echelon_bp)
    app.register_blueprint(theme_manage_bp)
    app.register_blueprint(dragon_tiger_bp)    # 新增
```

- [ ] **Step 3: 验证后端启动**

```bash
cd backend && source venv/bin/activate && python3 app.py &
sleep 3
curl -s "http://localhost:9001/api/v1/dragon-tiger?date=20260515" | python3 -m json.tool | head -30
```

Expected: JSON 响应，`success: true`，`data.stocks` 是数组。

- [ ] **Step 4: 提交**

```bash
git add backend/routes/__init__.py backend/app.py
git commit -m "feat: register dragon tiger blueprint"
```

---

## Task 5: 前端样式文件

**Files:**
- Create: `frontend/src/pages/DragonTiger/index.css`

- [ ] **Step 1: 写 CSS**

```css
/* frontend/src/pages/DragonTiger/index.css */

.dt-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 64px);
  background: #141213;
  color: #fff;
  overflow: hidden;
}

/* 顶部日期导航栏 */
.dt-top-bar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 10px 20px;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.dt-date-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dt-date-btn {
  background: #1f1f1f;
  border: 1px solid #333;
  color: #ccc;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s;
}

.dt-date-btn:hover:not(:disabled) {
  background: #2a2a2a;
  color: #fff;
}

.dt-date-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.dt-date-label {
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  min-width: 90px;
  text-align: center;
}

/* 主体两栏 */
.dt-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 左侧股票列表 */
.dt-stock-list {
  width: 270px;
  flex-shrink: 0;
  border-right: 1px solid #2a2a2a;
  overflow-y: auto;
  background: #1a1a1a;
}

.dt-stock-list::-webkit-scrollbar {
  width: 4px;
}

.dt-stock-list::-webkit-scrollbar-thumb {
  background: #444;
  border-radius: 2px;
}

.dt-stock-item {
  padding: 12px 14px;
  border-bottom: 1px solid #222;
  cursor: pointer;
  transition: background 0.15s;
}

.dt-stock-item:hover {
  background: #222;
}

.dt-stock-item.selected {
  background: #1a2840;
  border-left: 3px solid #1890ff;
}

.dt-stock-item-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
}

.dt-stock-name {
  font-size: 14px;
  font-weight: 600;
  color: #fff;
}

.dt-stock-code {
  font-size: 11px;
  color: #666;
}

.dt-stock-pct {
  font-size: 13px;
  font-weight: 500;
}

.dt-stock-pct.up { color: #ff4d4f; }
.dt-stock-pct.down { color: #52c41a; }
.dt-stock-pct.flat { color: #888; }

.dt-stock-net {
  font-size: 12px;
  color: #faad14;
  margin-bottom: 4px;
}

.dt-stock-reason {
  font-size: 11px;
  color: #666;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 右侧详情 */
.dt-detail {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.dt-detail::-webkit-scrollbar {
  width: 4px;
}

.dt-detail::-webkit-scrollbar-thumb {
  background: #444;
  border-radius: 2px;
}

.dt-detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #555;
  font-size: 14px;
}

/* 详情头部 */
.dt-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.dt-detail-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.dt-detail-name {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
}

.dt-detail-code {
  font-size: 14px;
  color: #888;
}

.dt-detail-meta {
  font-size: 13px;
  color: #aaa;
}

.dt-detail-net {
  font-size: 14px;
  font-weight: 600;
  color: #faad14;
}

.dt-detail-net.positive { color: #ff4d4f; }
.dt-detail-net.negative { color: #52c41a; }

/* AI分析按钮 */
.dt-ai-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  color: #fff;
  padding: 6px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: opacity 0.2s;
  white-space: nowrap;
}

.dt-ai-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.dt-ai-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 席位两栏 */
.dt-seats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.dt-seats-panel {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  overflow: hidden;
}

.dt-seats-title {
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  border-bottom: 1px solid #2a2a2a;
}

.dt-seats-title.buy { color: #ff4d4f; }
.dt-seats-title.sell { color: #52c41a; }

.dt-seat-row {
  display: grid;
  grid-template-columns: 1fr 90px 90px 90px;
  padding: 8px 14px;
  border-bottom: 1px solid #1f1f1f;
  font-size: 12px;
  align-items: center;
}

.dt-seat-row:last-child {
  border-bottom: none;
}

.dt-seat-name {
  color: #ccc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dt-seat-name.hot-money {
  color: #ff69b4;
  font-weight: 600;
}

.dt-seat-col {
  text-align: right;
  color: #888;
}

.dt-seat-col.buy-col { color: #ff6666; }
.dt-seat-col.sell-col { color: #66cc66; }
.dt-seat-col.net-pos { color: #ff4d4f; font-weight: 600; }
.dt-seat-col.net-neg { color: #52c41a; font-weight: 600; }

.dt-seat-header {
  display: grid;
  grid-template-columns: 1fr 90px 90px 90px;
  padding: 6px 14px;
  font-size: 11px;
  color: #555;
  border-bottom: 1px solid #2a2a2a;
  background: #111;
}

.dt-seat-header-col {
  text-align: right;
}

.dt-seat-header-col:first-child {
  text-align: left;
}

/* AI分析结果 */
.dt-ai-result {
  background: #1a1a2e;
  border: 1px solid #2a2a5a;
  border-radius: 6px;
  padding: 16px;
  margin-top: 8px;
}

.dt-ai-result-title {
  font-size: 13px;
  color: #7b9cff;
  font-weight: 600;
  margin-bottom: 10px;
}

.dt-ai-result-text {
  font-size: 13px;
  color: #ccc;
  line-height: 1.8;
  white-space: pre-wrap;
}

/* 空状态 */
.dt-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}

/* 上榜原因 badge */
.dt-reason-badge {
  display: inline-block;
  background: #1f1f2e;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  color: #aaa;
  margin-right: 6px;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/pages/DragonTiger/index.css
git commit -m "feat: add dragon tiger page CSS"
```

---

## Task 6: 前端主页面组件

**Files:**
- Create: `frontend/src/pages/DragonTiger/index.js`

- [ ] **Step 1: 写主组件**

```jsx
// frontend/src/pages/DragonTiger/index.js
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Spin } from 'antd';
import { LeftOutlined, RightOutlined, RobotOutlined, LoadingOutlined } from '@ant-design/icons';
import { apiRequest } from '../../config/api';
import './index.css';

// 获取最近交易日（周末退到周五）
const getLastTradingDayStr = () => {
  const d = new Date();
  const dow = d.getDay();
  if (dow === 6) d.setDate(d.getDate() - 1);
  if (dow === 0) d.setDate(d.getDate() - 2);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
};

const offsetDate = (dateStr, delta) => {
  const d = new Date(
    parseInt(dateStr.slice(0, 4)),
    parseInt(dateStr.slice(4, 6)) - 1,
    parseInt(dateStr.slice(6, 8))
  );
  let count = 0;
  const step = delta > 0 ? 1 : -1;
  while (count !== delta) {
    d.setDate(d.getDate() + step);
    const dow = d.getDay();
    if (dow !== 0 && dow !== 6) count += step;
  }
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
};

const formatDateDisplay = (s) =>
  s && s.length === 8 ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s;

const fmtAmount = (val) => {
  const v = parseFloat(val || 0);
  if (isNaN(v)) return '--';
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(0)}万`;
  return `${v.toFixed(0)}`;
};

const HOT_MONEY_KW = ['知春路', '成都', '宁波', '佛山', '拉萨', '乐清千帆', '温州', '绍兴', '华鑫', '财通', '游资'];
const isHotMoney = (name) => HOT_MONEY_KW.some((kw) => name && name.includes(kw));

function SeatTable({ seats, direction }) {
  if (!seats || seats.length === 0) {
    return <div style={{ padding: '20px 14px', color: '#555', fontSize: 12 }}>暂无数据</div>;
  }
  return (
    <>
      <div className="dt-seat-header">
        <span>席位名称</span>
        <span className="dt-seat-header-col">买入额</span>
        <span className="dt-seat-header-col">卖出额</span>
        <span className="dt-seat-header-col">净额</span>
      </div>
      {seats.map((seat, i) => {
        const hot = seat.is_hot_money || isHotMoney(seat.seat_name || '');
        const net = parseFloat(seat.net_amount || 0);
        return (
          <div key={i} className="dt-seat-row">
            <span className={`dt-seat-name ${hot ? 'hot-money' : ''}`} title={seat.seat_name}>
              {seat.seat_name || '--'}
            </span>
            <span className="dt-seat-col buy-col">{fmtAmount(seat.buy_amount)}</span>
            <span className="dt-seat-col sell-col">{fmtAmount(seat.sell_amount)}</span>
            <span className={`dt-seat-col ${net > 0 ? 'net-pos' : net < 0 ? 'net-neg' : ''}`}>
              {fmtAmount(seat.net_amount)}
            </span>
          </div>
        );
      })}
    </>
  );
}

function DragonTiger() {
  const todayStr = getLastTradingDayStr();
  const [currentDate, setCurrentDate] = useState(todayStr);
  const [loading, setLoading] = useState(false);
  const [stocks, setStocks] = useState([]);
  const [selectedCode, setSelectedCode] = useState(null);
  const [aiResults, setAiResults] = useState({}); // code -> analysis
  const [aiLoading, setAiLoading] = useState(new Set());
  const dataCache = useRef({}); // date -> stocks[]

  const fetchData = useCallback(async (date) => {
    if (dataCache.current[date]) {
      setStocks(dataCache.current[date]);
      if (dataCache.current[date].length > 0 && !selectedCode) {
        setSelectedCode(dataCache.current[date][0].code);
      }
      return;
    }
    setLoading(true);
    setStocks([]);
    setSelectedCode(null);
    try {
      const res = await apiRequest(`/api/v1/dragon-tiger?date=${date}`);
      if (res?.data?.stocks) {
        dataCache.current[date] = res.data.stocks;
        setStocks(res.data.stocks);
        if (res.data.stocks.length > 0) {
          setSelectedCode(res.data.stocks[0].code);
        }
      }
    } catch (e) {
      console.error('龙虎榜加载失败:', e);
    } finally {
      setLoading(false);
    }
  }, [selectedCode]);

  useEffect(() => {
    fetchData(currentDate);
  }, [currentDate]); // eslint-disable-line

  const handleDateChange = (delta) => {
    const next = delta > 0 ? offsetDate(currentDate, 1) : offsetDate(currentDate, -1);
    setCurrentDate(next);
    setAiResults({});
  };

  const handleAiAnalysis = async (stock) => {
    const code = stock.code;
    if (aiResults[code] || aiLoading.has(code)) return;
    setAiLoading((prev) => new Set([...prev, code]));
    try {
      const res = await apiRequest('/api/v1/dragon-tiger/ai-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: currentDate, code }),
      });
      if (res?.data?.analysis) {
        setAiResults((prev) => ({ ...prev, [code]: res.data.analysis }));
      }
    } catch (e) {
      console.error('AI分析失败:', e);
    } finally {
      setAiLoading((prev) => {
        const next = new Set(prev);
        next.delete(code);
        return next;
      });
    }
  };

  const selectedStock = stocks.find((s) => s.code === selectedCode) || null;

  return (
    <div className="dt-container">
      {/* 顶部日期导航 */}
      <div className="dt-top-bar">
        <div className="dt-date-nav">
          <button className="dt-date-btn" onClick={() => handleDateChange(-1)}>
            <LeftOutlined /> 前一天
          </button>
          <span className="dt-date-label">{formatDateDisplay(currentDate)}</span>
          <button
            className="dt-date-btn"
            disabled={currentDate >= todayStr}
            onClick={() => handleDateChange(1)}
          >
            后一天 <RightOutlined />
          </button>
        </div>
      </div>

      {/* 主体 */}
      <div className="dt-main">
        {/* 左侧列表 */}
        <div className="dt-stock-list">
          {loading ? (
            <div className="dt-loading">
              <Spin size="large" tip="加载中..." />
            </div>
          ) : stocks.length === 0 ? (
            <div style={{ padding: 20, color: '#555', fontSize: 13 }}>暂无龙虎榜数据</div>
          ) : (
            stocks.map((stock) => {
              const pct = parseFloat(stock.change_pct || 0);
              const pctClass = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat';
              const net = parseFloat(stock.net_buy || 0);
              return (
                <div
                  key={stock.code}
                  className={`dt-stock-item ${selectedCode === stock.code ? 'selected' : ''}`}
                  onClick={() => setSelectedCode(stock.code)}
                >
                  <div className="dt-stock-item-header">
                    <span className="dt-stock-name">{stock.name}</span>
                    <span className={`dt-stock-pct ${pctClass}`}>
                      {pct > 0 ? '+' : ''}{pct.toFixed(2)}%
                    </span>
                  </div>
                  <div className="dt-stock-code">{stock.code}</div>
                  <div className="dt-stock-net">
                    净额 {fmtAmount(stock.net_buy)}
                  </div>
                  <div className="dt-stock-reason" title={stock.reason}>
                    {stock.reason || '--'}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* 右侧详情 */}
        <div className="dt-detail">
          {!selectedStock ? (
            <div className="dt-detail-empty">← 点击左侧股票查看龙虎榜详情</div>
          ) : (
            <>
              {/* 头部 */}
              <div className="dt-detail-header">
                <div className="dt-detail-title">
                  <span className="dt-detail-name">{selectedStock.name}</span>
                  <span className="dt-detail-code">({selectedStock.code})</span>
                  <span className="dt-detail-meta">
                    上榜原因：<span className="dt-reason-badge" title={selectedStock.reason}>
                      {selectedStock.reason || '--'}
                    </span>
                  </span>
                  <span className={`dt-detail-net ${parseFloat(selectedStock.net_buy) > 0 ? 'positive' : 'negative'}`}>
                    净额：{fmtAmount(selectedStock.net_buy)}
                  </span>
                </div>
                <button
                  className="dt-ai-btn"
                  disabled={aiLoading.has(selectedStock.code)}
                  onClick={() => handleAiAnalysis(selectedStock)}
                >
                  {aiLoading.has(selectedStock.code)
                    ? <><LoadingOutlined style={{ marginRight: 4 }} />分析中...</>
                    : <><RobotOutlined style={{ marginRight: 4 }} />AI分析</>
                  }
                </button>
              </div>

              {/* 席位表格 */}
              <div className="dt-seats-row">
                <div className="dt-seats-panel">
                  <div className="dt-seats-title buy">买入席位</div>
                  <SeatTable seats={selectedStock.buy_seats} direction="buy" />
                </div>
                <div className="dt-seats-panel">
                  <div className="dt-seats-title sell">卖出席位</div>
                  <SeatTable seats={selectedStock.sell_seats} direction="sell" />
                </div>
              </div>

              {/* AI分析结果 */}
              {aiResults[selectedStock.code] && (
                <div className="dt-ai-result">
                  <div className="dt-ai-result-title">
                    <RobotOutlined style={{ marginRight: 6 }} />AI 资金意图解读
                  </div>
                  <div className="dt-ai-result-text">{aiResults[selectedStock.code]}</div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default DragonTiger;
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/pages/DragonTiger/index.js
git commit -m "feat: add dragon tiger frontend page component"
```

---

## Task 7: 前端路由和导航集成

**Files:**
- Modify: `frontend/src/App.js`

- [ ] **Step 1: 修改 App.js**

```jsx
// 在 import 区域添加：
import DragonTiger from './pages/DragonTiger';

// navItems 中添加（在 '情绪周期' 之前）：
const navItems = [
  { key: '/stock-dashboard', label: '个股分析' },
  { key: '/limit-up-echelon', label: '涨停梯队' },
  { key: '/dragon-tiger', label: '核心游资' },   // 新增
  { key: '/emotion-cycle', label: '情绪周期' },
];

// Routes 中添加：
<Route path="/dragon-tiger" element={<DragonTiger />} />
```

完整修改后的 navItems 和 Routes 区域：

```jsx
const navItems = [
  { key: '/stock-dashboard', label: '个股分析' },
  { key: '/limit-up-echelon', label: '涨停梯队' },
  { key: '/dragon-tiger', label: '核心游资' },
  { key: '/emotion-cycle', label: '情绪周期' },
];
```

```jsx
<Routes>
  <Route path="/" element={<Navigate to="/stock-dashboard" replace />} />
  <Route path="/home" element={<Home />} />
  <Route path="/stock-dashboard" element={<StockDashboard />} />
  <Route path="/limit-up-echelon" element={<LimitUpEchelon />} />
  <Route path="/dragon-tiger" element={<DragonTiger />} />
  <Route path="/emotion-cycle" element={<EmotionCycle />} />
  <Route path="*" element={<Navigate to="/stock-dashboard" replace />} />
</Routes>
```

- [ ] **Step 2: 启动前端验证**

```bash
cd frontend && npm start
```

打开 http://localhost:3000，确认：
1. 导航栏出现"核心游资"菜单项
2. 点击后进入 `/dragon-tiger` 页面
3. 页面右上角有日期导航按钮
4. 左侧股票列表有数据（或显示"暂无数据"）
5. 点击股票后右侧显示买入/卖出席位表格
6. 游资席位名称显示为粉色
7. 点击 AI分析 按钮后出现 loading，完成后显示分析结果

- [ ] **Step 3: 提交**

```bash
git add frontend/src/App.js
git commit -m "feat: add dragon tiger route and nav menu item"
```

---

## Self-Review

### Spec 覆盖检查

| 需求 | 任务 | 状态 |
|------|------|------|
| 调用同花顺/akshare龙虎榜接口 | Task 3 `_fetch_from_akshare` | ✅ |
| 新增核心游资模块（样式如图） | Task 5/6/7 | ✅ |
| 时间切换（前一天/后一天） | Task 6 日期导航 | ✅ |
| 当天有数据用DB，无则调接口 | Task 3 `get_dragon_tiger` 逻辑 | ✅ |
| 每股龙虎榜右侧 AI分析按钮 | Task 6 `dt-ai-btn` | ✅ |
| AI对龙虎榜资金意图解读 | Task 3 `_build_ai_prompt` + `ai_analysis` | ✅ |
| 数据统一入库避免重复分析 | Task 2 `save_ai_analysis` + UNIQUE KEY | ✅ |
| 游资席位高亮（粉色） | Task 5/6 `hot-money` class | ✅ |
| 3张DB表 | Task 1 | ✅ |

### 关键实现注意事项

1. **akshare 函数实际参数（已验证）：**
   - `ak.stock_lhb_detail_em(start_date="20260515", end_date="20260515")` — 返回列：代码, 名称, 涨跌幅, 收盘价, 龙虎榜净买额, 龙虎榜买入额, 龙虎榜卖出额, 龙虎榜成交额, 市场总成交额, 上榜原因, 解读
   - `ak.stock_lhb_stock_detail_em(symbol="002031", date="20260515", flag="买入")` — 返回列：序号, 交易营业部名称, 买入金额, 买入金额-占总成交比例, 卖出金额, 卖出金额-占总成交比例, 净额, 类型

2. **并发拉取席位**：每只股票需调用 2 次 akshare（买入+卖出），用 `ThreadPoolExecutor(max_workers=5)` 控制并发。

3. **金额单位**：akshare 返回的金额单位为**元**（float），DB 存 `DECIMAL(20,2)`，前端 `fmtAmount` 自动转换为亿/万显示。

4. **NaN处理**：`_fmt_amount` 中有 NaN 检测 (`v != v`)，避免写入 DB 异常。
