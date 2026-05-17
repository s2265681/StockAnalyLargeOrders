# 情绪周期研判离线化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「周期研判」生成完全移到离线 cron 任务，去掉前端触发，支持每日收盘后自动生成最新一天 + 全量倒序回填历史。

**Architecture:** 在 `routes/emotion_cycle.py` 抽出纯函数 `analyze_one_date`（幂等、不依赖 HTTP），由两个 jobs 脚本（每日 + 倒序回填）调用，shell 包装器经 crontab 每工作日 16:00 触发。删除前端「全量生成」按钮及对应 admin 端点。本地与线上共用同一 MySQL，写一次即一致。

**Tech Stack:** Python 3.13 / Flask（仅复用 helper，不起服务）/ unittest / MySQL / React (antd) / crontab

---

## File Structure

- `backend/routes/emotion_cycle.py` — 修改：新增 `analyze_one_date`；删除 admin 端点 `post_emotion_analysis_with_storage`、`BATCH_SIZE`、未用的 `admin_required` import
- `backend/jobs/emotion_cycle_daily.py` — 新建：每日任务，生成最新交易日
- `backend/jobs/backfill_emotion_cycle.py` — 新建：全量倒序回填
- `backend/jobs/run_emotion_cycle.sh` — 新建：shell 包装器
- `backend/tests/test_emotion_cycle.py` — 修改：新增 `analyze_one_date` 测试；删除 `test_batch_storage_requires_admin`
- `backend/tests/test_emotion_cycle_jobs.py` — 新建：jobs 单元测试
- `frontend/src/pages/EmotionCycle/index.js` — 修改：移除「全量生成」按钮、`handleBatchAnalysis`、`batchLoading`、死 import
- crontab — 新增一行（实施时确认后执行）

测试运行方式（从 `backend/` 目录）：
`venv/bin/python -m unittest tests.test_emotion_cycle tests.test_emotion_cycle_jobs -v`

---

## Task 1: 抽取 `analyze_one_date` 纯函数

**Files:**
- Modify: `backend/routes/emotion_cycle.py`（在 `_call_claude_batch` 定义之后、`BATCH_SIZE` 之前插入）
- Test: `backend/tests/test_emotion_cycle.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_emotion_cycle.py` 文件末尾 `if __name__ == "__main__":` 之前插入：

```python
class AnalyzeOneDateTest(unittest.TestCase):
    def _records(self):
        return [
            {"date": f"2026-05-{day:02d}", "limit_up_count": day}
            for day in range(8, 16)
        ]

    def test_skips_when_already_in_db(self):
        from routes.emotion_cycle import analyze_one_date
        with patch(
            "routes.emotion_cycle._get_analysis_from_db",
            return_value={"stage": "退潮期"},
        ):
            with patch("routes.emotion_cycle._call_claude_batch") as call_ai:
                with patch("routes.emotion_cycle._save_analysis_to_db") as save:
                    status = analyze_one_date("20260515", self._records())
        self.assertEqual(status, "skipped")
        call_ai.assert_not_called()
        save.assert_not_called()

    def test_uses_prior_five_days_as_context_and_saves(self):
        from routes.emotion_cycle import analyze_one_date
        ai_result = {
            "date": "2026-05-15",
            "stage": "退潮期",
            "analysis": "走弱",
            "advice": "轻仓",
            "recommendations": [],
        }
        with patch("routes.emotion_cycle._get_analysis_from_db", return_value=None):
            with patch(
                "routes.emotion_cycle._call_claude_batch",
                return_value=[ai_result],
            ) as call_ai:
                with patch(
                    "routes.emotion_cycle._save_analysis_to_db",
                    return_value=True,
                ) as save:
                    status = analyze_one_date("20260515", self._records())
        self.assertEqual(status, "saved")
        analyzed = call_ai.call_args.args[0]
        self.assertEqual(
            [r["date"] for r in analyzed],
            ["2026-05-10", "2026-05-11", "2026-05-12",
             "2026-05-13", "2026-05-14", "2026-05-15"],
        )
        save.assert_called_once_with("20260515", ai_result)

    def test_returns_failed_when_target_missing_in_ai_result(self):
        from routes.emotion_cycle import analyze_one_date
        with patch("routes.emotion_cycle._get_analysis_from_db", return_value=None):
            with patch(
                "routes.emotion_cycle._call_claude_batch",
                return_value=[{"date": "2026-05-14", "stage": "退潮期"}],
            ):
                with patch("routes.emotion_cycle._save_analysis_to_db") as save:
                    status = analyze_one_date("20260515", self._records())
        self.assertEqual(status, "failed")
        save.assert_not_called()

    def test_force_true_bypasses_db_skip(self):
        from routes.emotion_cycle import analyze_one_date
        ai_result = {"date": "2026-05-15", "stage": "退潮期"}
        with patch(
            "routes.emotion_cycle._get_analysis_from_db",
            return_value={"stage": "旧"},
        ):
            with patch(
                "routes.emotion_cycle._call_claude_batch",
                return_value=[ai_result],
            ):
                with patch(
                    "routes.emotion_cycle._save_analysis_to_db",
                    return_value=True,
                ) as save:
                    status = analyze_one_date(
                        "20260515", self._records(), force=True
                    )
        self.assertEqual(status, "saved")
        save.assert_called_once_with("20260515", ai_result)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && venv/bin/python -m unittest tests.test_emotion_cycle.AnalyzeOneDateTest -v`
