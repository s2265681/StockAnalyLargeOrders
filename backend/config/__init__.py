"""AI 配置与提示词统一入口"""
from config.ai_accounts import (
    ACCOUNTS,
    get_active_account,
    get_active_account_id,
    list_accounts_public,
    set_active_account_id,
)
from config.ai_config import GENERAL_BROAD_TAGS_ORDERED, get_scenario

__all__ = [
    "ACCOUNTS",
    "get_active_account",
    "get_active_account_id",
    "list_accounts_public",
    "set_active_account_id",
    "GENERAL_BROAD_TAGS_ORDERED",
    "get_scenario",
]
