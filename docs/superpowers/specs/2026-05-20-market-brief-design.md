# 盘前资讯面板 设计文档

## 目标

在情绪周期页面顶部增加一条横条，展示海外市场夜盘涨跌 + AI 摘要入口。每天 8:30 定时生成，用户进页面直接读取缓存，点击摘要入口弹出完整内容。

## 架构

**数据流：**
```
cron 8:30 → market_brief_daily.py
  → fetch_overseas_indices()  → curl → Sina Finance API → 解析5只指数
  → generate_ai_summary()     → call_claude_for_scenario("market_brief") → 摘要文本
  → save_brief()              → upsert market_brief 表
```

**前端读取：**
```
EmotionCycle 页面加载 → GET /api/market-brief/today
  → 若有数据：渲染顶部横条（海外指数 + AI摘要入口）
  → 若无数据：不渲染横条（静默，不报错）
  → 点击"AI摘要"文字 → 弹窗展示完整 summary
```

## 数据模型

```sql
CREATE TABLE IF NOT EXISTS market_brief (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    brief_date   DATE     NOT NULL,
    overseas_json TEXT    NOT NULL,        -- JSON array，5只指数
    ai_summary   TEXT     NOT NULL,        -- Claude 生成的中文摘要
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_date (brief_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

`overseas_json` 结构示例：
```json
[
  {"symbol": "INDEXDOW",    "name": "道指",  "close": 34061.32, "change_pct": 1.23},
  {"symbol": "INDEXNASDAQ", "name": "纳指",  "close": 13456.78, "change_pct": 0.87},
  {"symbol": "INDEXSP",     "name": "标普",  "close": 4321.00,  "change_pct": 0.64},
  {"symbol": "INDEXHK",     "name": "恒指",  "close": 18234.56, "change_pct": -0.31},
  {"symbol": "INDEXNK225",  "name": "日经",  "close": 33567.00, "change_pct": 1.54}
]
```

## 后端文件

### 新增文件

| 文件 | 职责 |
|------|------|
| `backend/migrations/20260520_create_market_brief.sql` | 建表 |
| `backend/services/market_brief_service.py` | 拉数据、调 Claude、读写 DB |
| `backend/routes/market_brief.py` | GET `/api/market-brief/today` |
| `backend/jobs/market_brief_daily.py` | 独立执行的定时任务入口 |
| `backend/jobs/run_market_brief.sh` | Shell wrapper，供 crontab 调用 |
| `backend/tests/test_market_brief.py` | 单元测试 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `backend/config/ai_config.py` | 新增 `"market_brief"` scenario（sonnet，1024 tokens，90s）|
| `backend/app.py` | 注册 market_brief blueprint |
| `backend/jobs/crontab.server.txt` | 添加 `30 8 * * 1-5` 定时条目 |
| `.github/workflows/deploy.yml` | 迁移列表追加新 sql 文件 |

## 海外数据拉取

**API：** `https://hq.sinajs.cn/list=b_INDEXDOW,b_INDEXNASDAQ,b_INDEXSP,b_INDEXHK,b_INDEXNK225`

**响应格式（JS 变量字符串）：**
```
var hq_str_b_INDEXDOW="道琼斯指数,34061.32,33941.54,119.78,0.35,...";
```
字段顺序：名称, 最新价, 昨收, 涨跌额, 涨跌幅%（取 index 0/1/4）

**实现约束：** 必须用 curl 子进程调用（eventlet 下不能用 bare requests），与项目其他外部 HTTP 一致。

**解析逻辑：**
```python
# 每行：var hq_str_b_INDEXDOW="道琼斯指数,34061.32,33941.54,119.78,0.35,...";
# fields = line.split('"')[1].split(',')
# name=fields[0], close=float(fields[1]), change_pct=float(fields[4])
```

## AI 摘要

**scenario：** `"market_brief"`（新增到 `ai_config.py`）：sonnet，1024 tokens，90s timeout

**prompt 模板（传入 overseas_data 列表）：**
```
今日盘前数据如下（昨夜收盘）：
- 道指：+1.23%
- 纳指：+0.87%
- 标普：+0.64%
- 恒指：-0.31%
- 日经：+1.54%

请生成一份简洁的今日A股盘前参考摘要，包含：
1. 海外市场简评（1-2句）
2. 今日A股值得关注的板块方向（2-3个，结合海外表现推断）
3. 风险提示（1句）

要求：纯中文，总字数不超过200字，不需要标题，直接正文。
```

## 前端文件

### 新增文件

| 文件 | 职责 |
|------|------|
| `frontend/src/components/MarketBriefBar/index.js` | 顶部横条 + 弹窗组件 |
| `frontend/src/components/MarketBriefBar/index.css` | 样式 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `frontend/src/pages/EmotionCycle/index.js` | 在图表上方引入并渲染 `<MarketBriefBar />` |

## MarketBriefBar 组件

**行为：**
- 挂载时调用 `GET /api/market-brief/today`
- 无数据（`available: false`）→ 不渲染任何内容（隐藏）
- 有数据 → 渲染横条：`[盘前参考] 🇺🇸 道指 +1.23%  纳指 ...  |  📰 AI摘要：...→  [8:30 更新]`
- 点击 "📰 AI摘要：..." → Ant Design `Modal` 展示完整 `ai_summary`

**横条样式：**
- `height: 36px`，`background: #fff`，`border-bottom: 1px solid #f0f0f0`
- 指数颜色：涨为红（`#f5222d`），跌为绿（`#52c41a`）
- AI摘要入口：蓝色文字（`#1677ff`），最多显示 40 字 + "→"，超出截断

**API 响应格式：**
```json
{
  "success": true,
  "data": {
    "available": true,
    "brief_date": "2026-05-20",
    "generated_at": "2026-05-20 08:30:12",
    "overseas": [...],        // 5只指数数组
    "ai_summary": "..."       // 完整摘要文本
  }
}
```
无数据时：`{"success": true, "data": {"available": false}}`

## 容错处理

| 场景 | 处理 |
|------|------|
| Sina API 拉取失败 | 记录日志，任务退出码非零（不入库）|
| Claude 生成失败 | 记录日志，任务退出码非零（不入库）|
| 当日还未生成（< 8:30）| 接口返回 `available: false`，前端不渲染横条 |
| 非交易日 | 接口返回 `available: false`（无当日记录）|
| 前端请求失败 | catch 后静默，不显示横条，不报错 |

## cron 条目

```
# --- 盘前资讯 ---
30 8 * * 1-5 ${NIU_ROOT}/backend/jobs/run_market_brief.sh >> ${NIU_LOG}/market_brief_job.log 2>&1
```
