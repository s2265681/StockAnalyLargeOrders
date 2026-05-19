# AI 诊股「大家都在搜」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AI 诊股页面输入框下方新增标签区，展示当日已诊股票（大家都在搜）和同花顺热股 Top5，最多 10 个；同时增加慢分析提示和 localStorage 代码记忆。

**Architecture:** 后端新增 `GET /api/v1/ai-diagnosis/hot-stocks` 接口，复用已有 curl 子进程逻辑抓取同花顺热股（内存缓存 10 分钟），并查询 `ai_diagnosis_cache` 获取当日已诊记录。前端新增 `HotSearchTags` 组件消费该接口，点击已诊标签走缓存路径，点击热股标签走正常诊股路径。

**Tech Stack:** Python/Flask（后端），React 18 + Ant Design（前端），MySQL（已有 ai_diagnosis_cache 表）

---

## File Map

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/services/ai_diagnosis_service.py` | 修改 | 新增 `_fetch_ths_hot_top5` 和 `get_hot_stocks_for_diagnosis` |
| `backend/routes/ai_diagnosis.py` | 修改 | 新增 `GET /api/v1/ai-diagnosis/hot-stocks` 路由 |
| `backend/tests/test_ai_diagnosis.py` | 修改 | 新增服务函数和路由的测试 |
| `frontend/src/pages/AiDiagnosis/index.js` | 修改 | 新增 HotSearchTags 组件、localStorage 逻辑、慢分析提示 |
| `frontend/src/pages/AiDiagnosis/index.css` | 修改 | 新增热股标签区样式 |

---

## Task 1: 后端服务函数——热股抓取与已诊查询

**Files:**
- Modify: `backend/services/ai_diagnosis_service.py`

- [ ] **Step 1: 在 `ai_diagnosis_service.py` 顶部（现有 import 之后）新增缓存变量**

在 `_adapter = DataSourceAdapter(use_l2=False)` 这行下方插入：

```python
import time as _time

