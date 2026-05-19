"""
AI 多账号配置 — 通过 AI_ACCOUNT 或 POST /api/v1/ai-account 切换。

账号：
  anyrouter  — AnyRouter（Claude Haiku，大陆优化线）
  kalowave   — Kalowave GPT（gpt-5.5 / gpt-5.4）

密钥请写在 backend/.env（勿提交 git）：
  AI_ACCOUNT=anyrouter|kalowave
  AI_ACCOUNT_ANYROUTER_KEY=sk-...
  AI_ACCOUNT_KALOWAVE_KEY=sk-...
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_ACTIVE_FILE = _BACKEND_DIR / "data" / "ai_account.active"

DEFAULT_ACCOUNT_ID = "kalowave"
VALID_ACCOUNT_IDS = frozenset({"anyrouter", "kalowave"})


@dataclass(frozen=True)
class AiAccount:
    id: str
    label: str
    api_url: str
    key_env: str
    models: dict[str, str]
    description: str = ""

    def resolve_api_key(self) -> str:
        key = os.environ.get(self.key_env, "").strip()
        if key:
            return key
        # 兼容旧环境变量
        if self.id == "anyrouter":
            return os.environ.get("CLAUDE_API_KEY", "").strip()
        return ""


def _normalize_api_url(base: str, path: str = "/v1/messages") -> str:
    base = (base or "").rstrip("/")
    if base.endswith("/v1/messages") or base.endswith("/v1/chat/completions"):
        return base
    return f"{base}{path}"


ACCOUNTS: dict[str, AiAccount] = {
    "anyrouter": AiAccount(
        id="anyrouter",
        label="AnyRouter (Claude)",
        api_url=_normalize_api_url(
            os.environ.get(
                "AI_ACCOUNT_ANYROUTER_URL",
                "https://a-ocnfniawgw.cn-shanghai.fcapp.run",
            ),
        ),
        key_env="AI_ACCOUNT_ANYROUTER_KEY",
        models={
            "haiku": os.environ.get(
                "AI_ACCOUNT_ANYROUTER_HAIKU",
                "claude-haiku-4-5-20251001",
            ),
            "sonnet": os.environ.get(
                "AI_ACCOUNT_ANYROUTER_SONNET",
                os.environ.get("CLAUDE_MODEL_SONNET", "claude-haiku-4-5-20251001"),
            ),
            "opus": os.environ.get(
                "AI_ACCOUNT_ANYROUTER_OPUS",
                os.environ.get("CLAUDE_MODEL_OPUS", "claude-haiku-4-5-20251001"),
            ),
        },
        description="AnyRouter 大陆优化线；Sonnet/Opus 暂回退 Haiku",
    ),
    "kalowave": AiAccount(
        id="kalowave",
        label="Kalowave (GPT)",
        api_url=_normalize_api_url(
            os.environ.get("AI_ACCOUNT_KALOWAVE_URL", "https://token.kalowave.com"),
        ),
        key_env="AI_ACCOUNT_KALOWAVE_KEY",
        models={
            # 结构化 JSON（涨停分组/题材标签）：Haiku 快且稳
            "haiku": os.environ.get(
                "AI_ACCOUNT_KALOWAVE_HAIKU", "claude-haiku-4-5-20251001",
            ),
            # 情绪周期、龙虎榜、诊股追问
            "sonnet": os.environ.get("AI_ACCOUNT_KALOWAVE_SONNET", "gpt-5.4"),
            # 诊股报告、当天买卖分析
            "opus": os.environ.get("AI_ACCOUNT_KALOWAVE_OPUS", "gpt-5.5"),
        },
        description="Kalowave：分析 gpt-5.5 / 解读 gpt-5.4 / 打标签 haiku",
    ),
}


def _read_active_from_file() -> str | None:
    try:
        if not _ACTIVE_FILE.exists():
            return None
        data = json.loads(_ACTIVE_FILE.read_text(encoding="utf-8"))
        account_id = str(data.get("account", "")).strip()
        if account_id in VALID_ACCOUNT_IDS:
            return account_id
    except (OSError, json.JSONDecodeError, TypeError) as e:
        logger.warning("读取 AI 账号切换文件失败: %s", e)
    return None


def get_active_account_id() -> str:
    from_file = _read_active_from_file()
    if from_file:
        return from_file
    account_id = os.environ.get("AI_ACCOUNT", DEFAULT_ACCOUNT_ID).strip()
    if account_id in VALID_ACCOUNT_IDS:
        return account_id
    return DEFAULT_ACCOUNT_ID


def get_active_account() -> AiAccount:
    account_id = get_active_account_id()
    return ACCOUNTS[account_id]


def set_active_account_id(account_id: str) -> None:
    account_id = str(account_id).strip()
    if account_id not in VALID_ACCOUNT_IDS:
        raise ValueError(f"未知账号: {account_id}，可选: {', '.join(sorted(VALID_ACCOUNT_IDS))}")
    _ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ACTIVE_FILE.write_text(
        json.dumps({"account": account_id}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def list_accounts_public() -> list[dict]:
    active = get_active_account_id()
    out = []
    for account in ACCOUNTS.values():
        out.append({
            "id": account.id,
            "label": account.label,
            "description": account.description,
            "models": dict(account.models),
            "configured": bool(account.resolve_api_key()),
            "active": account.id == active,
        })
    return out


def get_models_for_active_account() -> dict[str, str]:
    return dict(get_active_account().models)