Expected: FAIL — `ImportError: cannot import name 'analyze_one_date'`

- [ ] **Step 3: 实现函数**

在 `backend/routes/emotion_cycle.py` 中，`_call_claude_batch` 函数定义结束后、`BATCH_SIZE = 10` 这一行之前，插入：

```python
def analyze_one_date(target_dt: str, all_records: list, force: bool = False) -> str:
    """为单个交易日生成周期研判并存库（幂等、不依赖 HTTP）。

    返回 'skipped' | 'saved' | 'failed'。
    - force=False 且 DB 已有该日 → 'skipped'
    - 取 target 当日 + 之前 5 个交易日作趋势上下文
    - 调 _call_claude_batch，从返回中取 target 当日结果并存库
    """
    target_dt = str(target_dt).replace("-", "")
    if not force and _get_analysis_from_db(target_dt):
        logger.info(f"{target_dt} 已有周期研判，跳过")
        return "skipped"

    valid = [r for r in all_records if isinstance(r, dict) and _record_date_key(r)]
    ordered = sorted(valid, key=_record_date_key)
    idx = next(
        (i for i, r in enumerate(ordered) if _record_date_key(r) == target_dt),
        None,
    )
    if idx is None:
        logger.error(f"{target_dt} 不在记录列表中，无法分析")
        return "failed"

    ctx_start = max(0, idx - 5)
    batch = ordered[ctx_start:idx + 1]
    logger.info(f"分析 {target_dt}，上下文 {len(batch)} 条")

    results = _call_claude_batch(batch)
    item = next(
        (
            x for x in results
            if isinstance(x, dict) and _record_date_key(x) == target_dt
        ),
        None,
    )
    if item is None:
        logger.error(f"AI 返回未包含 {target_dt}")
        return "failed"

    if not _save_analysis_to_db(target_dt, item):
        logger.error(f"{target_dt} 存库失败")
        return "failed"
    logger.info(f"{target_dt} 周期研判已存库")
    return "saved"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && venv/bin/python -m unittest tests.test_emotion_cycle.AnalyzeOneDateTest -v`
Expected: PASS — 4 tests OK

- [ ] **Step 5: 提交**

```bash
cd /Users/mac/Github/NiuNIuNiu
git add backend/routes/emotion_cycle.py backend/tests/test_emotion_cycle.py
git commit -m "feat: 抽取 analyze_one_date 幂等纯函数供离线任务复用"
```

---

## Task 2: 每日任务 `emotion_cycle_daily.py`

**Files:**
- Create: `backend/jobs/emotion_cycle_daily.py`
- Test: `backend/tests/test_emotion_cycle_jobs.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_emotion_cycle_jobs.py`：

