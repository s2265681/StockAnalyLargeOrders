"""
AI 配置表 — 场景 → 模型档位 / token / 超时。

默认账号：kalowave（见 config/ai_accounts.py）

┌────────────────────────────┬────────┬─────────────────────────────┐
│ scenario                   │ 档位   │ kalowave 模型               │
├────────────────────────────┼────────┼─────────────────────────────┤
│ ai_diagnosis               │ opus   │ gpt-5.5  全面诊股           │
│ emotion_cycle_daily        │ opus   │ gpt-5.5  当天买卖分析       │
│ emotion_cycle_* (其余)     │ sonnet │ gpt-5.4  情绪周期研判       │
│ dragon_tiger               │ sonnet │ gpt-5.4  龙虎榜解读         │
│ ai_diagnosis_chat          │ sonnet │ gpt-5.4  诊股追问           │
│ limit_up_*                 │ haiku  │ claude-haiku  题材分组      │
└────────────────────────────┴────────┴─────────────────────────────┘
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config.ai_accounts import get_models_for_active_account

GENERAL_BROAD_TAGS_ORDERED = (
    "合成生物", "机器人", "低空经济", "算力/服务器", "算力/半导体产业化",
    "半导体产业链", "第三代半导体", "光通信", "PCB", "电力", "光伏",
    "锂电池", "医药", "房地产", "大消费", "教育", "文化传媒", "AI应用",
    "军工", "油气", "稀土永磁", "充电桩", "电子特气/化工", "氟化工",
    "猪肉", "并购重组", "体育产业", "其他概念",
)

_SCENARIO_TEMPLATES: dict[str, tuple[str, int, int, str]] = {
    "emotion_cycle_realtime": ("sonnet", 2048, 60, "盘中实时情绪分析"),
    "emotion_cycle_daily": ("opus", 8192, 150, "当天分析含买卖点"),
    "emotion_cycle_batch": ("sonnet", 16000, 180, "历史批量周期研判"),
    "emotion_cycle_single": ("sonnet", 4096, 120, "单日周期研判"),
    "limit_up_group": ("haiku", 8192, 90, "涨停梯队分组"),
    "limit_up_regroup": ("haiku", 4096, 90, "其他概念重分组"),
    "limit_up_split": ("haiku", 8192, 90, "过大标签拆分"),
    "limit_up_stock_theme": ("haiku", 256, 60, "单股题材"),
    "ai_diagnosis": ("opus", 4096, 120, "诊股报告"),
    "ai_diagnosis_chat": ("sonnet", 1024, 60, "诊股追问"),
    "dragon_tiger": ("sonnet", 2048, 90, "龙虎榜解读"),
}


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


def get_scenario(name: str) -> ScenarioConfig:
    if name not in _SCENARIO_TEMPLATES:
        raise KeyError(f"未知 AI 场景: {name}，可选: {', '.join(_SCENARIO_TEMPLATES)}")
    tier, max_tokens, curl_timeout, description = _SCENARIO_TEMPLATES[name]
    models = get_models_for_active_account()
    return ScenarioConfig(
        model=models.get(tier, tier),
        max_tokens=max_tokens,
        curl_timeout=curl_timeout,
        description=description,
    )
