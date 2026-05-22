# AI 提示词重构 + 超短战法库扩展 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把分散重复的 AI 知识抽到单一事实源模块,战法库从 3 个扩到 7 个超短核心战法,并修掉仓位不一致、token 硬编码等杂项。

**Architecture:** 新建 `backend/config/ai_knowledge.py` 存放知识片段常量(字段说明/六大指标/五阶段/统一仓位表/7 战法)。`ai_prompts.py` 各 prompt 与 `skills/*.md` 全部从片段组合,后端 prompt 用精版战法、战法库文档用详版。纯提示词层改动,不动数据库。

**Tech Stack:** Python 3.13、Flask、pytest(unittest 风格)。测试运行环境:工作目录 `backend/`,命令前缀 `venv/bin/python -m pytest`。

设计文档: `docs/superpowers/specs/2026-05-22-ai-prompts-tactics-refactor-design.md`

---

## Task 1: 创建 ai_knowledge.py 知识片段常量

**Files:**
- Create: `backend/config/ai_knowledge.py`
- Test: `backend/tests/test_ai_knowledge.py`

知识片段从现有 `backend/config/ai_prompts.py` 的 `SYSTEM_PROMPT` 提取:
- `FIELD_GUIDE` ← 现有 `ai_prompts.py` 第 14-27 行「## 数据字段说明」整段(含标题行)
- `EMOTION_INDICATORS` ← 现有第 29-36 行「## 六大情绪指标交叉验证」整段
- `EMOTION_STAGES` ← 现有第 38-68 行「## 情绪周期五阶段」整段,但**五个阶段的仓位描述统一替换为下方 `POSITION_TABLE` 口径**(升温期统一为 6-8 成,删除「5-7成」旧值)
- `POSITION_TABLE` ← 新写,统一仓位表

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_ai_knowledge.py`:

```python
import unittest

from config import ai_knowledge as K


class KnowledgeFragmentsTest(unittest.TestCase):
    def test_field_guide_present(self):
        self.assertIn("rise_ratio", K.FIELD_GUIDE)
        self.assertIn("broken_board_count", K.FIELD_GUIDE)

    def test_emotion_indicators_present(self):
        self.assertIn("六大情绪指标", K.EMOTION_INDICATORS)
        self.assertIn("打板成功率", K.EMOTION_INDICATORS)

    def test_emotion_stages_present(self):
        for stage in ("冰点期", "修复期", "升温期", "高潮期", "退潮期"):
            self.assertIn(stage, K.EMOTION_STAGES)

    def test_position_table_unified(self):
        # 升温期统一为 6-8 成,旧的 5-7 成口径不得残留
        self.assertIn("6-8成", K.POSITION_TABLE)
        self.assertNotIn("5-7成", K.POSITION_TABLE)
        self.assertNotIn("5-7成", K.EMOTION_STAGES)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'config.ai_knowledge'`

- [ ] **Step 3: 创建 ai_knowledge.py 片段常量**

创建 `backend/config/ai_knowledge.py`,先放四个字符串常量。`FIELD_GUIDE`、`EMOTION_INDICATORS` 直接搬运现有 `ai_prompts.py` `SYSTEM_PROMPT` 内对应整段文本。`EMOTION_STAGES` 搬运五阶段整段,但每阶段的「策略/仓位」行改为引用统一口径。`POSITION_TABLE` 新写:

```python
"""AI 知识片段单一事实源 — 后端 prompt 与 skills/*.md 共用。"""
from __future__ import annotations

from dataclasses import dataclass

FIELD_GUIDE = """## 数据字段说明
- date: 日期
- rise_ratio: 上涨比例（上涨家数/下跌家数，>1 表示涨多跌少）
- rise_count: 上涨家数（辅助字段）
- fall_count: 下跌家数（辅助字段）
- consec_limit: 连板家数（当日有多少只连板股）
- pressure_height: 压力高度(历史最高连板高度)
- latest_height: 最新高度(当前市场最高连板)
- big_loss_mood: 大面情绪(越高=亏钱效应越强，即跌幅>7%的前期强势股数量)
- big_profit_mood: 大肉情绪(越高=赚钱效应越强，即涨幅>7%的股票数量)
- limit_up_count: 涨停家数
- board_hit_rate: 打板成功率(%)
- limit_down_count: 跌停家数
- monster_stock: 妖股名称(当日最高连板股)
- broken_board_count: 炸板家数（封板后打开的股票数）"""

EMOTION_INDICATORS = """## 六大情绪指标交叉验证

1. **涨停/跌停数量** — 情绪基本温度计。涨停数反映赚钱效应广度，跌停数反映亏钱效应烈度。
2. **连板高度(latest_height)** — 情绪天花板。高标断板往往是情绪转折的关键信号。
3. **大面情绪(big_loss_mood)** — 亏钱效应烈度。>20=极端恐慌，10-20=较强亏钱，5-10=温和，<5=健康。
4. **大肉情绪(big_profit_mood)** — 赚钱效应强度。>80=极强（高潮），>60=强（升温），<40=弱。
5. **打板成功率(board_hit_rate)** — 打板资金盈亏。>65%=强，50-65%=温和，<40%=亏钱。
6. **炸板家数(broken_board_count)** — 市场分歧度。炸板/涨停比>0.5=分歧极大。"""

