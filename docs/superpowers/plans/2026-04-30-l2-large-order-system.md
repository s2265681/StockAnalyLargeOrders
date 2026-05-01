# L2大单系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于东方财富免费API实现实时L2大单监控系统，预留L2付费升级通道。

**Architecture:** 后端新增 services/ 层封装东方财富数据获取，通过 data_source_adapter 统一适配免费/L2接口，暴露 `/api/v1/l2_dashboard` 统一API。前端复用现有组件，改用新API获取数据，增加轮询机制。

**Tech Stack:** Flask, requests, React 18, Jotai, ECharts, Ant Design

---

## 文件结构

### 新增文件
| 文件 | 职责 |
|------|------|
| `backend/services/__init__.py` | services 包初始化 |
| `backend/services/eastmoney_free.py` | 东方财富免费API数据获取 |
| `backend/services/eastmoney_l2.py` | L2付费接口预留空壳 |
| `backend/services/data_source_adapter.py` | 数据源适配器，大单识别、分级统计 |
| `backend/routes/l2_dashboard.py` | `/api/v1/l2_dashboard` 路由 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `backend/routes/__init__.py` | 注册 l2_dashboard_bp |
| `backend/app.py` | 导入并注册 l2_dashboard_bp |
| `frontend/src/store/atoms.js` | 新增 fetchL2DashboardAtom |
| `frontend/src/pages/StockDashboard/index.js` | 改用新atom + 轮询 |
| `frontend/src/pages/StockDashboard/components/StockOrderDetails.js` | 适配新数据格式 |
| `frontend/src/pages/StockDashboard/components/StockChart.js` | 适配新数据格式中的统计金额 |

---

## Task 1: 东方财富免费数据获取服务

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/eastmoney_free.py`

- [ ] **Step 1: 创建 services 包**

```bash
mkdir -p /Users/mac/Github/NiuNIuNiu/backend/services
```

创建 `backend/services/__init__.py`:
```python
```
（空文件，仅作为包标识）

- [ ] **Step 2: 实现 EastMoneyFreeSource**

创建 `backend/services/eastmoney_free.py`:

```python
"""
东方财富免费API数据获取服务
提供实时行情、逐笔成交明细、分时走势数据
"""
import requests
import logging
import time

logger = logging.getLogger(__name__)

