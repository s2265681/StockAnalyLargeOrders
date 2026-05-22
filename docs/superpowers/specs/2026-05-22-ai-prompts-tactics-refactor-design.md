# AI 提示词重构 + 超短战法库扩展 设计文档

日期: 2026-05-22
状态: 已批准设计,待生成实现计划

## 背景与动机

`backend/config/ai_prompts.py` 已增长到 1027 行,存在以下问题:

1. **知识重复且开始漂移** — 「数据字段说明 / 六大情绪指标 / 情绪周期五阶段 / 三大战法」在 `SYSTEM_PROMPT`、`BATCH_ANALYSIS_PROMPT`、`SINGLE_DATE_ANALYSIS_PROMPT` 三处各抄一遍。已出现实际不一致:升温期仓位在后端 prompt 写「5-7成」,在 skill 写「6-8成」。
2. **skill 正文以 Python 三引号字符串塞进 `.py`** — 编辑体验差,diff 噪音大;`ai_prompts.py` 大半篇幅是 markdown 字符串。
3. **`trading-patterns.md` 脱管** — 不在 `AGENT_SKILLS` 字典里,`sync_skills.py` 不会同步它,而它是三大战法最详细的版本,导致战法知识散在 4 个文件无单一事实源。
4. **战法体系单薄** — 只有 3 个战法,未覆盖打板/接力、反包、龙回头、中军补涨等超短主流打法。
5. **诊股报告缺战法适配维度** — `DIAGNOSIS_REPORT_TEMPLATE` 做 8 维度分析却不含战法判定,报告无「适用哪个战法」。
6. **skill 让模型 WebSearch 搜本可结构化提供的数据** — `stock-analysis.md` 要求联网搜首板/连板溢价率,数字不可靠且慢。
7. **杂项** — `_STOCKAPI_TOKEN` 明文硬编码在 `ai_diagnosis_service.py`;根目录散落 `*.log` 未入 `.gitignore`。

## 目标

- 知识片段单一事实源,后端 prompt 与 skill 共用,改一处全生效。
- 战法库从 3 个扩展到 7 个超短核心战法。
- 战法分层:详版进独立战法库文档,精版进 API 提示词,控制 token。
- 诊股报告增加战法适配维度。
- 修掉仓位阈值不一致、token 硬编码、日志入库等杂项。

## 非目标

- 不新增 MCP 工具(避免范围扩散)。
- 不改数据库结构。
- 不改 AI 账号/模型/超时配置(`ai_config.py`、`ai_accounts.py` 不动)。
- 不做与本目标无关的重构。

## 战法库最终清单(7 个)

| # | 战法 | 来源 | 核心要点 |
|---|------|------|---------|
| 1 | 龙头首阴低吸 | 现有 | 龙头连涨后首根阴线低吸,跌幅 -3%~-7%,量不超前日 2 倍 |
| 2 | 爆量涨停 & 竞价弱转强 | 现有 | 龙头爆量封板 → 次日竞价高开弱转强确认 |
| 3 | 首板一进二 | 现有 | 强首板筛选(题材/封板质量/换手/市值)→ 次日做二板 |
| 4 | 打板/接力 | 新增 | 扫板/排板/回封板三手法;接力看地位(续命板/小龙头/总龙头);半路板列为高风险反面教材;不涨停不买 |
| 5 | 断板反包 | 新增 | 连板(≥3 板)断板后弱转强;断板需爆量大换手 + 分时进攻;含一字反包/N 字反包;11 点前未翻红时间止损 |
| 6 | 龙回头 | 新增 | 龙头回踩做第二波;放量拉升 + 缩量回踩;5/10/20 日线支撑;调整窗口 3-10 日(理想 5-7 日) |
| 7 | 中军补涨 | 新增 | 龙头休整时资金切向中军,承接人气补涨联动;中军需具一定体量与确定性 |

调研共识写入战法库前言:**没有永恒有效的战法,机械套形态会失效**。每个战法以「情绪环境 + 资金预期」为前置判断,而非纯形态匹配。

## 架构设计

### 新模块:`backend/config/ai_knowledge.py`

AI 知识唯一事实源,导出以下片段常量与组合:

```
FIELD_GUIDE: str          # 数据字段说明(date/rise_ratio/.../broken_board_count)
EMOTION_INDICATORS: str   # 六大情绪指标交叉验证
EMOTION_STAGES: str       # 情绪周期五阶段(内嵌统一仓位)
POSITION_TABLE: str       # 统一仓位表(见下)

TACTICS: dict[str, Tactic]  # 7 个战法
                            # Tactic 含 name / brief(一句话要点) / full(详细正文)
TACTICS_BRIEF: str          # 7 战法精版拼接 + 情绪适配表 → 用于 API 提示词
TACTICS_FULL: str           # 7 战法详版拼接 → 用于 trading-patterns.md
```

`Tactic` 用 `@dataclass(frozen=True)` 定义,字段 `name: str`、`brief: str`、`full: str`。

### 统一仓位表

| 阶段 | 总仓位 | 备注 |
|------|--------|------|
| 冰点期 | 0-1 成 | 空仓为主,板块集体抵抗可极轻仓试错龙头 |
| 修复期 | 2-3 成 | 小仓试错,锁先连板方向 |
| 升温期 | 6-8 成 | 加仓做龙头确认买点 + 补涨龙 |
| 高潮期 | 6-8 成 | 持股不加仓,逐步提高止盈标准 |
| 退潮期 | 0-2 成 | 减仓/空仓,绝不追高 |

