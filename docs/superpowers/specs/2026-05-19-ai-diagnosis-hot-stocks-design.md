# AI 诊股「大家都在搜」模块设计文档

**日期：** 2026-05-19
**状态：** 已确认

---

## 概述

在 AI 诊股页面输入框下方新增标签区，展示「大家都在搜（当日已诊过）」和「同花顺热股 Top5」，最多 10 个标签。同时优化慢分析提示体验，并通过 localStorage 记住用户上次输入的股票代码。

---

## 功能点

| 功能 | 说明 |
|------|------|
| 大家都在搜标签 | 从当日 ai_diagnosis_cache 读取已诊股票，以标签展示，点击直接读缓存 |
| 热股标签 | 同花顺热股 Top5，点击正常发起诊股 |
| 标签顺序 | 大家都在搜在前，热股在后，合计最多 10 个 |
| 慢分析提示 | 点「开始诊股」后立即 Toast 提示分析较慢，可先去看其他模块 |
| 记住输入代码 | 输入框 onChange 写 localStorage，页面 mount 时恢复（不自动查询） |

---

## 后端

### 新增服务函数

**文件：** `backend/services/ai_diagnosis_service.py`

新增 `get_hot_stocks_for_diagnosis()` 函数：

1. **同花顺热股抓取**：复用 `backend/routes/limit_up_echelon.py` 中 `_fetch_ths_hot_stocks` 的 curl 子进程逻辑，取前 5 条（`code`、`name`）。结果内存缓存 10 分钟（`_HOT_CACHE`），避免频繁请求。
2. **当日已诊列表**：查询 `ai_diagnosis_cache`，取当日所有记录，从 `snapshot_json` 提取 `name`，从 `report_json` 提取 `rating`，按 `updated_at` 倒序。
3. **返回结构**：
   ```json
   {
     "searched": [{"code": "000001", "name": "平安银行", "rating": "偏多"}],
     "hot": [{"code": "300750", "name": "宁德时代"}]
   }
   ```

### 新增路由

**文件：** `backend/routes/ai_diagnosis.py`

```
GET /api/v1/ai-diagnosis/hot-stocks
```

- 无参数，调用 `get_hot_stocks_for_diagnosis()` 返回标签数据
- 响应使用现有 `v1_success_response`

---

## 前端

### localStorage

- Key：`ai_diagnosis_last_code`
- 时机：输入框 `onChange` 时写入；页面 `useEffect` mount 时读取，恢复到 code state（不触发查询）

### 标签区组件 `HotSearchTags`

位于工具栏（`.ai-toolbar`）下方，独立 `<div className="ai-hot-tags">`。

**数据获取：** 页面 mount 时请求一次，结果存入 state `hotData: { searched: [], hot: [] }`。

**标签数量逻辑：**
- `searched` 取全部（当日已诊，理论上不多）
- `hot` 补至合计不超过 10 个
- 示例：3 个 searched + 5 个 hot = 8 个；0 个 searched + 5 个 hot = 5 个

**点击行为：**
- 「大家都在搜」标签：`setCode(code)` → 调 `tryLoadCache(code)` → 从缓存展示，不走 AI
- 「热股」标签：`setCode(code)` → 调 `runDiagnosis(code, false)`

**视觉区分：**
- 大家都在搜标签：`color="blue"` + 前缀图标 `SearchOutlined`
- 热股标签：`color="orange"` + 前缀图标 `FireOutlined`
- 两组之间加竖线分隔（若两组均有数据）

### 慢分析提示

在 `runDiagnosis` 函数开始时（`setLoading(true)` 之后）立即执行：

```js
message.info('AI 分析较慢，可先去看其他模块，回来后可继续查看', 6);
```

6 秒后自动消失，不阻塞用户操作。

---

## 数据库

无新增表。复用现有 `ai_diagnosis_cache`（date, code, snapshot_json, report_json）。

---

## 不在范围内

- 登录用户隔离（大家都在搜为全局当日记录，不区分用户）
- 热股数据持久化（纯内存缓存，重启后第一次请求重新抓取）
- 搜索历史跨天保留

---

## API 汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/ai-diagnosis/hot-stocks` | 获取标签数据（新增） |
| POST | `/api/v1/ai-diagnosis` | 发起诊股（已有） |
| GET | `/api/v1/ai-diagnosis/cache?code=` | 读缓存（已有） |