POSITION_TABLE = """## 统一仓位表（情绪周期对应总仓位）
- 冰点期：0-1成 — 空仓为主，板块集体抵抗可极轻仓试错龙头
- 修复期：2-3成 — 小仓试错，锁定率先连板方向
- 升温期：6-8成 — 加仓做龙头确认买点 + 强势板块补涨龙
- 高潮期：6-8成 — 持股不加仓，逐步提高止盈标准
- 退潮期：0-2成 — 减仓/空仓，绝不追高，不抄底补跌股
单票上限 1-3成；首板一进二、打板单票不超过 3成。"""

EMOTION_STAGES = """## 情绪周期五阶段

### 1. 冰点期
- 核心条件：涨停<30只，跌停>50只，无3板以上连板
- 辅助确认：大面情绪>20，打板成功率<40%，大肉情绪<20
- 仓位：0-1成（见统一仓位表）。若板块集体抵抗可极轻仓试错龙头
- 转折信号：跌停连续2日减少 + 某方向出现2连板

### 2. 修复期
- 核心条件：涨停30-50只，跌停明显减少，出现3板股
- 辅助确认：大面情绪降至10以下，打板成功率40-50%，大肉情绪回升
- 仓位：2-3成。小仓位试错，锁定率先打出连板的方向龙头
- 转折信号：大肉情绪>50 + 出现4板股 + 连续2日涨停递增

### 3. 升温期
- 核心条件：涨停50-80只，有5板以上龙头，连板家数明显增多
- 辅助确认：大肉情绪>60，大面情绪<5，打板成功率50-65%
- 仓位：6-8成。做龙头确认买点和强势板块补涨龙
- 警惕信号：打板成功率开始下降但仍>50% = 可能进入高潮末期

### 4. 高潮期
- 核心条件：涨停>100只，多只高位连板(7板+)，连板家数>15
- 辅助确认：大肉情绪>80，大面情绪极低(<3)，打板成功率>65%
- 仓位：6-8成，持股为主不加仓，逐步提高止盈标准
- 退潮预警：打板成功率持续下降 + 高标股大幅分歧 + 跟风股掉队

### 5. 退潮期
- 核心条件：涨停骤降(较前日减少30%以上)，大面情绪急升(>15)
- 辅助确认：炸板家数远超涨停家数，打板成功率骤降，龙头断板或天地板
- 仓位：0-2成。减仓或空仓，绝不追高，不抄底补跌股
- 底部信号：跌停开始缩减 + 新方向出现涨停板块效应

## 趋势判断要点
- 不要只看单日数据，要看近5-10日的趋势变化方向
- 关注"拐点"：连续上升后的首次回落，或连续下降后的首次回升
- 炸板/涨停比例是分歧度的关键指标
- 情绪周期不一定按顺序走，可能从高潮直接跳到冰点"""
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 提交**

```bash
git add backend/config/ai_knowledge.py backend/tests/test_ai_knowledge.py
git commit -m "feat: 新建 ai_knowledge 知识片段单一事实源"
```

---

## Task 2: ai_knowledge.py 新增 Tactic 与 7 战法

**Files:**
- Modify: `backend/config/ai_knowledge.py`
- Test: `backend/tests/test_ai_knowledge.py`