单票上限 1-3 成;首板一进二/打板单票 ≤3 成。该表为全局唯一来源,后端 prompt 与 skill 均引用。

### `ai_prompts.py` 重构

各 prompt 改为「角色设定 + 片段拼接 + JSON schema」结构,不再内联重复段:

- `SYSTEM_PROMPT` = 角色 + `FIELD_GUIDE` + `EMOTION_INDICATORS` + `EMOTION_STAGES` + `TACTICS_BRIEF` + JSON schema
- `BATCH_ANALYSIS_PROMPT` = 同构,多日批量变体
- `SINGLE_DATE_ANALYSIS_PROMPT` = 保留 `{FIELD_GUIDE}` 占位符(由 `emotion_cycle.py:1384` 替换,现有逻辑不变)
- `DAILY_ANALYSIS_SYSTEM_PROMPT` / `INTRADAY_SYSTEM_PROMPT` = 引用 `TACTICS_BRIEF`
- `DIAGNOSIS_REPORT_TEMPLATE` = 嵌入 `TACTICS_BRIEF`,新增战法字段(见下)

所有对外 prompt 变量名保持不变,`emotion_cycle.py`、`dragon_tiger_service.py` 等导入方零改动。预计 `ai_prompts.py` 由 1027 行降至 ~350 行。

### skill 生成

`AGENT_SKILLS` 字典纳入第 4 个条目 `trading-patterns`。`STOCK_ANALYSIS_SKILL_BODY` 等改为由片段组合的函数(如 `build_stock_analysis_skill()`)。`sync_skills.py` 逻辑不变(由 `AGENT_SKILLS` 驱动),自动生成/覆盖 4 个 `skills/*.md`:

- `stock-analysis.md`
- `market-sentiment.md`
- `board-hitting.md`
- `trading-patterns.md`(战法库详版,由 `TACTICS_FULL` 生成)

### 诊股报告新增战法维度

`DIAGNOSIS_REPORT_TEMPLATE` 嵌入 `TACTICS_BRIEF`,JSON 增加两个字段:

- `applicable_tactic`: 适用战法名;不适用则写「当前无适用战法」+ 原因
- `tactic_fit`: 战法适配说明(80 字内,讲清为何符合/不符合触发条件)

`ai_diagnosis_service.py` 的 `_normalize_report()` 同步补这两个字段的兜底默认值,保证前端可渲染(`applicable_tactic` 缺省「待观察」,`tactic_fit` 缺省空串)。

### skill 数据获取调整

`stock-analysis.md` / `market-sentiment.md` / `board-hitting.md` 第 1 步措辞调整:

- 结构化数据优先用 MCP 工具(`limit_up_themes`、`stock_l2_dashboard` 等)
- WebSearch 仅用于最新消息、政策催化等增量信息
- 溢价率等无实时数据源的指标,做定性判断,**禁止编造精确数字**

### 杂项修复

- `ai_diagnosis_service.py` 的 `_STOCKAPI_TOKEN` 改为读环境变量(`os.getenv("STOCKAPI_TOKEN", <旧值兜底>)`),旧值作为 fallback 避免线上立即失效;同步在 `backend/.env` 增加 `STOCKAPI_TOKEN`。
- `.gitignore` 增加 `*.log`。

## 数据流

```
ai_knowledge.py (片段单一事实源)
   │
   ├─→ ai_prompts.py 各 prompt (拼 BRIEF 版战法 + 片段)
   │      └─→ 后端 AI 调用 (诊股/情绪周期/龙虎榜)
   │
   └─→ AGENT_SKILLS → sync_skills.py
          └─→ skills/*.md ×4 (trading-patterns 用 FULL 版战法)
                 └─→ Claude Code / 微信 agent 读取
```

## 错误处理

- 重构为纯字符串组合,无新增运行时失败点。
- `ai_knowledge.py` 仅含模块级常量与 dataclass,导入即失败可在 CI/启动时立即发现。
- 诊股新增字段走 `_normalize_report` 兜底,AI 不返回也不影响渲染。

## 测试与验证

1. `cd backend && python -c "import config.ai_knowledge, config.ai_prompts"` — 导入无报错
2. `python backend/config/sync_skills.py` — 生成 4 个 skill,`git diff skills/` 人工核对内容正确、无占位符残留
3. 重启后端,跑一次 AI 诊股 + 一次情绪周期分析,确认返回 JSON 可解析、`applicable_tactic` / `tactic_fit` 字段出现
4. 全程不改数据库结构,纯提示词层改动,可整体回滚

## 风险

- 提示词内容变化可能影响 AI 输出风格/质量 — 属预期内的有意改动(仓位统一、战法扩展)。
- `TACTICS_BRIEF` 进入诊股 prompt 会增加其体积 — 精版战法刻意压缩,诊股走 opus / 4096 tokens,余量充足。

## 实现顺序建议

1. 新建 `ai_knowledge.py`(片段 + 7 战法)
2. 重构 `ai_prompts.py`(拼片段、纳入 trading-patterns、诊股加字段)
3. 跑 `sync_skills.py` 生成 4 个 `skills/*.md`
4. 改 `ai_diagnosis_service.py`(`_normalize_report` 补字段、token 入 env)
5. 改 `.gitignore`、`backend/.env`
6. 验证(导入 / sync / 重启冒烟)
