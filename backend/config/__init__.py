"""AI 配置与提示词统一入口"""
from config.ai_config import DEFAULT_MODEL, GENERAL_BROAD_TAGS_ORDERED, MODELS, SCENARIOS, get_scenario

__all__ = [
    "DEFAULT_MODEL",
    "MODELS",
    "SCENARIOS",
    "get_scenario",
    "GENERAL_BROAD_TAGS_ORDERED",
]