```python
import unittest
from unittest.mock import patch


class EmotionCycleDailyTest(unittest.TestCase):
    def _records(self):
        return [
            {"date": f"2026-05-{day:02d}", "limit_up_count": day}
            for day in range(8, 16)
        ]

    def test_run_default_picks_latest_trading_day(self):
        from jobs.emotion_cycle_daily import run
        with patch(
            "jobs.emotion_cycle_daily._fetch_emotion_records",
            return_value=self._records(),
        ):
            with patch(
                "jobs.emotion_cycle_daily.analyze_one_date",
                return_value="saved",
            ) as analyze:
                run(None)
        self.assertEqual(analyze.call_args.args[0], "20260515")

    def test_run_explicit_date_passes_through(self):
        from jobs.emotion_cycle_daily import run
        with patch(
            "jobs.emotion_cycle_daily._fetch_emotion_records",
            return_value=self._records(),
        ):
            with patch(
                "jobs.emotion_cycle_daily.analyze_one_date",
                return_value="skipped",
            ) as analyze:
                run("20260512")
        self.assertEqual(analyze.call_args.args[0], "20260512")

    def test_run_raises_when_no_records(self):
        from jobs.emotion_cycle_daily import run
        with patch(
            "jobs.emotion_cycle_daily._fetch_emotion_records",
            return_value=[],
        ):
            with self.assertRaises(SystemExit):
                run(None)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && venv/bin/python -m unittest tests.test_emotion_cycle_jobs -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobs.emotion_cycle_daily'`

- [ ] **Step 3: 实现脚本**

新建 `backend/jobs/emotion_cycle_daily.py`：

```python
#!/usr/bin/env python3
"""收盘后定时任务：生成最新交易日的情绪周期研判。

用法：
  python jobs/emotion_cycle_daily.py            # 跑 StockAPI 最新交易日
  python jobs/emotion_cycle_daily.py 20260515   # 跑指定日期
  python jobs/emotion_cycle_daily.py 20260515 force  # 强制重生成

建议 crontab（工作日 16:00）：
  0 16 * * 1-5 /Users/mac/Github/NiuNIuNiu/backend/jobs/run_emotion_cycle.sh \
    >> /Users/mac/Github/NiuNIuNiu/emotion_cycle_job.log 2>&1
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.emotion_cycle import (
    _fetch_emotion_records,
    _record_date_key,
    analyze_one_date,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("emotion_cycle_daily")


def run(dt=None, force=False):
    logger.info(f"===== 开始周期研判定时任务 date={dt or 'latest'} =====")
    records = _fetch_emotion_records()
    if not records:
        logger.error("未获取到情绪周期数据")
        sys.exit(1)

    ordered = sorted(
        (r for r in records if isinstance(r, dict) and _record_date_key(r)),
        key=_record_date_key,
    )
    target = dt if dt else _record_date_key(ordered[-1])

    status = analyze_one_date(target, records, force=force)
    logger.info(f"===== 任务完成 date={target} status={status} =====")
    if status == "failed":
        sys.exit(1)


if __name__ == "__main__":
    dt_arg = sys.argv[1] if len(sys.argv) > 1 else None
    force_arg = len(sys.argv) > 2 and sys.argv[2] == "force"
    run(dt_arg, force_arg)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && venv/bin/python -m unittest tests.test_emotion_cycle_jobs -v`
Expected: PASS — 3 tests OK

- [ ] **Step 5: 提交**

```bash
cd /Users/mac/Github/NiuNIuNiu
git add backend/jobs/emotion_cycle_daily.py backend/tests/test_emotion_cycle_jobs.py
git commit -m "feat: 新增周期研判每日离线任务"
```

---

## Task 3: 倒序回填 `backfill_emotion_cycle.py`