战法 1-3 详版正文搬运现有 `skills/trading-patterns.md`(战法一/二/三整段)。战法 4-7 为新增,正文内容见 Step 3。

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_ai_knowledge.py` 末尾追加:

```python
class TacticsTest(unittest.TestCase):
    EXPECTED = [
        "龙头首阴低吸", "爆量涨停弱转强", "首板一进二",
        "打板接力", "断板反包", "龙回头", "中军补涨",
    ]

    def test_seven_tactics(self):
        self.assertEqual(len(K.TACTICS), 7)
        for key in self.EXPECTED:
            self.assertIn(key, K.TACTICS)

    def test_tactic_has_brief_and_full(self):
        for key, tac in K.TACTICS.items():
            self.assertTrue(tac.brief, f"{key} brief 为空")
            self.assertTrue(tac.full, f"{key} full 为空")
            self.assertTrue(len(tac.full) > len(tac.brief), f"{key} full 应比 brief 长")

    def test_tactics_brief_has_adapt_table(self):
        self.assertIn("情绪适配", K.TACTICS_BRIEF)
        for stage in ("冰点期", "升温期", "退潮期"):
            self.assertIn(stage, K.TACTICS_BRIEF)

    def test_tactics_full_covers_all(self):
        for tac in K.TACTICS.values():
            self.assertIn(tac.full, K.TACTICS_FULL)
        # 调研共识必须写入战法库前言
        self.assertIn("没有永恒有效的战法", K.TACTICS_FULL)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py::TacticsTest -q`
Expected: FAIL — `AttributeError: module 'config.ai_knowledge' has no attribute 'TACTICS'`

- [ ] **Step 3: 实现 Tactic 与 7 战法**

在 `backend/config/ai_knowledge.py` 追加。`Tactic` dataclass + `TACTICS` 字典。战法 1-3 的 `full` 用 `skills/trading-patterns.md` 现有正文,`brief` 为压缩要点。战法 4-7 的 `full` 用以下内容(每个战法正文结构:核心逻辑 / 触发条件 / 买点 / 仓位 / 止损 / 风险 / 情绪适配):

战法四「打板接力」核心内容:
- 核心逻辑:打板买的是确定性溢价,溢价=个股质量×情绪环境;接力打板必须看地位,没地位的接力板不打。
- 三手法:扫板(差1-2档买入,确定性高、没板损失大)、排板(涨停后排队,稳健可撤单)、回封板(炸板回封再买)。
- 接力地位三类:续命板(老题材股碰新热点续命,逢板必打)、小龙头(新题材2-3板,谨慎)、总龙头(干掉对手且题材继续发酵)。
- 触发条件:①属当日领涨主线题材 ②不涨停不买,最后一档卖一确认才买 ③对后市有3-5板空间预期 ④逻辑先行(大盘/热点/个股都有把握)。
- 半路板列为反面教材:散户最易亏钱环节,冲高回落概率大,宁可排队没买进也不打错。
- 买点:盘前计划票可扫板,盘中临时决定的排板。
- 止损:没封板日内即走;封单突撤或要炸板及时撤单。
- 情绪适配:升温期积极、修复期只打主线龙头、退潮期不打。

战法五「断板反包」核心内容:
- 核心逻辑:连板票断板后弱转强,博"强更强";本质是情绪转变的把控,确定性达70%才试错。
- 触发条件:①连板≥3板后断板(首板断板不算,要辨识度) ②断板当天爆巨量大换手(筹码已交换) ③断板当天分时有明显进攻(早盘冲高即回落不算) ④预判次日情绪延续高潮或修复(分歧则成功率大降)。
- 子型:一字反包(情绪回暖节点做最快反包的创业板股)、N字反包(下跌盘整后涨停放量回调,靠近低位支撑企稳买入)。
- 买点:反包当天(激进者断板买,保守者反包后下一天打板)。
- 止损:时间止损—次日11点前未翻红即止损;形态止损—跌破涨停板底部止损。
- 情绪适配:高潮/修复期做,分歧期回避。

战法六「龙回头」核心内容:
- 核心逻辑:龙头大幅拉升后回调洗盘,做第二波;解决"发现龙头时已买不到"。
- 触发条件:①前期是有几个涨停板的强势龙头 ②前期放量拉升 + 回踩极度缩量(主力未离场) ③回踩有均线支撑(超短看10日线、波段看20日线) ④调整窗口3-10日(理想5-7日) ⑤第一波涨幅50-80%为佳(涨2-3倍易走双重顶)。
- 买点:确认见底、成交额缩倍量,分时杀跌低吸;回踩20日线附近借分时低吸;规避换手不充分的一字连板。
- 特殊情形:因大盘大跌导致的龙回头可操作性更好(主力没来得及出),回调时间越短幅度越小越好。
- 止损:调整低点下方一定幅度;跌破支撑均线止损。
- 风险:大盘震荡/持续下跌时谨慎;龙头死于天量跌停、妖股死于加速。

战法七「中军补涨」核心内容:
- 核心逻辑:中军=介于龙头与杂毛之间、承接龙头人气且有体量与确定性的中坚股;龙头回踩/休整时资金阶段性切换推动中军补涨。
- 触发条件:①题材主线明确且未退潮 ②龙头进入分歧/休整(非崩塌) ③中军股有一定流通体量、题材属性正宗、辨识度居板块第二梯队 ④板块仍有联动(3只+涨停)。
- 买点:龙头分歧日,中军股盘中启动、分时突破均线时跟随。
- 止损:龙头断头铡刀或板块崩则中军同步止损;中军跌破启动平台止损。
- 风险:中军本质是跟随,龙头一旦证伪中军最先被抛弃。
- 情绪适配:升温/高潮期有效,退潮期资金不切中军而直接撤,不做。

代码骨架:

```python
@dataclass(frozen=True)
class Tactic:
    name: str
    brief: str  # 一句话要点，进 API 提示词
    full: str   # 详细正文，进 trading-patterns.md


