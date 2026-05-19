"""
AI 配置表 — 修改模型、token、超时请改本文件。

环境变量（可选，覆盖默认模型）：
  CLAUDE_MODEL              全局默认模型
  CLAUDE_API_URL / CLAUDE_API_KEY  见 utils/claude_client.py

┌─────────────────────────────┬──────────────────┬───────────┬─────────┬────────────────────────────┐
│ scenario                    │ 模型档位          │ max_tokens│ timeout │ 说明                        │
├─────────────────────────────┼──────────────────┼───────────┼─────────┼────────────────────────────┤
│ emotion_cycle_realtime      │ sonnet           │ 2048      │ 60s     │ 盘中实时情绪 POST           │
│ emotion_cycle_daily         │ opus             │ 8192      │ 150s    │ 当天分析（买卖点/复盘）★    │
│ emotion_cycle_batch         │ sonnet           │ 16000     │ 180s    │ 历史批量周期研判             │
│ emotion_cycle_single        │ sonnet           │ 4096      │ 120s    │ 单日周期研判（带上下文）     │
│ limit_up_group              │ haiku            │ 8192      │ 90s     │ 涨停梯队题材分组（结构化）   │
│ limit_up_regroup            │ haiku            │ 4096      │ 90s     │ 「其他概念」重分组           │
│ limit_up_split              │ haiku            │ 8192      │ 90s     │ 过大标签拆分                 │
│ limit_up_stock_theme        │ haiku            │ 256       │ 60s     │ 单股题材标签                 │
│ ai_diagnosis                │ opus             │ 4096      │ 120s    │ 诊股 JSON 报告 ★             │
│ ai_diagnosis_chat           │ sonnet           │ 1024      │ 60s     │ 诊股追问对话                 │
│ dragon_tiger                │ sonnet           │ 2048      │ 90s     │ 龙虎榜席位解读               │
│ cursor_stock_analysis       │ (Cursor 本地)    │ —         │ —       │ 见 ai_prompts 技能区         │
│ cursor_market_sentiment     │ (Cursor 本地)    │ —         │ —       │ 见 ai_prompts 技能区         │
│ cursor_board_hitting        │ (Cursor 本地)    │ —         │ —       │ 见 ai_prompts 技能区         │
└─────────────────────────────┴──────────────────┴───────────┴─────────┴────────────────────────────┘

模型档位说明：
  haiku  — 快、便宜：题材标签、梯队 JSON 分组等结构化任务
  sonnet — 均衡：盘中情绪、批量周期、龙虎榜解读、诊股追问
  opus   — 最强：当天分析（买卖点/复盘）、全面诊股报告
  可在 MODELS 中改成你中转站实际支持的模型 ID
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# 中转站模型 ID（按实际可用名称修改）
MODELS = {
    "haiku": os.environ.get("CLAUDE_MODEL_HAIKU", "claude-haiku-4-5-20251001"),
    "sonnet": os.environ.get("CLAUDE_MODEL_SONNET", "claude-sonnet-4-6"),
    "opus": os.environ.get("CLAUDE_MODEL_OPUS", "claude-opus-4-6"),
}

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", MODELS["haiku"])

# 涨停梯队「通用大类」白名单（题材分组 prompt 注入）
GENERAL_BROAD_TAGS_ORDERED = (
    "合成生物", "机器人", "低空经济", "算力/服务器", "算力/半导体产业化",
    "半导体产业链", "第三代半导体", "光通信", "PCB", "电力", "光伏",
    "锂电池", "医药", "房地产", "大消费", "教育", "文化传媒", "AI应用",
    "军工", "油气", "稀土永磁", "充电桩", "电子特气/化工", "氟化工",
    "猪肉", "并购重组", "体育产业", "其他概念",
)


@dataclass(frozen=True)
class ScenarioConfig:
    model: str
    max_tokens: int
    curl_timeout: int
    proc_timeout: Optional[int] = None
    description: str = ""

    @property
    def proc_timeout_resolved(self) -> int:
        return self.proc_timeout if self.proc_timeout is not None else self.curl_timeout + 5


def _cfg(model_tier: str, max_tokens: int, curl_timeout: int, description: str) -> ScenarioConfig:
    return ScenarioConfig(
        model=MODELS.get(model_tier, model_tier),
        max_tokens=max_tokens,
        curl_timeout=curl_timeout,
        description=description,
    )


SCENARIOS: dict[str, ScenarioConfig] = {
    "emotion_cycle_realtime": _cfg("sonnet", 2048, 60, "盘中实时情绪分析"),
    "emotion_cycle_daily": _cfg("opus", 8192, 150, "当天分析含买卖点"),
    "emotion_cycle_batch": _cfg("sonnet", 16000, 180, "历史批量周期研判"),
    "emotion_cycle_single": _cfg("sonnet", 4096, 120, "单日周期研判"),
    "limit_up_group": _cfg("haiku", 8192, 90, "涨停梯队分组"),
    "limit_up_regroup": _cfg("haiku", 4096, 90, "其他概念重分组"),
    "limit_up_split": _cfg("haiku", 8192, 90, "过大标签拆分"),
    "limit_up_stock_theme": _cfg("haiku", 256, 60, "单股题材"),
    "ai_diagnosis": _cfg("opus", 4096, 120, "诊股报告"),
    "ai_diagnosis_chat": _cfg("sonnet", 1024, 60, "诊股追问"),
    "dragon_tiger": _cfg("sonnet", 2048, 90, "龙虎榜解读"),
}


def get_scenario(name: str) -> ScenarioConfig:
    if name not in SCENARIOS:
        raise KeyError(f"未知 AI 场景: {name}，可选: {', '.join(SCENARIOS)}")
    return SCENARIOS[name]