class EastMoneyFreeSource:
    """东方财富免费数据源"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/'
        })

    def _get_market_code(self, code):
        """将股票代码转换为东方财富市场代码格式

        Args:
            code: 6位股票代码，如 '000001'
        Returns:
            东方财富格式代码，如 '0.000001' (深圳) 或 '1.600000' (上海)
        """
        if code.startswith(('0', '3')):
            return f'0.{code}'  # 深圳
        elif code.startswith('6'):
            return f'1.{code}'  # 上海
        else:
            return f'0.{code}'

    def get_realtime_quote(self, code):
        """获取实时行情（含买一/卖一价，用于推算方向）

        Args:
            code: 股票代码
        Returns:
            dict: {
                'name': 股票名称,
                'price': 当前价,
                'yesterday_close': 昨收,
                'open': 今开,
                'high': 最高,
                'low': 最低,
                'volume': 成交量(股),
                'turnover': 成交额(元),
                'bid1_price': 买一价,
                'ask1_price': 卖一价,
                'change_percent': 涨跌幅
            }
        """
        market_code = self._get_market_code(code)
        url = 'https://push2.eastmoney.com/api/qt/stock/get'
        params = {
            'secid': market_code,
            'fields': 'f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f169,f170',
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'fltt': 2
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富行情接口返回异常: {data}")
                return None

            d = data['data']
            return {
                'code': code,
                'name': d.get('f58', ''),
                'price': d.get('f43', 0) / 100 if isinstance(d.get('f43'), int) else d.get('f43', 0),
                'yesterday_close': d.get('f60', 0) / 100 if isinstance(d.get('f60'), int) else d.get('f60', 0),
                'open': d.get('f46', 0) / 100 if isinstance(d.get('f46'), int) else d.get('f46', 0),
                'high': d.get('f44', 0) / 100 if isinstance(d.get('f44'), int) else d.get('f44', 0),
                'low': d.get('f45', 0) / 100 if isinstance(d.get('f45'), int) else d.get('f45', 0),
                'volume': d.get('f47', 0),
                'turnover': d.get('f48', 0),
                'bid1_price': d.get('f51', 0) / 100 if isinstance(d.get('f51'), int) else d.get('f51', 0),
                'ask1_price': d.get('f52', 0) / 100 if isinstance(d.get('f52'), int) else d.get('f52', 0),
                'change_percent': d.get('f170', 0) / 100 if isinstance(d.get('f170'), int) else d.get('f170', 0),
            }
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}")
            return None

    def get_tick_details(self, code, pos=-1):
        """获取逐笔成交明细

        东方财富的成交明细接口返回最新的成交记录，每条包含时间、价格、成交量。
        通过 pos 参数可以增量获取新数据。

        Args:
            code: 股票代码
            pos: 位置参数，-1 表示获取最新数据
        Returns:
            dict: {
                'details': [
                    {
                        'time': '09:30:02',
                        'price': 4.46,
                        'volume': 100,  # 手
                        'amount': 44600.0,  # 元
                        'type': 1/2/4  # 1=买盘 2=卖盘 4=中性
                    }, ...
                ],
                'pos': int  # 下次请求用的位置参数
            }
        """
        market_code = self._get_market_code(code)
        url = 'https://push2.eastmoney.com/api/qt/stock/details/get'
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4',
            'fields2': 'f51,f52,f53,f54,f55',
            'pos': pos,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'fltt': 2
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富成交明细接口返回异常: {data}")
                return {'details': [], 'pos': pos}

            details_raw = data['data'].get('details', [])
            new_pos = data['data'].get('pos', pos)
            details = []

            for item in details_raw:
                # 格式: "时间,价格,成交量(手),类型,额外"
                parts = item.split(',')
                if len(parts) < 4:
                    continue

                time_str = parts[0]
                price = float(parts[1])
                volume = int(parts[2])  # 手
                buy_sell_type = int(parts[3])  # 1=买 2=卖 4=中性

                details.append({
                    'time': time_str,
                    'price': price,
                    'volume': volume,
                    'amount': round(price * volume * 100, 2),  # 手转股再算金额
                    'type': buy_sell_type
                })

            return {'details': details, 'pos': new_pos}
        except Exception as e:
            logger.error(f"获取成交明细失败: {e}")
            return {'details': [], 'pos': pos}

    def get_timeshare(self, code):
        """获取当日分时走势数据

        Args:
            code: 股票代码
        Returns:
            list: [
                {
                    'time': '09:30',
                    'price': 4.46,
                    'avg_price': 4.45,
                    'volume': 12000  # 手
                }, ...
            ]
        """
        market_code = self._get_market_code(code)
        url = 'https://push2his.eastmoney.com/api/qt/stock/trends2/get'
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
            'iscr': 0,
            'ndays': 1,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get('rc') != 0 or not data.get('data'):
                logger.warning(f"东方财富分时接口返回异常: {data}")
                return []

            trends_raw = data['data'].get('trends', [])
            yesterday_close = data['data'].get('preClose', 0)
            result = []

            for item in trends_raw:
                # 格式: "2026-04-30 09:30,价格,成交量,现额,...,均价"
                parts = item.split(',')
                if len(parts) < 7:
                    continue

                time_full = parts[0]
                time_str = time_full.split(' ')[1] if ' ' in time_full else time_full

                result.append({
                    'time': time_str,
                    'price': float(parts[1]),
                    'volume': int(parts[2]),
                    'avg_price': float(parts[6]) if parts[6] else float(parts[1]),
                })

            return result
        except Exception as e:
            logger.error(f"获取分时数据失败: {e}")
            return []

    def infer_direction(self, buy_sell_type):
        """将东方财富的成交类型转换为买卖方向

        东方财富免费成交明细中 type 字段:
        1 = 买盘(成交在卖方价格，主动买入)
        2 = 卖盘(成交在买方价格，主动卖出)
        4 = 中性盘

        Args:
            buy_sell_type: 1/2/4
        Returns:
            str: '被买'/'被卖'/'中性'
        """
        if buy_sell_type == 1:
            return '被买'
        elif buy_sell_type == 2:
            return '被卖'
        else:
            return '中性'
```

- [ ] **Step 3: 手动验证接口可用性**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
source venv/bin/activate
python -c "
from services.eastmoney_free import EastMoneyFreeSource
src = EastMoneyFreeSource()

# 测试实时行情
quote = src.get_realtime_quote('000001')
print('=== 实时行情 ===')
print(quote)

# 测试成交明细（取最新几条）
tick = src.get_tick_details('000001')
print('=== 成交明细(前3条) ===')
print(tick['details'][:3])

# 测试分时走势
ts = src.get_timeshare('000001')
print('=== 分时数据(前3条) ===')
print(ts[:3])
"
```

预期：打印出平安银行的实时行情、最近几条成交记录、分时走势数据。如果非交易时间可能返回收盘数据。

- [ ] **Step 4: 提交**

```bash
git add backend/services/__init__.py backend/services/eastmoney_free.py
git commit -m "feat: 添加东方财富免费API数据获取服务"
```

---

## Task 2: L2预留接口 + 数据源适配器

**Files:**
- Create: `backend/services/eastmoney_l2.py`
- Create: `backend/services/data_source_adapter.py`

- [ ] **Step 1: 创建L2预留空壳**

创建 `backend/services/eastmoney_l2.py`:

```python
"""
东方财富L2付费数据源（预留）
开通L2后实现具体逻辑，替换免费数据源
"""
import logging

logger = logging.getLogger(__name__)


class EastMoneyL2Source:
    """东方财富L2付费数据源

    与 EastMoneyFreeSource 相同的方法签名。
    开通L2（约30元/月）后实现以下方法即可切换。
    """

    def get_realtime_quote(self, code):
        raise NotImplementedError("L2数据源尚未实现，请先开通东方财富Level-2服务")

    def get_tick_details(self, code, pos=-1):
        raise NotImplementedError("L2数据源尚未实现，请先开通东方财富Level-2服务")

    def get_timeshare(self, code):
        raise NotImplementedError("L2数据源尚未实现，请先开通东方财富Level-2服务")

    def infer_direction(self, buy_sell_type):
        raise NotImplementedError("L2数据源尚未实现，请先开通东方财富Level-2服务")
```

- [ ] **Step 2: 实现数据源适配器**

创建 `backend/services/data_source_adapter.py`:

```python
"""
数据源适配器
负责调用数据源获取原始数据，进行大单识别、分级统计，返回统一格式
"""
import logging
import time
from datetime import datetime

from .eastmoney_free import EastMoneyFreeSource
from .eastmoney_l2 import EastMoneyL2Source

logger = logging.getLogger(__name__)

# 大单分级阈值（单位：元）
LEVEL_THRESHOLDS = {
    'above_300': 3_000_000,
    'above_100': 1_000_000,
    'above_50':  500_000,
    'above_30':  300_000,
}

# 简单内存缓存
_cache = {}
CACHE_TTL = 5  # 秒


class DataSourceAdapter:
    """数据源适配器，统一免费/L2数据源，输出标准格式"""

    def __init__(self, use_l2=False):
        """
        Args:
            use_l2: 是否使用L2付费数据源，默认False使用免费源
        """
        if use_l2:
            self.source = EastMoneyL2Source()
            self.source_name = 'eastmoney_l2'
        else:
            self.source = EastMoneyFreeSource()
            self.source_name = 'eastmoney_free'

    def get_l2_dashboard(self, code):
        """获取L2大单看板全量数据

        一次调用返回前端所需的全部数据：股票信息、分时走势、大单统计、大单明细、big_map。
        结果缓存5秒。

        Args:
            code: 股票代码
        Returns:
            dict: 统一格式的L2看板数据
        """
        cache_key = f'l2_dashboard_{code}'
        now = time.time()

        if cache_key in _cache:
            cached_time, cached_data = _cache[cache_key]
            if now - cached_time < CACHE_TTL:
                return cached_data

        result = self._build_dashboard(code)
        _cache[cache_key] = (now, result)
        return result

    def _build_dashboard(self, code):
        """构建完整的看板数据"""
        # 1. 获取实时行情
        quote = self.source.get_realtime_quote(code)
        if not quote:
            return {'success': False, 'message': '获取行情数据失败'}

        # 2. 获取逐笔成交明细
        tick_result = self.source.get_tick_details(code)
        all_details = tick_result.get('details', [])

        # 3. 获取分时走势
        timeshare = self.source.get_timeshare(code)

        # 4. 标注买卖方向
        for detail in all_details:
            detail['direction'] = self.source.infer_direction(detail['type'])

        # 5. 识别大单并分级
        large_orders = self._identify_large_orders(all_details)
        statistics = self._calculate_statistics(all_details)
        big_map = self._build_big_map(large_orders)

        return {
            'success': True,
            'data': {
                'stock_info': {
                    'code': quote['code'],
                    'name': quote['name'],
                    'price': quote['price'],
                    'yesterday_close': quote['yesterday_close'],
                    'open': quote['open'],
                    'high': quote['high'],
                    'low': quote['low'],
                    'volume': quote['volume'],
                    'turnover': quote['turnover'],
                    'change_percent': quote['change_percent'],
                },
                'timeshare': timeshare,
                'statistics': statistics,
                'large_orders': large_orders,
                'big_map': big_map,
                'data_source': self.source_name,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        }

    def _identify_large_orders(self, details):
        """从逐笔明细中识别大单（成交额>=30万）

        Args:
            details: 逐笔成交列表
        Returns:
            list: 大单列表，按金额降序排列
        """
        large = []
        for d in details:
            if d['amount'] >= LEVEL_THRESHOLDS['above_30']:
                large.append({
                    'time': d['time'],
                    'direction': d['direction'],
                    'price': d['price'],
                    'volume_lots': d['volume'],  # 手
                    'amount': round(d['amount'] / 10000, 2),  # 万元
                })
        large.sort(key=lambda x: x['amount'], reverse=True)
        return large

    def _calculate_statistics(self, details):
        """按分级统计大单买卖笔数和金额

        Returns:
            dict: {
                'above_300': {'buy_count': N, 'sell_count': N, 'buy_amount': N, 'sell_amount': N},
                ...
                'below_30': {...}
            }
        """
        stats = {}
        for level_key in list(LEVEL_THRESHOLDS.keys()) + ['below_30']:
            stats[level_key] = {
                'buy_count': 0, 'sell_count': 0,
                'buy_amount': 0.0, 'sell_amount': 0.0,
            }

        for d in details:
            amount = d['amount']
            is_buy = d['direction'] in ('被买', '主买')
            amount_wan = amount / 10000

            # 确定归属级别（取最高匹配级别）
            if amount >= LEVEL_THRESHOLDS['above_300']:
                level_key = 'above_300'
            elif amount >= LEVEL_THRESHOLDS['above_100']:
                level_key = 'above_100'
            elif amount >= LEVEL_THRESHOLDS['above_50']:
                level_key = 'above_50'
            elif amount >= LEVEL_THRESHOLDS['above_30']:
                level_key = 'above_30'
            else:
                level_key = 'below_30'

            if is_buy:
                stats[level_key]['buy_count'] += 1
                stats[level_key]['buy_amount'] = round(stats[level_key]['buy_amount'] + amount_wan, 2)
            else:
                stats[level_key]['sell_count'] += 1
                stats[level_key]['sell_amount'] = round(stats[level_key]['sell_amount'] + amount_wan, 2)

        return stats

    def _build_big_map(self, large_orders):
        """构建分时图大单标注数据（按分钟分组）

        Args:
            large_orders: 大单列表
        Returns:
            dict: { '09:35': [{'type': '被买', 'volume': 414, 'amount': 185.5}], ... }
        """
        big_map = {}
        for order in large_orders:
            time_str = order['time']
            # 截取到分钟 HH:MM
            if len(time_str) >= 5:
                minute_key = time_str[:5]
            else:
                minute_key = time_str

            if minute_key not in big_map:
                big_map[minute_key] = []

            big_map[minute_key].append({
                'type': order['direction'],
                'volume': order['volume_lots'],
                'amount': order['amount'],
            })

        return big_map
```

- [ ] **Step 3: 手动验证适配器**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
source venv/bin/activate
python -c "
from services.data_source_adapter import DataSourceAdapter
adapter = DataSourceAdapter(use_l2=False)
result = adapter.get_l2_dashboard('000001')
print('success:', result.get('success'))
if result.get('data'):
    d = result['data']
    print('stock:', d['stock_info']['name'], d['stock_info']['price'])
    print('timeshare count:', len(d['timeshare']))
    print('large_orders count:', len(d['large_orders']))
    print('statistics:', d['statistics'])
    print('big_map keys:', list(d['big_map'].keys())[:5])
    print('data_source:', d['data_source'])
"
```

预期：打印出平安银行的完整看板数据，包含分时、大单统计、大单列表。

- [ ] **Step 4: 提交**

```bash
git add backend/services/eastmoney_l2.py backend/services/data_source_adapter.py
git commit -m "feat: 添加数据源适配器和L2预留接口"
```

---

## Task 3: L2 Dashboard API 路由

**Files:**
- Create: `backend/routes/l2_dashboard.py`
- Modify: `backend/routes/__init__.py`
- Modify: `backend/app.py`

- [ ] **Step 1: 创建路由文件**

创建 `backend/routes/l2_dashboard.py`:

```python
"""
L2大单看板统一API路由
提供一站式的L2大单数据接口
"""
import logging
from flask import Blueprint, request, jsonify

from services.data_source_adapter import DataSourceAdapter

logger = logging.getLogger(__name__)

l2_dashboard_bp = Blueprint('l2_dashboard', __name__)

# 创建适配器实例（默认使用免费数据源）
adapter = DataSourceAdapter(use_l2=False)


@l2_dashboard_bp.route('/api/v1/l2_dashboard')
def l2_dashboard():
    """L2大单看板统一接口

    一次返回前端所需的全部数据：股票信息、分时走势、大单统计、大单明细、big_map。

    Query Params:
        code: 股票代码，默认 '000001'

    Returns:
        JSON: 统一格式的L2看板数据
    """
    code = request.args.get('code', '000001')

    # 基本校验
    if not code.isdigit() or len(code) != 6:
        return jsonify({'success': False, 'message': f'无效的股票代码: {code}'}), 400

    try:
        result = adapter.get_l2_dashboard(code)
        return jsonify(result)
    except Exception as e:
        logger.error(f"L2看板接口异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务异常: {str(e)}'}), 500
```

- [ ] **Step 2: 注册蓝图到 routes/__init__.py**

在 `backend/routes/__init__.py` 中添加导入和导出：

将:
```python
from .l2_data import l2_data_bp

__all__ = [
    'stock_basic_bp',
    'stock_timeshare_bp',
    'stock_tick_bp',
    'stock_realtime_bp',
    'stock_other_bp',
    'l2_data_bp'
]
```

改为:
```python
from .l2_data import l2_data_bp
from .l2_dashboard import l2_dashboard_bp

__all__ = [
    'stock_basic_bp',
    'stock_timeshare_bp',
    'stock_tick_bp',
    'stock_realtime_bp',
    'stock_other_bp',
    'l2_data_bp',
    'l2_dashboard_bp'
]
```

- [ ] **Step 3: 在 app.py 中注册蓝图**

在 `backend/app.py` 的导入区域，将:
```python
from routes import (
    stock_basic_bp,
    stock_timeshare_bp,
    stock_tick_bp,
    stock_realtime_bp,
    stock_other_bp,
    l2_data_bp
)
```

改为:
```python
from routes import (
    stock_basic_bp,
    stock_timeshare_bp,
    stock_tick_bp,
    stock_realtime_bp,
    stock_other_bp,
    l2_data_bp,
    l2_dashboard_bp
)
```

在 `register_blueprints` 函数中，在 `app.register_blueprint(l2_data_bp)` 行后添加:
```python
    app.register_blueprint(l2_dashboard_bp)    # L2大单看板统一接口
```

- [ ] **Step 4: 验证API可用**

重启后端服务，然后测试：

```bash
curl "http://localhost:9001/api/v1/l2_dashboard?code=000001" | python -m json.tool | head -40
```

预期：返回 `{"success": true, "data": {...}}` 格式的 JSON，包含 stock_info、timeshare、statistics、large_orders、big_map 字段。

- [ ] **Step 5: 提交**

```bash
git add backend/routes/l2_dashboard.py backend/routes/__init__.py backend/app.py
git commit -m "feat: 添加L2大单看板统一API路由"
```

---

## Task 4: 前端 atoms 改造

**Files:**
- Modify: `frontend/src/store/atoms.js`

- [ ] **Step 1: 在 atoms.js 末尾添加 fetchL2DashboardAtom**

在 `frontend/src/store/atoms.js` 的 `environmentInfoAtom` 定义之前（约第307行），添加:

```javascript
// L2大单看板统一数据获取
export const fetchL2DashboardAtom = atom(
  null,
  async (get, set, code) => {
    set(loadingAtom, true);
    set(errorAtom, null);

    try {
      const data = await apiRequest(`/api/v1/l2_dashboard?code=${code}`, { timeout: 15000 });

      if (data.success === true && data.data) {
        const d = data.data;

        // 填充分时数据（兼容 StockChart 现有格式）
        set(timeshareDataAtom, {
          fenshi: (d.timeshare || []).map(t => t.price),
          volume: (d.timeshare || []).map(t => t.volume),
          zhuli: [],
          sanhu: [],
          big_map: d.big_map || {},
          base_info: {
            prevClosePrice: d.stock_info.yesterday_close,
            highPrice: d.stock_info.high,
            lowPrice: d.stock_info.low,
          },
        });

        // 填充大单数据（兼容 StockOrderDetails 现有格式）
        const orders = (d.large_orders || []).map(order => ({
          time: order.time,
          type: (order.direction === '被买' || order.direction === '主买') ? 'buy' : 'sell',
          price: order.price,
          volume: order.volume_lots,
          amount: order.amount * 10000, // 万元转元，兼容现有组件
          category: determineCategoryFromWan(order.amount),
          direction: order.direction,
        }));

        set(largeOrdersDataAtom, {
          summary: {
            buyCount: orders.filter(o => o.type === 'buy').length,
            sellCount: orders.filter(o => o.type === 'sell').length,
            totalAmount: orders.reduce((s, o) => s + o.amount, 0),
            netInflow: orders.filter(o => o.type === 'buy').reduce((s, o) => s + o.amount, 0) -
                       orders.filter(o => o.type === 'sell').reduce((s, o) => s + o.amount, 0),
          },
          largeOrders: orders,
          levelStats: {
            D300: d.statistics.above_300,
            D100: d.statistics.above_100,
            D50: d.statistics.above_50,
            D30: d.statistics.above_30,
            under_D30: d.statistics.below_30,
          },
        });

        // 填充股票基础数据
        set(stockBasicDataAtom, {
          code: d.stock_info.code,
          name: d.stock_info.name,
          current_price: d.stock_info.price,
          change_percent: d.stock_info.change_percent,
          high: d.stock_info.high,
          low: d.stock_info.low,
          open: d.stock_info.open,
          yesterday_close: d.stock_info.yesterday_close,
          volume: d.stock_info.volume,
          turnover: d.stock_info.turnover,
          data_source: d.data_source,
        });
      } else {
        set(errorAtom, data.message || '获取L2数据失败');
      }
    } catch (error) {
      set(errorAtom, `获取L2看板数据失败: ${error.message}`);
    } finally {
      set(loadingAtom, false);
    }
  }
);

// 帮助函数：根据万元金额确定类别
const determineCategoryFromWan = (amountWan) => {
  if (amountWan >= 300) return 'D300';
  if (amountWan >= 100) return 'D100';
  if (amountWan >= 50) return 'D50';
  if (amountWan >= 30) return 'D30';
  return 'under_D30';
};
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/store/atoms.js
git commit -m "feat: 添加L2看板统一数据获取atom"
```

---

## Task 5: StockDashboard 改用新API + 轮询

**Files:**
- Modify: `frontend/src/pages/StockDashboard/index.js`

- [ ] **Step 1: 改造 StockDashboard**

将 `frontend/src/pages/StockDashboard/index.js` 的完整内容替换为:

```javascript
import React, { useEffect, useRef, useCallback } from 'react';
import { useAtom } from 'jotai';
import { useSearchParams } from 'react-router-dom';
import StockBasicInfo from './components/StockBasicInfo';
import StockChart from './components/StockChart';
import StockOrderDetails from './components/StockOrderDetails';
import {
  stockCodeAtom,
  fetchL2DashboardAtom
} from '../../store/atoms';

const POLL_INTERVAL = 5000; // 5秒轮询

const isTradeTime = () => {
  const now = new Date();
  const hour = now.getHours();
  const minute = now.getMinutes();
  const day = now.getDay();

  // 周末不交易
  if (day === 0 || day === 6) return false;

  // 上午 9:30 - 11:30
  if ((hour === 9 && minute >= 30) || hour === 10 || (hour === 11 && minute <= 30)) return true;
  // 下午 13:00 - 15:00
  if (hour === 13 || hour === 14 || (hour === 15 && minute === 0)) return true;

  return false;
};

const StockDashboard = () => {
  const [searchParams] = useSearchParams();
  const [stockCode, setStockCode] = useAtom(stockCodeAtom);
  const [, fetchL2Dashboard] = useAtom(fetchL2DashboardAtom);
  const timerRef = useRef(null);

  const handleStockCodeChange = (newCode) => {
    setStockCode(newCode);
  };

  // 数据获取函数
  const fetchData = useCallback(() => {
    if (stockCode) {
      fetchL2Dashboard(stockCode);
    }
  }, [stockCode, fetchL2Dashboard]);

  // 初始加载 + 轮询
  useEffect(() => {
    // 立即加载一次
    fetchData();

    // 设置轮询
    timerRef.current = setInterval(() => {
      if (isTradeTime()) {
        fetchData();
      }
    }, POLL_INTERVAL);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [fetchData]);

  return (
    <div className='stock-dashboard-container' style={{ backgroundColor: '#141213', minHeight: '100vh' }}>
      <StockBasicInfo onStockCodeChange={handleStockCodeChange} />
      <StockChart />
      <StockOrderDetails />
    </div>
  );
};

export default StockDashboard;
```

- [ ] **Step 2: 验证前端编译**

```bash
cd /Users/mac/Github/NiuNIuNiu/frontend
npx react-scripts build 2>&1 | tail -5
```

预期：编译成功，无错误。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/StockDashboard/index.js
git commit -m "feat: StockDashboard改用L2看板API并增加交易时间轮询"
```

---

## Task 6: StockOrderDetails 适配新数据格式

**Files:**
- Modify: `frontend/src/pages/StockDashboard/components/StockOrderDetails.js`

- [ ] **Step 1: 更新 status 显示逻辑**

在 `StockOrderDetails.js` 的 `getFilteredTrades` 函数中（约第140-148行），将 status 判断逻辑:

```javascript
      if (trade.type === 'buy') {
        status = amountWan >= 100 ? '主买' : '被买';
      } else {
        status = '主卖';
      }
```

改为（使用后端返回的精确方向）:

```javascript
      // 优先使用后端返回的方向标识
      if (trade.direction) {
        status = trade.direction;
      } else if (trade.type === 'buy') {
        status = amountWan >= 100 ? '主买' : '被买';
      } else {
        status = amountWan >= 100 ? '主卖' : '被卖';
      }
```

- [ ] **Step 2: 更新 levelStats 使用后端统计数据**

在 `StockOrderDetails.js` 中，更新 `getAmountLevelStats` 函数（约第44-76行），在函数开头增加直接使用后端 levelStats 的逻辑:

将整个 `getAmountLevelStats` 函数:
```javascript
  const getAmountLevelStats = () => {
    if (!largeOrdersData || !largeOrdersData.largeOrders) return {};

    const orders = largeOrdersData.largeOrders;
    const stats = {
      300: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 },
      100: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 },
      50: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 },
      30: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 }
    };

    orders.forEach(order => {
      const amountWan = order.amount / 10000;
      let level;

      if (amountWan >= 300) level = 300;
      else if (amountWan >= 100) level = 100;
      else if (amountWan >= 50) level = 50;
      else if (amountWan >= 30) level = 30;
      else return;

      if (order.type === 'buy') {
        stats[level].buy += 1;
        stats[level].buyAmount += amountWan;
      } else {
        stats[level].sell += 1;
        stats[level].sellAmount += amountWan;
      }
      stats[level].totalAmount += amountWan;
    });

    return stats;
  };
```

替换为:
```javascript
  const getAmountLevelStats = () => {
    if (!largeOrdersData) return {};

    // 优先使用后端返回的 levelStats（含精确金额）
    if (largeOrdersData.levelStats) {
      const ls = largeOrdersData.levelStats;
      const mapLevel = (key) => {
        const s = ls[key] || {};
        return {
          buy: s.buy_count || 0,
          sell: s.sell_count || 0,
          buyAmount: s.buy_amount || 0,
          sellAmount: s.sell_amount || 0,
          totalAmount: (s.buy_amount || 0) + (s.sell_amount || 0),
        };
      };
      return {
        300: mapLevel('D300'),
        100: mapLevel('D100'),
        50: mapLevel('D50'),
        30: mapLevel('D30'),
      };
    }

    // 降级：从 largeOrders 列表计算
    if (!largeOrdersData.largeOrders) return {};
    const orders = largeOrdersData.largeOrders;
    const stats = {
      300: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 },
      100: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 },
      50: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 },
      30: { buy: 0, sell: 0, totalAmount: 0, buyAmount: 0, sellAmount: 0 }
    };

    orders.forEach(order => {
      const amountWan = order.amount / 10000;
      let level;
      if (amountWan >= 300) level = 300;
      else if (amountWan >= 100) level = 100;
      else if (amountWan >= 50) level = 50;
      else if (amountWan >= 30) level = 30;
      else return;

      if (order.type === 'buy') {
        stats[level].buy += 1;
        stats[level].buyAmount += amountWan;
      } else {
        stats[level].sell += 1;
        stats[level].sellAmount += amountWan;
      }
      stats[level].totalAmount += amountWan;
    });
    return stats;
  };
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/StockDashboard/components/StockOrderDetails.js
git commit -m "feat: StockOrderDetails适配L2看板API数据格式"
```

---

## Task 7: 端到端验证

**Files:** 无新文件

- [ ] **Step 1: 重启后端**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
# 停掉旧进程
pkill -f "python app.py" 2>/dev/null || true
# 启动
source venv/bin/activate && python app.py &
sleep 3
```

- [ ] **Step 2: 验证后端API**

```bash
# 测试L2看板接口
curl -s "http://localhost:9001/api/v1/l2_dashboard?code=000001" | python -m json.tool | head -50

# 测试无效代码
curl -s "http://localhost:9001/api/v1/l2_dashboard?code=abc" | python -m json.tool
```

预期：
- 第一个请求返回 `{"success": true, "data": {stock_info, timeshare, statistics, large_orders, big_map}}`
- 第二个请求返回 `{"success": false, "message": "无效的股票代码: abc"}`

- [ ] **Step 3: 验证前端页面**

启动前端（如果未启动）：
```bash
cd /Users/mac/Github/NiuNIuNiu/frontend && npm start &
```

打开浏览器访问 `http://localhost:9000/stock-dashboard?code=000001`，验证：
1. 分时图正常显示
2. 大单标注出现在图表上
3. 统计面板显示各级别的笔数和金额
4. 底部明细列表正常显示时间/状态/价格/手数/金额

- [ ] **Step 4: 验证轮询**

在浏览器开发者工具 Network 面板中观察：
- 交易时间内：每5秒自动发起 `/api/v1/l2_dashboard` 请求
- 非交易时间：不发起轮询请求（初始加载只有一次）

- [ ] **Step 5: 最终提交**

确认一切正常后，如果有任何修复性改动：
```bash
git add -A
git commit -m "fix: 端到端验证修复"
```