TACTICS: dict[str, Tactic] = {
    "龙头首阴低吸": Tactic(
        name="龙头首阴低吸",
        brief="龙头连涨后首根阴线低吸；跌幅-3%~-7%、量不超前日2倍；首阴日尾盘缩量企稳或次日不破首阴低点买入；退潮期不做。",
        full="""### 战法一：龙头首阴低吸
<搬运 skills/trading-patterns.md 战法一全文正文（去掉文件级标题）>""",
    ),
    "爆量涨停弱转强": Tactic(
        name="龙头爆量涨停 & 次日竞价弱转强",
        brief="龙头爆量封板（成交额创10日新高、换手>10%）→ 次日竞价高开+2%~5%、开盘弱转强突破开盘价确认买入；退潮期假信号多不做。",
        full="""### 战法二：龙头爆量涨停 & 次日竞价高开弱转强
<搬运 skills/trading-patterns.md 战法二全文正文>""",
    ),
    "首板一进二": Tactic(
        name="首板一进二",
        brief="从当日涨停筛强首板（主线题材+10:30前流畅封板+换手5%-15%+流通50-200亿）→ 次日竞价确认做二板；单票≤3成,分散2-3只。",
        full="""### 战法三：首板一进二
<搬运 skills/trading-patterns.md 战法三全文正文>""",
    ),
    "打板接力": Tactic(
        name="打板/接力",
        brief="扫板/排板/回封板三手法；接力必看地位（续命板/小龙头/总龙头）；不涨停不买；半路板是散户最易亏钱环节，宁可没买进不打错。",
        full="""### 战法四：打板/接力
<按 Step 3 战法四核心内容展开成完整正文>""",
    ),
    "断板反包": Tactic(
        name="断板反包",
        brief="连板≥3板断板后弱转强博强更强；断板需爆量大换手+分时进攻；含一字/N字反包；次日11点前未翻红时间止损；分歧期回避。",
        full="""### 战法五：断板反包
<按 Step 3 战法五核心内容展开成完整正文>""",
    ),
    "龙回头": Tactic(
        name="龙回头",
        brief="龙头大幅拉升后回踩做第二波；放量拉升+缩量回踩、5/10/20日线支撑、调整3-10日；缩倍量分时低吸；大盘弱时谨慎。",
        full="""### 战法六：龙回头
<按 Step 3 战法六核心内容展开成完整正文>""",
    ),
    "中军补涨": Tactic(
        name="中军补涨",
        brief="龙头休整时资金切向中军补涨；中军需体量+题材正宗+板块第二梯队；龙头分歧日分时突破跟随；退潮期不做。",
        full="""### 战法七：中军补涨
<按 Step 3 战法七核心内容展开成完整正文>""",
    ),
}

_TACTICS_PREFACE = """# 短线核心战法库

七大超短实战战法。重要前提：**没有永恒有效的战法**，机械套图形（龙回头、N字反包等）胜率未必过半。每个战法都以"情绪环境 + 资金预期"为前置判断——先想清楚这是游资票还是机构票、明天接力意愿高不高、当前哪类资金主导，再谈形态。
"""

_ADAPT_TABLE = """## 战法 × 情绪周期适配表
| 战法 | 冰点期 | 修复期 | 升温期 | 高潮期 | 退潮期 |
|------|--------|--------|--------|--------|--------|
| 龙头首阴低吸 | 不做 | 极轻仓试错 | 标准仓位 | 标准仓位 | 不做 |
| 爆量涨停&弱转强 | 不做 | 只做龙头(2成) | 积极(4-5成) | 谨慎(可能见顶) | 不做 |
| 首板一进二 | 不做 | 只做主线龙头(1成) | 积极筛选(2-3成) | 优选最强 | 不做 |
| 打板/接力 | 不做 | 只打主线龙头 | 积极 | 只打最强龙头 | 不打 |
| 断板反包 | 不做 | 修复期可做 | 做 | 做 | 分歧期回避 |
| 龙回头 | 不做 | 谨慎 | 做 | 做 | 大盘弱时不做 |
| 中军补涨 | 不做 | 谨慎 | 做 | 做 | 不做 |
"""

TACTICS_BRIEF = (
    "## 七大超短战法（精版）\n"
    + "\n".join(f"- **{t.name}**：{t.brief}" for t in TACTICS.values())
    + "\n\n"
    + _ADAPT_TABLE
)

TACTICS_FULL = (
    _TACTICS_PREFACE
    + "\n"
    + "\n\n".join(t.full for t in TACTICS.values())
    + "\n\n"
    + _ADAPT_TABLE
)
```

注:`<...>` 占位处在实现时替换为实际正文 — 战法 1-3 从 `skills/trading-patterns.md` 现有正文搬运,战法 4-7 把 Step 3 的核心内容按「核心逻辑/触发条件/买点/仓位/止损/风险/情绪适配」结构展开成完整段落。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: 提交**

```bash
git add backend/config/ai_knowledge.py backend/tests/test_ai_knowledge.py
git commit -m "feat: ai_knowledge 新增 7 个超短战法（精版+详版）"
```

---

## Task 3: 重构 ai_prompts.py 情绪周期类 prompts

**Files:**
- Modify: `backend/config/ai_prompts.py`
- Test: `backend/tests/test_ai_knowledge.py`

把 `SYSTEM_PROMPT`、`BATCH_ANALYSIS_PROMPT`、`SINGLE_DATE_ANALYSIS_PROMPT`、`DAILY_ANALYSIS_SYSTEM_PROMPT` 改为从 `ai_knowledge` 片段拼接。变量名保持不变,导入方零改动。

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_ai_knowledge.py` 末尾追加:

