"""AI 中转 API 客户端（Anthropic /v1/messages 或 OpenAI 兼容格式）"""
import json
import logging
import os
import subprocess
import tempfile

from config.ai_accounts import ACCOUNTS, AiAccount, get_active_account

logger = logging.getLogger(__name__)

_last_api_error: str = ""


def get_last_api_error() -> str:
    return _last_api_error


def _set_last_error(msg: str) -> None:
    global _last_api_error
    _last_api_error = msg or ""


def get_claude_api_key() -> str:
    return get_active_account().resolve_api_key()


def refresh_client_credentials() -> None:
    return None


def extract_claude_text(body: dict) -> str:
    """从 Anthropic messages 或 OpenAI chat/completions 响应提取文本"""
    if not isinstance(body, dict):
        return ""

    if "error" in body:
        return ""

    content_blocks = body.get("content")
    if isinstance(content_blocks, list):
        parts = []
        for block in content_blocks:
            if isinstance(block, dict):
                btype = block.get("type") or ""
                if btype in ("thinking", "redacted_thinking"):
                    continue
                parts.append(
                    block.get("text")
                    or block.get("content")
                    or block.get("output_text")
                    or ""
                )
            elif isinstance(block, str):
                parts.append(block)
        joined = "".join(parts).strip()
        if joined:
            return joined

    message = (body.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()

    # 部分 GPT 通道直接给 output_text
    if body.get("output_text"):
        return str(body["output_text"]).strip()
    return ""


def _invoke_account(
    account: AiAccount,
    user_content: str,
    *,
    model: str,
    max_tokens: int,
    curl_timeout: int,
    proc_timeout: int,
    raise_on_error: bool,
) -> str:
    api_key = account.resolve_api_key()
    if not api_key:
        msg = f"AI 账号 {account.id} 未配置密钥（{account.key_env}）"
        _set_last_error(msg)
        if raise_on_error:
            raise RuntimeError(msg)
        logger.error(msg)
        return ""

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": max_tokens,
    })
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(payload)
        payload_file = f.name
    try:
        logger.info(
            "AI 调用 account=%s model=%s timeout=%ss prompt_len=%s",
            account.id, model, curl_timeout, len(user_content),
        )
        proc = subprocess.run(
            [
                "curl", "-s", "--max-time", str(curl_timeout),
                account.api_url,
                "-H", f"Authorization: Bearer {api_key}",
                "-H", "Content-Type: application/json",
                "-H", "anthropic-version: 2023-06-01",
                "-d", f"@{payload_file}",
            ],
            capture_output=True, text=True, timeout=proc_timeout,
        )
        if proc.returncode != 0:
            msg = f"[{account.id}/{model}] curl 失败 (exit {proc.returncode}): {(proc.stderr or '')[:300]}"
            _set_last_error(msg)
            if raise_on_error:
                raise RuntimeError(msg)
            logger.error(msg)
            return ""
        if not (proc.stdout or "").strip():
            msg = f"[{account.id}/{model}] API 返回空响应"
            _set_last_error(msg)
            if raise_on_error:
                raise RuntimeError(msg)
            logger.error(msg)
            return ""
        body = json.loads(proc.stdout)
        if "error" in body:
            err = body["error"]
            err_msg = err.get("message") if isinstance(err, dict) else str(err)
            msg = f"[{account.id}/{model}] API 错误: {err_msg or err}"
            _set_last_error(msg)
            if raise_on_error:
                raise RuntimeError(msg)
            logger.error(msg)
            return ""
        text = extract_claude_text(body)
        if not text:
            msg = f"[{account.id}/{model}] 响应无文本内容: {(proc.stdout or '')[:200]}"
            _set_last_error(msg)
            if raise_on_error:
                raise RuntimeError(msg)
            logger.warning(msg)
            return ""
        _set_last_error("")
        return text
    except subprocess.TimeoutExpired:
        msg = f"[{account.id}/{model}] 调用超时({curl_timeout}s)"
        _set_last_error(msg)
        if raise_on_error:
            raise RuntimeError(msg)
        logger.error(msg)
        return ""
    except json.JSONDecodeError as e:
        msg = f"[{account.id}/{model}] 响应非 JSON: {e}"
        _set_last_error(msg)
        if raise_on_error:
            raise RuntimeError(msg)
        logger.error(msg)
        return ""
    finally:
        try:
            os.unlink(payload_file)
        except OSError:
            pass


def call_claude(
    user_content: str,
    *,
    max_tokens: int = 4096,
    model: str | None = None,
    account_id: str | None = None,
    curl_timeout: int = 90,
    proc_timeout=None,
    raise_on_error: bool = False,
) -> str:
    """调用 AI，返回助手回复文本"""
    if proc_timeout is None:
        proc_timeout = curl_timeout + 5
    account = ACCOUNTS[account_id] if account_id else get_active_account()
    use_model = model or account.models.get("haiku", "")
    return _invoke_account(
        account,
        user_content,
        model=use_model,
        max_tokens=max_tokens,
        curl_timeout=curl_timeout,
        proc_timeout=proc_timeout,
        raise_on_error=raise_on_error,
    )


def call_claude_for_scenario(
    scenario: str,
    user_content: str,
    *,
    raise_on_error: bool = False,
    account_id: str | None = None,
    **kwargs,
) -> str:
    from config.ai_config import get_scenario, _SCENARIO_TEMPLATES

    cfg = get_scenario(scenario)
    if account_id:
        tier = _SCENARIO_TEMPLATES.get(scenario, ("haiku",))[0]
        model = kwargs.get("model") or ACCOUNTS[account_id].models.get(tier, tier)
    else:
        model = kwargs.get("model", cfg.model)

    return call_claude(
        user_content,
        max_tokens=kwargs.get("max_tokens", cfg.max_tokens),
        model=model,
        account_id=account_id,
        curl_timeout=kwargs.get("curl_timeout", cfg.curl_timeout),
        proc_timeout=kwargs.get("proc_timeout", cfg.curl_timeout + 5),
        raise_on_error=raise_on_error,
    )
