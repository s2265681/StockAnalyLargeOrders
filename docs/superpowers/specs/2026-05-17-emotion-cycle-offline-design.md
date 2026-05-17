# 情绪周期研判离线化设计

日期：2026-05-17

## 背景与目标

当前「周期研判」由前端管理员点「全量生成」按钮触发 `POST /api/v1/emotion-analysis-with-storage`，
后端拉 StockAPI 数据、分批调 Claude、写入共享 MySQL `emotion_analysis_results` 表。

问题：生成依赖人工点击；前端触发与潜在的其他生成路径可能造成结果不一致。

目标：把**周期研判**生成流程完全移到离线，去掉前端触发，每日收盘后自动生成最新一天，
并支持一次性全量倒序回填历史。

**范围限定**：仅「周期研判」离线化。「盘中研判」（实时刷新）保持现状不动。

## 关键约束

- 本地与线上**连同一个 MySQL 实例**。离线任务跑一次写入共享库，线上前端读同一库，
  一致性天然满足——无需任何同步逻辑。
- Claude 输出非确定性，"一致"只能靠"生成一次、共享存储"实现，不能靠两边各跑一次。
- 沿用现有 echelon 离线任务范式（`jobs/echelon_daily.py` + `run_echelon.sh` + crontab）。

## 架构

### 1. 后端核心抽取

在 `routes/emotion_cycle.py` 新增可复用纯函数（jobs 直接 import，与 echelon 范式一致）：

```python
def analyze_one_date(target_dt: str, all_records: list, force: bool = False) -> str:
    """为单个交易日生成周期研判并存库。

    返回: 'skipped' | 'saved' | 'failed'
    - force=False 且 DB 已有该日 → 'skipped'（幂等）
    - 取 target 当日 + 之前 5 个交易日作趋势上下文
    - 调 _call_claude_batch，从返回中取 target 当日结果
    - _save_analysis_to_db 存 target 当日；返回中找不到 target → 'failed'
    """
```

复用现有 helper：`_fetch_emotion_records()`、`_call_claude_batch()`、
`_save_analysis_to_db()`、`_get_analysis_from_db()`、`_record_date_key()`。
逻辑等价于现有 `refresh_current_emotion_analysis` 的单日分析，抽成纯函数、幂等、不依赖 HTTP。

### 2. 离线 jobs（三个新文件）

**`backend/jobs/emotion_cycle_daily.py`** — 每日任务
- 用法：`python jobs/emotion_cycle_daily.py [YYYYMMDD]`
- 默认 target = StockAPI 返回的最新交易日
- 调 `analyze_one_date(target, all_records, force=False)`
- 已有则跳过；StockAPI 拉取失败或单日失败 → exit 非 0（cron 日志可见）
- 可选 `force` 参数作逃生口

**`backend/jobs/backfill_emotion_cycle.py`** — 全量倒序回填
- 用法：`python jobs/backfill_emotion_cycle.py`
- 拉全部 records，按日期**从新到旧**逆序遍历
- 每日 `analyze_one_date(force=False)`，已有跳过
- 单日失败计数后继续下一日，每日间 `sleep(2)`
- 结束打印 成功/跳过/失败 计数

**`backend/jobs/run_emotion_cycle.sh`** — shell 包装器（同 `run_echelon.sh`）
```bash
#!/bin/bash
cd /Users/mac/Github/NiuNIuNiu/backend
venv/bin/python jobs/emotion_cycle_daily.py "$@"
```

### 3. Crontab

新增一行（周一到五下午 4 点）：
```
0 16 * * 1-5 /Users/mac/Github/NiuNIuNiu/backend/jobs/run_emotion_cycle.sh >> /Users/mac/Github/NiuNIuNiu/emotion_cycle_job.log 2>&1
```
修改 crontab 属系统级操作：实施时先给出确切命令、用户确认后再执行，不擅自改。

### 4. 后端端点删除

- 删除 `POST /api/v1/emotion-analysis-with-storage` 及其处理函数 `post_emotion_analysis_with_storage`
- 保留：`GET /api/v1/emotion-cycle`、`GET /api/v1/emotion-analysis-cache`、
  `GET /api/v1/emotion-intraday-cache`、`POST /api/v1/emotion-intraday-refresh`（全部不动）
- 其余两个未被前端使用的端点（`emotion-analysis`、`emotion-analysis-refresh-current`）
  属无关死代码，**不在本次范围**，保持原样

### 5. 前端改动 `frontend/src/pages/EmotionCycle/index.js`

- 删除 `handleBatchAnalysis` 函数、`batchLoading` state
- 删除日期导航栏里 `isAdmin && (...)` 的「全量生成」按钮块
- 周期研判 `AnalysisBlock` 的 `loading={batchLoading}` 移除（数据纯从 cache 读）
- 盘中刷新按钮 + handler 完全保留
- 若 `isAdmin` 仅此处使用则一并清理相关 import/变量

## 数据流

1. **一次性回填**：`backfill_emotion_cycle.py` → 拉全部 StockAPI records →
   从新到旧逐日，DB 无则带 5 日上下文调 Claude 存库 → 共享 MySQL 填满
2. **每日 16:00**（cron，工作日）：`run_emotion_cycle.sh` → 最新交易日 → 无则分析存库
3. **前端**：只读 `emotion-analysis-cache?date=X`；盘中刷新保持实时
4. **一致性**：单一共享 MySQL，本地任务写、线上前端读同一行，天然一致

## 错误处理

- StockAPI 拉取失败：日志 + exit 非 0，cron 日志可见
- 单日 Claude 失败：每日任务 exit 非 0（可见）；回填计 fail 后继续下一日
- 全程幂等，重跑安全

## 测试（沿用 `backend/tests/test_emotion_cycle.py`，TDD）

- `analyze_one_date`：DB 已有则跳过且不调 Claude；上下文窗口为前 5 日 + 当日；成功时存库
- 回填：逆序遍历、跳过已有
- mock `_fetch_emotion_records` 和 `_call_claude_batch`

## 不做（YAGNI）

- 不做本地↔线上同步逻辑（同一个 DB）
- 不动盘中研判
- 不清理无关死端点
- 不引入 APScheduler 等进程内调度（沿用 crontab）