```python
class PromptCompositionTest(unittest.TestCase):
    def test_system_prompt_uses_fragments(self):
        from config import ai_prompts as P
        self.assertIn("broken_board_count", P.SYSTEM_PROMPT)   # FIELD_GUIDE
        self.assertIn("六大情绪指标", P.SYSTEM_PROMPT)          # EMOTION_INDICATORS
        self.assertIn("龙回头", P.SYSTEM_PROMPT)               # TACTICS_BRIEF
        self.assertIn("\"stage\"", P.SYSTEM_PROMPT)            # JSON schema 保留

    def test_no_stale_position_value(self):
        from config import ai_prompts as P
        # 旧的不一致仓位口径不得残留
        self.assertNotIn("5-7成", P.SYSTEM_PROMPT)
        self.assertNotIn("5-7成", P.BATCH_ANALYSIS_PROMPT)

    def test_single_date_keeps_placeholder(self):
        from config import ai_prompts as P
        self.assertIn("{FIELD_GUIDE}", P.SINGLE_DATE_ANALYSIS_PROMPT)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py::PromptCompositionTest -q`
Expected: FAIL — `test_no_stale_position_value` 因当前 `SYSTEM_PROMPT` 含「5-7成」而失败;`test_system_prompt_uses_fragments` 因不含「龙回头」而失败。

- [ ] **Step 3: 重构四个 prompt**

在 `backend/config/ai_prompts.py` 顶部 import 区加:

```python
from config.ai_knowledge import (
    FIELD_GUIDE,
    EMOTION_INDICATORS,
    EMOTION_STAGES,
    TACTICS_BRIEF,
)
```

**关键约束:用字符串拼接(`+`)组合片段,不要用 f-string。** JSON schema 段含大量 `{` `}`,f-string 会把它们当表达式;拼接则可让 JSON schema 保持普通字符串与单花括号。

把 `SYSTEM_PROMPT` 改为拼接(保留原角色设定首句与原 JSON schema 段,中间的字段说明/六大指标/五阶段/三大战法替换为片段):

```python
SYSTEM_PROMPT = (
    "你是短线情绪博弈的高手，能通过多维数据综合研判A股市场情绪周期。\n\n"
    + FIELD_GUIDE + "\n\n"
    + EMOTION_INDICATORS + "\n\n"
    + EMOTION_STAGES + "\n\n"
    + TACTICS_BRIEF + "\n\n"
    + """推荐标的筛选逻辑：
1. 首阴机会：前几日的monster_stock如果断板了（不再是最新monster_stock），大概率是龙头首阴。即使退潮期，前期总龙头的首阴也值得关注（轻仓试错）。
2. 爆量涨停机会：当日monster_stock或热门板块龙头中放巨量封板的标的。
3. 首板一进二机会：结合热门板块题材，筛选当日符合首板条件的强势股作为备选池。
4. 断板反包/龙回头机会：连板断板后弱转强、龙头回踩缩量企稳的标的。
5. 每个推荐要说明适用哪个战法、为什么符合条件。
6. 即使退潮期也要给出可观察/可轻仓试错的标的，不要只推荐"空仓观望"。

请严格按以下JSON格式返回（不要返回其他内容）：
{
  "stage": "冰点期/修复期/升温期/高潮期/退潮期",
  "analysis": "详细分析：包含数据趋势解读、关键拐点、与前几日对比（300字以内）",
  "advice": "操作建议：包含仓位、方向、风控（150字以内）",
  "recommendations": [
    {"stock": "股票名称", "reason": "推荐理由（说明符合哪个战法及原因）", "position": "建议仓位如2成"}
  ]
}"""
)
```

同理用拼接重写:
- `BATCH_ANALYSIS_PROMPT` = `FIELD_GUIDE + EMOTION_INDICATORS + EMOTION_STAGES + TACTICS_BRIEF` + 保留其多日数组 JSON schema 与「每个交易日一条」说明(JSON schema 保持单花括号普通字符串)。
- `SINGLE_DATE_ANALYSIS_PROMPT` 保持 `{FIELD_GUIDE}` 占位符不变(由 `emotion_cycle.py:1384` 替换),其余说明对齐片段口径。
- `DAILY_ANALYSIS_SYSTEM_PROMPT` 用拼接在「## 战法与输出要求」段后插入 `TACTICS_BRIEF`。

删除文件中已被片段取代的重复整段文本。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: 验证导入方未破坏**

Run: `cd backend && venv/bin/python -m pytest tests/test_emotion_cycle.py -q`
Expected: PASS(与改动前一致;若改动前已有失败则失败项不变)