**Files:**
- Create: `backend/jobs/backfill_emotion_cycle.py`
- Test: `backend/tests/test_emotion_cycle_jobs.py`（追加测试类）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_emotion_cycle_jobs.py` 的 `if __name__ == "__main__":` 之前插入：

```python
class BackfillEmotionCycleTest(unittest.TestCase):
    def _records(self):
        return [
            {"date": f"2026-05-{day:02d}", "limit_up_count": day}
            for day in range(8, 16)
        ]

    def test_iterates_newest_to_oldest_skipping_existing(self):
        from jobs.backfill_emotion_cycle import main
        calls = []

        def fake_analyze(dt, records, force=False):
            calls.append(dt)
            return "skipped" if dt == "20260514" else "saved"

        with patch(
            "jobs.backfill_emotion_cycle._fetch_emotion_records",
            return_value=self._records(),
        ):
            with patch(
                "jobs.backfill_emotion_cycle.analyze_one_date",
                side_effect=fake_analyze,
            ):
                with patch("jobs.backfill_emotion_cycle.time.sleep"):
                    main()

        self.assertEqual(
            calls,
            ["20260515", "20260514", "20260513", "20260512",
             "20260511", "20260510", "20260509", "20260508"],
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && venv/bin/python -m unittest tests.test_emotion_cycle_jobs.BackfillEmotionCycleTest -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobs.backfill_emotion_cycle'`

- [ ] **Step 3: 实现脚本**

新建 `backend/jobs/backfill_emotion_cycle.py`：

```python
#!/usr/bin/env python3
"""历史周期研判全量倒序回填（幂等跳过已有）。

用法：
  python jobs/backfill_emotion_cycle.py        # 回填全部历史，从新到旧
  python jobs/backfill_emotion_cycle.py force  # 强制重生成全部
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.emotion_cycle import (
    _fetch_emotion_records,
    _record_date_key,
    analyze_one_date,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_emotion_cycle")


def main():
    force = len(sys.argv) > 1 and sys.argv[1] == "force"
    records = _fetch_emotion_records()
    if not records:
        logger.error("未获取到情绪周期数据")
        sys.exit(1)

    ordered = sorted(
        (r for r in records if isinstance(r, dict) and _record_date_key(r)),
        key=_record_date_key,
    )
    dates_desc = [_record_date_key(r) for r in reversed(ordered)]
    logger.info(f"准备倒序回填 {len(dates_desc)} 个交易日: "
                f"{dates_desc[0]} → {dates_desc[-1]}")

    saved = skipped = failed = 0
    for dt in dates_desc:
        try:
            status = analyze_one_date(dt, records, force=force)
        except Exception as e:
            logger.error(f"{dt} 异常: {e}")
            failed += 1
            time.sleep(2)
            continue
        if status == "saved":
            saved += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1
        time.sleep(2)

    logger.info(f"回填完成：保存={saved} 跳过={skipped} 失败={failed}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && venv/bin/python -m unittest tests.test_emotion_cycle_jobs -v`
Expected: PASS — 4 tests OK（含 Task 2 的 3 个）

- [ ] **Step 5: 提交**

```bash
cd /Users/mac/Github/NiuNIuNiu
git add backend/jobs/backfill_emotion_cycle.py backend/tests/test_emotion_cycle_jobs.py
git commit -m "feat: 新增周期研判全量倒序回填脚本"
```

---

## Task 4: shell 包装器 `run_emotion_cycle.sh`

**Files:**
- Create: `backend/jobs/run_emotion_cycle.sh`

- [ ] **Step 1: 创建脚本**

新建 `backend/jobs/run_emotion_cycle.sh`：

```bash
#!/bin/bash
cd /Users/mac/Github/NiuNIuNiu/backend
venv/bin/python jobs/emotion_cycle_daily.py "$@"
```

- [ ] **Step 2: 加可执行权限**

Run: `chmod +x /Users/mac/Github/NiuNIuNiu/backend/jobs/run_emotion_cycle.sh`
Expected: 无输出，退出码 0

- [ ] **Step 3: 冒烟测试（mock 不调真 API，只验脚本能定位 python 和模块）**

Run: `cd /Users/mac/Github/NiuNIuNiu/backend && venv/bin/python -c "import jobs.emotion_cycle_daily; print('import ok')"`
Expected: `import ok`

- [ ] **Step 4: 提交**

```bash
cd /Users/mac/Github/NiuNIuNiu
git add backend/jobs/run_emotion_cycle.sh
git commit -m "feat: 新增周期研判任务 shell 包装器"
```

---

## Task 5: 删除 admin 端点及死代码

**Files:**
- Modify: `backend/routes/emotion_cycle.py:838-941`（删除 `post_emotion_analysis_with_storage` 整个函数及 `@emotion_cycle_bp.route` 装饰器）
- Modify: `backend/routes/emotion_cycle.py:835`（删除 `BATCH_SIZE = 10` 这一行）
- Modify: `backend/routes/emotion_cycle.py:15`（`from utils.auth_middleware import login_required, admin_required` → 去掉 `admin_required`）
- Modify: `backend/tests/test_emotion_cycle.py`（删除 `test_batch_storage_requires_admin` 方法）

- [ ] **Step 1: 删除测试方法**

在 `backend/tests/test_emotion_cycle.py` 中删除整个 `test_batch_storage_requires_admin` 方法（约 102-117 行，从 `def test_batch_storage_requires_admin(self):` 到该方法 `self.assertEqual(response.status_code, 200)` 结束）。删除后 `EmotionIntradayRefreshTest` 类只剩 `setUp` 和 `test_intraday_refresh_saves_separate_field`。

- [ ] **Step 2: 删除路由函数**

在 `backend/routes/emotion_cycle.py` 中删除从 `# ---------- 4. 全量情绪周期分析（为每一天生成分析） ----------` 注释块之后的 `@emotion_cycle_bp.route('/api/v1/emotion-analysis-with-storage', methods=['POST'])` 装饰器、`@admin_required`、整个 `def post_emotion_analysis_with_storage():` 函数体，直到文件末尾该函数结束。同时删除 `BATCH_SIZE = 10  # 每批处理的记录数` 这一行。保留该函数之前的 `BATCH_ANALYSIS_PROMPT`、`_fix_json_quotes`、`_call_claude_batch`、`analyze_one_date`（Task 1 新增）。

- [ ] **Step 3: 清理死 import**

在 `backend/routes/emotion_cycle.py` 第 15 行：

```python
from utils.auth_middleware import login_required, admin_required
```

改为：

```python
from utils.auth_middleware import login_required
```

- [ ] **Step 4: 运行全部后端测试确认通过**

Run: `cd backend && venv/bin/python -m unittest tests.test_emotion_cycle tests.test_emotion_cycle_jobs -v`
Expected: PASS — `AnalyzeOneDateTest` 4 + `EmotionCycleCurrentRefreshTest` 1 + `EmotionIntradayRefreshTest` 1 + jobs 4 = 10 tests OK，无 `test_batch_storage_requires_admin`

- [ ] **Step 5: 确认端点已不可达**

Run: `cd backend && grep -n "emotion-analysis-with-storage\|BATCH_SIZE\|admin_required" routes/emotion_cycle.py`
Expected: 无输出（全部已删除）

- [ ] **Step 6: 提交**

```bash
cd /Users/mac/Github/NiuNIuNiu
git add backend/routes/emotion_cycle.py backend/tests/test_emotion_cycle.py
git commit -m "refactor: 删除前端触发的周期研判 admin 端点（改为离线生成）"
```

---

## Task 6: 前端移除「全量生成」按钮

**Files:**
- Modify: `frontend/src/pages/EmotionCycle/index.js`

- [ ] **Step 1: 移除死 import（第 3 行）**

`frontend/src/pages/EmotionCycle/index.js` 第 3 行：

```javascript
import { ThunderboltOutlined, LeftOutlined, RightOutlined, ReloadOutlined } from '@ant-design/icons';
```

改为：

```javascript
import { LeftOutlined, RightOutlined, ReloadOutlined } from '@ant-design/icons';
```

- [ ] **Step 2: 移除 useAuth/isAdmin（第 17、193-194 行）**

删除第 17 行 `import { useAuth } from '../../context/AuthContext';`

将：

```javascript
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const todayStr = useMemo(() => getLastTradingDayStr(), []);
```

改为：

```javascript
  const todayStr = useMemo(() => getLastTradingDayStr(), []);
```

- [ ] **Step 3: 移除 batchLoading state（第 199 行）**

删除这一行：

```javascript
  const [batchLoading, setBatchLoading] = useState(false);
```

- [ ] **Step 4: 移除 handleBatchAnalysis 函数（第 250-268 行）**

删除整个 `const handleBatchAnalysis = async (force = false) => { ... };` 函数（从 `const handleBatchAnalysis` 到对应闭合 `};`）。

- [ ] **Step 5: 移除「全量生成」按钮块（第 404-417 行）**

删除日期导航栏内的 admin 按钮块：

```javascript
        {isAdmin && (
          <div className="date-nav-ai-btns">
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={() => handleBatchAnalysis(false)}
              loading={batchLoading}
              disabled={records.length === 0}
              className="ai-analysis-btn admin-batch-btn"
            >
              全量生成
            </Button>
          </div>
        )}
```

- [ ] **Step 6: 移除周期研判 AnalysisBlock 的 loading 属性**

将周期研判 block：

```javascript
          <AnalysisBlock
            title="周期研判"
            accent="cycle"
            result={cycleAnalysis}
            loading={batchLoading}
            emptyHint="暂无周期研判，请联系管理员生成"
          />
```

改为：

```javascript
          <AnalysisBlock
            title="周期研判"
            accent="cycle"
            result={cycleAnalysis}
            emptyHint="暂无周期研判，每日收盘后自动生成"
          />
```

- [ ] **Step 7: 构建校验**

Run: `cd frontend && npx eslint src/pages/EmotionCycle/index.js`
Expected: 无 `no-unused-vars` 等错误（`useState` 仍被其他 state 使用，保留）

- [ ] **Step 8: 提交**

```bash
cd /Users/mac/Github/NiuNIuNiu
git add frontend/src/pages/EmotionCycle/index.js
git commit -m "refactor: 移除前端周期研判全量生成按钮（改为离线生成）"
```

---

## Task 7: 配置 crontab（系统级，需用户确认）

**Files:** crontab（用户级）

- [ ] **Step 1: 查看现有 crontab**

Run: `crontab -l`
Expected: 现有两行（news.sh + run_echelon.sh）

- [ ] **Step 2: 向用户出示将追加的行并征得确认**

将追加：

```
0 16 * * 1-5 /Users/mac/Github/NiuNIuNiu/backend/jobs/run_emotion_cycle.sh >> /Users/mac/Github/NiuNIuNiu/emotion_cycle_job.log 2>&1
```

明确告知用户这是系统级修改，等用户确认后再执行 Step 3。

- [ ] **Step 3: 追加 crontab 行（用户确认后）**

Run: `(crontab -l 2>/dev/null; echo '0 16 * * 1-5 /Users/mac/Github/NiuNIuNiu/backend/jobs/run_emotion_cycle.sh >> /Users/mac/Github/NiuNIuNiu/emotion_cycle_job.log 2>&1') | crontab -`
Expected: 无输出

- [ ] **Step 4: 验证**

Run: `crontab -l | grep run_emotion_cycle`
Expected: 输出新增的那一行

---

## Task 8: 一次性全量倒序回填（人工触发）

- [ ] **Step 1: 提示用户这是真实 Claude 调用、耗时较长**

回填会对所有历史交易日逐日调 Claude（每日间隔 2s），可能耗时数十分钟并产生 API 费用。等用户确认后执行 Step 2。

- [ ] **Step 2: 后台运行回填**

Run（后台）: `cd /Users/mac/Github/NiuNIuNiu/backend && nohup venv/bin/python jobs/backfill_emotion_cycle.py >> /Users/mac/Github/NiuNIuNiu/emotion_cycle_backfill.log 2>&1 &`
Expected: 返回后台进程，日志写入 `emotion_cycle_backfill.log`

- [ ] **Step 3: 抽查结果**

Run: `tail -20 /Users/mac/Github/NiuNIuNiu/emotion_cycle_backfill.log`
Expected: 看到「保存=N 跳过=M 失败=K」结束行；失败为 0 或可解释

---

## Self-Review

**Spec 覆盖检查：**
- 抽取核心纯函数 → Task 1 ✓
- 每日任务 → Task 2 ✓
- 倒序回填 → Task 3 ✓
- shell 包装器 → Task 4 ✓
- crontab 0 16 * * 1-5 → Task 7 ✓
- 删除 admin 端点 + 死代码 → Task 5 ✓
- 前端移除按钮 → Task 6 ✓
- 一次性回填 → Task 8 ✓
- 一致性（同一 DB）→ 无需代码，spec 已说明 ✓
- 盘中研判不动 → 计划未触及 intraday 端点/按钮 ✓

**占位符扫描：** 无 TBD/TODO，所有代码步骤含完整代码 ✓

**类型/签名一致性：** `analyze_one_date(target_dt, all_records, force=False)` 返回 `'skipped'|'saved'|'failed'`，Task 2/3 调用签名一致；jobs 均 `from routes.emotion_cycle import _fetch_emotion_records, _record_date_key, analyze_one_date` ✓