_HOT_STOCKS_CACHE: dict = {"data": None, "ts": 0.0}
_HOT_STOCKS_TTL = 600  # 10 分钟
```

- [ ] **Step 2: 新增 `_fetch_ths_hot_top5` 函数**

在 `get_trading_date_str` 函数之后插入：

```python
def _fetch_ths_hot_top5() -> list:
    """用 curl 子进程抓取同花顺热股，返回前5条 [{code, name}]。"""
    urls = [
        "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock?stock_type=a&type=hour&list_type=normal",
        "https://eq.10jqka.com.cn/open/api/hot_list/v1/hot_stock/a/hour/data.txt",
    ]
    for url in urls:
        try:
            proc = subprocess.run(
                ["curl", "-s", "--max-time", "10", url, "-H", "User-Agent: Mozilla/5.0"],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                continue
            data = json.loads(proc.stdout)
            if data.get("status_code") == 0:
                stock_list = data.get("data", {}).get("stock_list", [])
                result = []
                for item in stock_list[:5]:
                    code = str(item.get("code", "")).zfill(6)
                    name = item.get("name", "")
                    if code and name:
                        result.append({"code": code, "name": name})
                return result
        except Exception as e:
            logger.warning(f"同花顺热股抓取失败 {url}: {e}")
    return []
```

- [ ] **Step 3: 新增 `get_hot_stocks_for_diagnosis` 函数**

紧接在 `_fetch_ths_hot_top5` 之后插入：

```python
def get_hot_stocks_for_diagnosis() -> dict:
    """
    返回当日已诊股票列表（searched）和同花顺热股 Top5（hot）。
    hot 结果内存缓存 10 分钟。
    """
    global _HOT_STOCKS_CACHE
    now = _time.time()
    if _HOT_STOCKS_CACHE["data"] is None or now - _HOT_STOCKS_CACHE["ts"] > _HOT_STOCKS_TTL:
        _HOT_STOCKS_CACHE["data"] = _fetch_ths_hot_top5()
        _HOT_STOCKS_CACHE["ts"] = now
    hot = _HOT_STOCKS_CACHE["data"]

    trade_date = get_trading_date_str()
    searched = []
    try:
        rows = execute_query(
            "SELECT code, snapshot_json, report_json FROM ai_diagnosis_cache "
            "WHERE date=%s ORDER BY updated_at DESC",
            (trade_date,),
        )
        for row in rows:
            code = row["code"]
            try:
                snap = json.loads(row["snapshot_json"])
                rep = json.loads(row["report_json"])
                name = (
                    (snap.get("quote") or {}).get("name")
                    or (snap.get("basic") or {}).get("name")
                    or code
                )
                rating = rep.get("rating", "")
                searched.append({"code": code, "name": name, "rating": rating})
            except Exception:
                searched.append({"code": code, "name": code, "rating": ""})
    except Exception as e:
        logger.warning(f"查询已诊缓存失败: {e}")

    return {"searched": searched, "hot": hot}
```

- [ ] **Step 4: 确认函数可以被正常导入**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -c "from services.ai_diagnosis_service import get_hot_stocks_for_diagnosis; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai_diagnosis_service.py
git commit -m "feat: 新增热股抓取与当日已诊查询服务函数"
```

---

## Task 2: 后端路由——新增 hot-stocks 接口

**Files:**
- Modify: `backend/routes/ai_diagnosis.py`

- [ ] **Step 1: 在 `ai_diagnosis.py` 的 import 中补充 `get_hot_stocks_for_diagnosis`**

将现有第 13-17 行：
```python
from services.ai_diagnosis_service import (
    get_cache,
    get_trading_date_str,
    normalize_code,
    run_chat,
    run_diagnosis,
)
```
改为：
```python
from services.ai_diagnosis_service import (
    get_cache,
    get_hot_stocks_for_diagnosis,
    get_trading_date_str,
    normalize_code,
    run_chat,
    run_diagnosis,
)
```

- [ ] **Step 2: 在文件末尾新增路由**

```python
@ai_diagnosis_bp.route("/api/v1/ai-diagnosis/hot-stocks", methods=["GET"])
def get_hot_stocks():
    try:
        data = get_hot_stocks_for_diagnosis()
        return v1_success_response(data=data)
    except Exception as e:
        logger.error(f"热股标签失败: {e}", exc_info=True)
        return v1_success_response(data={"searched": [], "hot": []})
```

- [ ] **Step 3: 启动后端验证路由可访问**

```bash
curl -s http://localhost:9001/api/v1/ai-diagnosis/hot-stocks | python3 -m json.tool | head -20
```

Expected: `{"success": true, "data": {"searched": [...], "hot": [...]}}`

- [ ] **Step 4: Commit**

```bash
git add backend/routes/ai_diagnosis.py
git commit -m "feat: 新增 GET /api/v1/ai-diagnosis/hot-stocks 路由"
```

---

## Task 3: 后端测试

**Files:**
- Modify: `backend/tests/test_ai_diagnosis.py`

- [ ] **Step 1: 新增服务函数单元测试**

在 `test_ai_diagnosis.py` 末尾，`AiDiagnosisRouteTest` 类之外，新增：

```python
import time
from unittest.mock import patch, MagicMock


class TestGetHotStocksForDiagnosis(unittest.TestCase):
    def setUp(self):
        # 每次测试前清空热股缓存
        import services.ai_diagnosis_service as svc
        svc._HOT_STOCKS_CACHE["data"] = None
        svc._HOT_STOCKS_CACHE["ts"] = 0.0

    @patch("services.ai_diagnosis_service._fetch_ths_hot_top5")
    @patch("services.ai_diagnosis_service.execute_query")
    def test_returns_searched_and_hot(self, mock_query, mock_hot):
        mock_hot.return_value = [{"code": "300750", "name": "宁德时代"}]
        mock_query.return_value = [
            {
                "code": "000001",
                "snapshot_json": '{"quote": {"name": "平安银行"}, "basic": {}}',
                "report_json": '{"rating": "偏多"}',
            }
        ]
        from services.ai_diagnosis_service import get_hot_stocks_for_diagnosis
        result = get_hot_stocks_for_diagnosis()
        self.assertEqual(result["hot"], [{"code": "300750", "name": "宁德时代"}])
        self.assertEqual(len(result["searched"]), 1)
        self.assertEqual(result["searched"][0]["code"], "000001")
        self.assertEqual(result["searched"][0]["name"], "平安银行")
        self.assertEqual(result["searched"][0]["rating"], "偏多")

    @patch("services.ai_diagnosis_service._fetch_ths_hot_top5")
    @patch("services.ai_diagnosis_service.execute_query")
    def test_hot_cache_not_refetched_within_ttl(self, mock_query, mock_hot):
        mock_hot.return_value = [{"code": "600519", "name": "贵州茅台"}]
        mock_query.return_value = []
        from services.ai_diagnosis_service import get_hot_stocks_for_diagnosis
        get_hot_stocks_for_diagnosis()
        get_hot_stocks_for_diagnosis()
        self.assertEqual(mock_hot.call_count, 1)

    @patch("services.ai_diagnosis_service._fetch_ths_hot_top5")
    @patch("services.ai_diagnosis_service.execute_query")
    def test_db_error_returns_empty_searched(self, mock_query, mock_hot):
        mock_hot.return_value = []
        mock_query.side_effect = Exception("DB down")
        from services.ai_diagnosis_service import get_hot_stocks_for_diagnosis
        result = get_hot_stocks_for_diagnosis()
        self.assertEqual(result["searched"], [])
```

- [ ] **Step 2: 新增路由测试**

在 `AiDiagnosisRouteTest` 类中新增方法：

```python
    @patch("routes.ai_diagnosis.get_hot_stocks_for_diagnosis")
    def test_hot_stocks_route(self, mock_fn):
        mock_fn.return_value = {
            "searched": [{"code": "000001", "name": "平安银行", "rating": "偏多"}],
            "hot": [{"code": "300750", "name": "宁德时代"}],
        }
        resp = self.client.get("/api/v1/ai-diagnosis/hot-stocks")
        body = resp.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]["searched"]), 1)
        self.assertEqual(len(body["data"]["hot"]), 1)

    @patch("routes.ai_diagnosis.get_hot_stocks_for_diagnosis")
    def test_hot_stocks_route_error_returns_empty(self, mock_fn):
        mock_fn.side_effect = Exception("unexpected")
        resp = self.client.get("/api/v1/ai-diagnosis/hot-stocks")
        body = resp.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["searched"], [])
        self.assertEqual(body["data"]["hot"], [])
```

- [ ] **Step 3: 运行测试，确认全部通过**

```bash
cd /Users/mac/Github/NiuNIuNiu/backend
python -m pytest tests/test_ai_diagnosis.py -v
```

Expected: 所有测试 PASS，无 FAIL。

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_ai_diagnosis.py
git commit -m "test: 覆盖 hot-stocks 服务函数与路由"
```

---

## Task 4: 前端——HotSearchTags 组件 + localStorage + 慢分析提示

**Files:**
- Modify: `frontend/src/pages/AiDiagnosis/index.js`

- [ ] **Step 1: 在文件顶部 import 中补充 `SearchOutlined`**

现有 import：
```js
import {
  RobotOutlined,
  SendOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  RiseOutlined,
  FallOutlined,
  AlertOutlined,
  FundOutlined,
  FireOutlined,
  StockOutlined,
} from '@ant-design/icons';
```

改为（新增 `SearchOutlined`）：
```js
import {
  RobotOutlined,
  SendOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  RiseOutlined,
  FallOutlined,
  AlertOutlined,
  FundOutlined,
  FireOutlined,
  StockOutlined,
  SearchOutlined,
} from '@ant-design/icons';
```

- [ ] **Step 2: 在文件顶部常量区新增 localStorage key**

在 `const CHAT_TIMEOUT = 60000;` 之后插入：

```js
const LS_CODE_KEY = 'ai_diagnosis_last_code';
```

- [ ] **Step 3: 新增 `HotSearchTags` 组件**

在 `function AiDiagnosis()` 之前插入：

```js
function HotSearchTags({ onSearchedClick, onHotClick }) {
  const [hotData, setHotData] = useState({ searched: [], hot: [] });

  useEffect(() => {
    apiRequest('/api/v1/ai-diagnosis/hot-stocks', { timeout: 10000 })
      .then((res) => {
        if (res.success && res.data) setHotData(res.data);
      })
      .catch(() => {});
  }, []);

  const { searched, hot } = hotData;
  const hotVisible = hot.slice(0, Math.max(0, 10 - searched.length));

  if (!searched.length && !hotVisible.length) return null;

  return (
    <div className="ai-hot-tags">
      {searched.map((s) => (
        <Tag
          key={`s-${s.code}`}
          className="ai-hot-tag ai-hot-tag--searched"
          icon={<SearchOutlined />}
          onClick={() => onSearchedClick(s.code)}
        >
          {s.name || s.code}
        </Tag>
      ))}
      {searched.length > 0 && hotVisible.length > 0 && (
        <span className="ai-hot-divider" />
      )}
      {hotVisible.map((h) => (
        <Tag
          key={`h-${h.code}`}
          className="ai-hot-tag ai-hot-tag--hot"
          icon={<FireOutlined />}
          onClick={() => onHotClick(h.code)}
        >
          {h.name || h.code}
        </Tag>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: 在 `AiDiagnosis` 组件内添加 localStorage 恢复逻辑**

在现有的 `const cacheRetryTimerRef = useRef(null);` 之后插入：

```js
  // 页面 mount 时恢复上次输入的代码（不自动查询）
  useEffect(() => {
    const saved = localStorage.getItem(LS_CODE_KEY);
    if (saved && /^\d{1,6}$/.test(saved)) setCode(saved);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 5: 输入框 onChange 写入 localStorage**

将现有输入框的 `onChange`：
```js
onChange={(e) => setCode(e.target.value)}
```
改为：
```js
onChange={(e) => {
  setCode(e.target.value);
  localStorage.setItem(LS_CODE_KEY, e.target.value);
}}
```

- [ ] **Step 6: 在 `runDiagnosis` 中加慢分析提示**

在 `runDiagnosis` 函数内，`setLoading(true);` 这行之后插入：

```js
    message.info('AI 分析较慢，可先去看其他模块，回来后可继续查看', 6);
```

- [ ] **Step 7: 在 JSX 工具栏下方插入 `HotSearchTags`**

将现有：
```jsx
      <div className="ai-toolbar">
        ...
      </div>

      {error && (
```
在 `</div>` 和 `{error &&` 之间插入：

```jsx
      <HotSearchTags
        onSearchedClick={(c) => {
          setCode(c);
          tryLoadCache(c);
        }}
        onHotClick={(c) => {
          setCode(c);
          runDiagnosis(c, false);
        }}
      />
```

完整区块变为：
```jsx
      <div className="ai-toolbar">
        <Input
          className="ai-code-input"
          placeholder="股票代码，如 000001"
          value={code}
          onChange={(e) => {
            setCode(e.target.value);
            localStorage.setItem(LS_CODE_KEY, e.target.value);
          }}
          onPressEnter={() => runDiagnosis(code, false)}
          maxLength={12}
        />
        <div className="ai-toolbar-actions">
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={loading}
            onClick={() => runDiagnosis(code, false)}
          >
            开始诊股
          </Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => runDiagnosis(code, true)}>
            强制刷新
          </Button>
          {cached && <Tag color="cyan" className="ai-cache-tag">缓存</Tag>}
        </div>
      </div>

      <HotSearchTags
        onSearchedClick={(c) => {
          setCode(c);
          tryLoadCache(c);
        }}
        onHotClick={(c) => {
          setCode(c);
          runDiagnosis(c, false);
        }}
      />

      {error && (
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/AiDiagnosis/index.js
git commit -m "feat: 新增 HotSearchTags 组件、localStorage 代码记忆、慢分析提示"
```

---

## Task 5: 前端——热股标签区 CSS

**Files:**
- Modify: `frontend/src/pages/AiDiagnosis/index.css`

- [ ] **Step 1: 在 `index.css` 末尾追加样式**

```css
/* ── 热股标签区 ── */
.ai-hot-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.ai-hot-tag {
  cursor: pointer;
  font-size: 13px;
  padding: 2px 10px;
  border-radius: 12px;
  transition: opacity 0.15s;
  user-select: none;
}

.ai-hot-tag:hover {
  opacity: 0.78;
}

.ai-hot-tag--searched {
  background: rgba(22, 119, 255, 0.08);
  border-color: #1677ff;
  color: #1677ff;
}

.ai-hot-tag--hot {
  background: rgba(250, 140, 22, 0.1);
  border-color: #fa8c16;
  color: #fa8c16;
}

.ai-hot-divider {
  display: inline-block;
  width: 1px;
  height: 18px;
  background: var(--border-color, #d9d9d9);
  margin: 0 4px;
  vertical-align: middle;
  flex-shrink: 0;
}
```

- [ ] **Step 2: 在浏览器中验证样式正确**

在开发环境打开 `http://localhost:3000`（或项目前端端口），导航到「AI 诊股」页面，确认：
- 标签区在工具栏下方、报错提示上方正确显示
- 「大家都在搜」标签蓝色图标、「热股」标签橙色图标
- 竖线分隔正确出现
- 点击标签触发正确行为（缓存 or 诊股）
- 刷新页面后输入框还原上次代码

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/AiDiagnosis/index.css
git commit -m "style: 热股标签区样式"
```

---

## 自检：Spec Coverage

| 需求点 | 对应 Task |
|--------|-----------|
| 大家都在搜标签（当日已诊） | Task 1 + Task 4 |
| 同花顺热股 Top5 标签 | Task 1 + Task 4 |
| 大家都在搜在前，热股在后 | Task 4 Step 3（hotVisible slice 逻辑） |
| 最多 10 个标签 | Task 4 Step 3（`Math.max(0, 10 - searched.length)`） |
| 点已诊标签直接读缓存 | Task 4 Step 7（`onSearchedClick` → `tryLoadCache`） |
| 点热股标签正常发起诊股 | Task 4 Step 7（`onHotClick` → `runDiagnosis`） |
| 慢分析提示 | Task 4 Step 6 |
| localStorage 记住代码 | Task 4 Step 4 + Step 5 |
| 热股内存缓存 10 分钟 | Task 1 Step 1 + Step 3 |
| 后端接口 | Task 2 |
| 测试覆盖 | Task 3 |