- [ ] **Step 6: 提交**

```bash
git add backend/config/ai_prompts.py backend/tests/test_ai_knowledge.py
git commit -m "refactor: 情绪周期类 prompt 改用 ai_knowledge 片段拼接"
```

---

## Task 4: 诊股模板嵌入战法 + 新增战法字段

**Files:**
- Modify: `backend/config/ai_prompts.py`(`DIAGNOSIS_REPORT_TEMPLATE`)
- Test: `backend/tests/test_ai_knowledge.py`

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_ai_knowledge.py` 末尾追加:

```python
class DiagnosisTemplateTest(unittest.TestCase):
    def test_template_embeds_tactics(self):
        from config import ai_prompts as P
        self.assertIn("七大超短战法", P.DIAGNOSIS_REPORT_TEMPLATE)

    def test_template_has_new_fields(self):
        from config import ai_prompts as P
        self.assertIn("applicable_tactic", P.DIAGNOSIS_REPORT_TEMPLATE)
        self.assertIn("tactic_fit", P.DIAGNOSIS_REPORT_TEMPLATE)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py::DiagnosisTemplateTest -q`
Expected: FAIL — 模板不含 `applicable_tactic`。

- [ ] **Step 3: 修改 DIAGNOSIS_REPORT_TEMPLATE**

`DIAGNOSIS_REPORT_TEMPLATE` 当前是普通字符串(含 `{code}` `{snapshot_json}` 占位)。改为在「分析维度」列表后插入战法库精版,并在 JSON 结构里新增两个字段。具体:

1. 在第 8 维度「买卖点位」后追加第 9 维度:
   `9. **战法适配**：对照下方七大战法，判断该股当前最适用哪个战法（或均不适用），说明符合/不符合的关键触发条件`
2. 在「快照数据：」行之前插入战法精版。因 `DIAGNOSIS_REPORT_TEMPLATE` 用 `.replace()` 而非 f-string,改为在模块内用拼接构造:

```python
from config.ai_knowledge import TACTICS_BRIEF  # 已在 Task 3 import，勿重复

_DIAGNOSIS_BODY = """你是一位 A 股超短线交易分析师。请根据以下**真实数据快照**对股票 {code} 做全面诊股。
... (保留原 1-8 维度) ...
9. **战法适配**：对照下方七大战法，判断该股当前最适用哪个战法（或均不适用），说明符合/不符合的关键触发条件

输出要求：
- 只输出一个 JSON 对象，不要 markdown 代码块，不要 ``` 包裹，不要任何前后说明
- 正文用纯中文，不要用 **加粗**、# 标题、列表符号等 Markdown 语法
- buy_points/sell_points 每项为 {{"price":"价位或条件","reason":"依据"}}
"""

DIAGNOSIS_REPORT_TEMPLATE = (
    _DIAGNOSIS_BODY
    + "\n" + TACTICS_BRIEF + "\n\n"
    + """快照数据：
{snapshot_json}

JSON 结构（字段名必须一致）：
{{
  "rating": "偏多|中性|偏空",
  "theme_position": "龙头|前排核心|中军跟随|补涨|无题材",
  "position_advice": "重仓|轻仓试错|观望|不参与",
  "applicable_tactic": "适用战法名；均不适用则写「当前无适用战法」",
  "tactic_fit": "战法适配说明（80字内，讲清符合/不符合的关键触发条件）",
  "summary": "150字内一句话结论",
  ... (保留原其余字段) ...
}}"""
)
```

保留原模板所有既有字段(`emotion_fit`、`buy_points` 等)与 `sections` 结构,仅新增 `applicable_tactic`、`tactic_fit` 两字段。

**注意:** 原 `DIAGNOSIS_REPORT_TEMPLATE` 的 JSON 结构段用 `{{`/`}}` 双花括号写法,但它是普通字符串(非 f-string、非 `.format()`),`build_diagnosis_prompt()` 仅做 `.replace()`。保持 `{{`/`}}` 原样不变(本任务不修这个历史写法),`{code}`/`{snapshot_json}` 保持单花括号供 `.replace()` 命中。`build_diagnosis_prompt()` 函数无需改动。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py::DiagnosisTemplateTest -q`
Expected: PASS (2 passed)

- [ ] **Step 5: 验证 build_diagnosis_prompt 仍可用**

Run: `cd backend && venv/bin/python -c "from config.ai_prompts import build_diagnosis_prompt; s=build_diagnosis_prompt({'code':'000001'}); assert 'applicable_tactic' in s and '000001' in s; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 6: 提交**

```bash
git add backend/config/ai_prompts.py backend/tests/test_ai_knowledge.py
git commit -m "feat: 诊股报告嵌入战法库并新增战法适配字段"
```

---

## Task 5: skill 正文片段化 + 纳入 trading-patterns

**Files:**
- Modify: `backend/config/ai_prompts.py`(skill body 常量与 `AGENT_SKILLS`)
- Test: `backend/tests/test_ai_knowledge.py`

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_ai_knowledge.py` 末尾追加:

```python
class AgentSkillsTest(unittest.TestCase):
    def test_four_skills_registered(self):
        from config.ai_prompts import AGENT_SKILLS
        self.assertEqual(
            set(AGENT_SKILLS),
            {"stock-analysis", "market-sentiment", "board-hitting", "trading-patterns"},
        )

    def test_trading_patterns_body_has_seven_tactics(self):
        from config.ai_prompts import AGENT_SKILLS
        body = AGENT_SKILLS["trading-patterns"]["body"]
        for name in ("打板", "断板反包", "龙回头", "中军补涨"):
            self.assertIn(name, body)

    def test_skill_step1_data_wording(self):
        from config.ai_prompts import AGENT_SKILLS
        body = AGENT_SKILLS["stock-analysis"]["body"]
        # 结构化数据优先用 MCP，WebSearch 仅补消息面
        self.assertIn("禁止编造", body)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py::AgentSkillsTest -q`
Expected: FAIL — `AGENT_SKILLS` 只有 3 个 key。

- [ ] **Step 3: 改 skill body 与 AGENT_SKILLS**

1. `STOCK_ANALYSIS_SKILL_BODY` 的「### 第1步：获取全量数据」段,把要求 WebSearch 搜溢价率的措辞改为:

```
同时用 WebSearch 仅搜索增量信息：
- 该股最新消息、政策/事件催化
- 该股所在板块今日动态
注意：涨跌停数、首板/连板溢价等结构化数据优先用 MCP 工具（limit_up_themes 等）获取；无实时数据源的指标做定性判断，禁止编造精确数字。
```

2. `MARKET_SENTIMENT_SKILL_BODY`、`BOARD_HITTING_SKILL_BODY` 的第1步同样处理(把「WebSearch 搜首板溢价率/连板溢价率/大面股」改为 MCP 优先 + 禁止编造数字)。

3. 新增 `TRADING_PATTERNS_SKILL_META` 与 `TRADING_PATTERNS_SKILL_BODY`:

```python
TRADING_PATTERNS_SKILL_META = """name: trading-patterns
description: 短线核心战法库，含龙头首阴低吸、爆量涨停弱转强、首板一进二、打板接力、断板反包、龙回头、中军补涨七大超短战法。适用于用户问"XXX首阴能买吗"、"明天竞价怎么操作"、"哪些首板明天能二板"、"XXX断板了还能接吗"、"龙回头怎么低吸"等问题。"""

from config.ai_knowledge import TACTICS_FULL  # 与已有 import 合并，勿重复

TRADING_PATTERNS_SKILL_BODY = TACTICS_FULL + """

## 分析流程
### 第1步：获取数据
并行调用 MCP 工具：stock_realtime、stock_l2_dashboard、stock_large_orders、stock_timeshare、limit_up_themes。WebSearch 仅补该股最新消息与市场情绪。

### 第2步：判断适用战法
按用户问题与个股状态对应到上述七大战法之一。

### 第3步：按战法框架分析
纯文本输出（发微信用，不要 markdown）：

【{股票名}】{战法名}分析
一、战法条件检查（逐项打勾/打叉）
二、关键数据
三、情绪环境（情绪周期 + 该战法当前胜率评估）
四、操作计划（买点/仓位/止损/目标）
五、风险提示

## 注意事项
- 退潮期原则上全部战法不做
- 总仓位控制在6成以内，止损是铁律
- 龙头地位是前提，跟风股套用龙头战法必亏
"""
```

4. `AGENT_SKILLS` 字典加第 4 条:

```python
"trading-patterns": {
    "meta": TRADING_PATTERNS_SKILL_META,
    "body": TRADING_PATTERNS_SKILL_BODY,
    "path": "skills/trading-patterns.md",
},
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py::AgentSkillsTest -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add backend/config/ai_prompts.py backend/tests/test_ai_knowledge.py
git commit -m "feat: trading-patterns 纳入 AGENT_SKILLS，skill 数据获取改 MCP 优先"
```

---

## Task 6: 生成 skills/*.md 四个技能文件

**Files:**
- Modify(生成): `skills/stock-analysis.md`、`skills/market-sentiment.md`、`skills/board-hitting.md`、`skills/trading-patterns.md`

- [ ] **Step 1: 跑同步脚本**

Run: `cd backend && venv/bin/python config/sync_skills.py`
Expected: 输出 4 行 `updated skills/...` + `done`

- [ ] **Step 2: 人工核对生成结果**

Run: `cd /Users/mac/Github/NiuNIuNiu && git diff --stat skills/`
检查:四个 `.md` 均被更新;`trading-patterns.md` 含 7 个战法标题与「没有永恒有效的战法」前言;无 `<...>` 占位符残留。

Run: `grep -c "###" skills/trading-patterns.md`
Expected: ≥7(七个战法各一个三级标题)

Run: `grep -rn "5-7成" skills/`
Expected: 无输出(旧仓位口径已清除)

- [ ] **Step 3: 提交**

```bash
git add skills/stock-analysis.md skills/market-sentiment.md skills/board-hitting.md skills/trading-patterns.md
git commit -m "chore: 重新生成 skills/*.md（含 7 战法战法库）"
```

---

## Task 7: 诊股报告补字段 + token 入环境变量

**Files:**
- Modify: `backend/services/ai_diagnosis_service.py`
- Test: `backend/tests/test_ai_diagnosis.py`

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_ai_diagnosis.py` 末尾追加新测试类:

```python
class NormalizeReportFieldsTest(unittest.TestCase):
    def test_normalize_report_has_tactic_fields(self):
        from services.ai_diagnosis_service import _normalize_report
        rep = _normalize_report({})
        self.assertIn("applicable_tactic", rep)
        self.assertIn("tactic_fit", rep)
        self.assertEqual(rep["applicable_tactic"], "待观察")
        self.assertEqual(rep["tactic_fit"], "")

    def test_normalize_report_keeps_ai_tactic(self):
        from services.ai_diagnosis_service import _normalize_report
        rep = _normalize_report({"applicable_tactic": "龙回头", "tactic_fit": "回踩10日线缩量"})
        self.assertEqual(rep["applicable_tactic"], "龙回头")
        self.assertEqual(rep["tactic_fit"], "回踩10日线缩量")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_diagnosis.py::NormalizeReportFieldsTest -q`
Expected: FAIL — 返回 dict 无 `applicable_tactic` 键。

- [ ] **Step 3: 改 _normalize_report**

在 `backend/services/ai_diagnosis_service.py` 的 `_normalize_report()` 返回的 dict 中,`theme_position` 之后加两行:

```python
        "applicable_tactic": raw.get("applicable_tactic") or "待观察",
        "tactic_fit": raw.get("tactic_fit") or "",
```

- [ ] **Step 4: 改 _STOCKAPI_TOKEN 为环境变量**

`ai_diagnosis_service.py` 顶部 `import os` 已存在。把:

```python
_STOCKAPI_TOKEN = "c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e"
```

改为:

```python
_STOCKAPI_TOKEN = os.getenv("STOCKAPI_TOKEN", "c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e")
```

(保留旧值为 fallback,避免线上环境变量未配置时立即失效。)

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_diagnosis.py -q`
Expected: PASS(新增 2 项通过,原有项不回归)

- [ ] **Step 6: 提交**

```bash
git add backend/services/ai_diagnosis_service.py backend/tests/test_ai_diagnosis.py
git commit -m "feat: 诊股报告补战法适配字段，STOCKAPI token 改读环境变量"
```

---

## Task 8: .gitignore 与集成验证

**Files:**
- Modify: `.gitignore`
- Modify: `backend/.env`(若存在;不存在则跳过并在收尾说明)

- [ ] **Step 1: .gitignore 加日志规则**

读取 `/Users/mac/Github/NiuNIuNiu/.gitignore`,在末尾追加(若已含 `*.log` 则跳过):

```
# 运行日志
*.log
```

- [ ] **Step 2: backend/.env 增加 STOCKAPI_TOKEN**

读取 `backend/.env`(若文件存在),追加一行:

```
STOCKAPI_TOKEN=c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e
```

若 `backend/.env` 不存在,跳过此步并在收尾告知用户手动添加。

- [ ] **Step 3: 全量集成验证**

Run: `cd backend && venv/bin/python -c "import config.ai_knowledge, config.ai_prompts; from config.ai_prompts import AGENT_SKILLS; print('imports ok,', len(AGENT_SKILLS), 'skills')"`
Expected: `imports ok, 4 skills`

Run: `cd backend && venv/bin/python -m pytest tests/test_ai_knowledge.py tests/test_ai_diagnosis.py tests/test_emotion_cycle.py -q`
Expected: 全 PASS(`test_emotion_cycle.py` 与改动前一致)

- [ ] **Step 4: 重启后端冒烟(可选,需后端环境)**

Run: `cd /Users/mac/Github/NiuNIuNiu && bash start.sh`
然后人工触发一次 AI 诊股与一次情绪周期分析,确认返回 JSON 可解析、`applicable_tactic`/`tactic_fit` 字段出现。若无法在当前环境跑后端,如实说明跳过。

- [ ] **Step 5: 提交**

```bash
git add .gitignore
git commit -m "chore: 运行日志加入 .gitignore"
```

(`backend/.env` 通常已被 gitignore,不提交。)

---

## 收尾

所有任务完成后:
- 确认 `git status` 干净
- 向用户汇报:`ai_prompts.py` 行数变化、战法从 3→7、新增字段、跳过的步骤(如后端冒烟)
- 提示:若 `backend/.env` 不存在需手动加 `STOCKAPI_TOKEN`;线上部署不涉及新迁移文件,无需改 `deploy.yml`
