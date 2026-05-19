"""AI 中转 API 客户端（Anthropic /v1/messages 或 OpenAI 兼容格式）"""
import json
import logging
import os
import subprocess
import tempfile

from config.ai_accounts import get_active_account

logger = logging.getLogger(__name__)


def get_claude_api_key() -> str:
    """当前激活账号的 API Key"""
    return get_active_account().resolve_api_key()


def refresh_client_credentials() -> None:
    """切换账号后调用（兼容旧代码，现为 no-op）"""
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
                if block.get("type") == "thinking":
                    continue
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        joined = "".join(parts).strip()
        if joined:
            return joined

    message = (body.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return ""


def call_claude(
    user_content: str,
    *,
    max_tokens: int = 4096,
    model: str | None = None,
    curl_timeout: int = 90,
    proc_timeout=None,
    raise_on_error: bool = False,
) -> str:
    """调用当前 AI 账号，返回助手回复文本"""
    if proc_timeout is None:
        proc_timeout = curl_timeout + 5

    account = get_active_account()
    api_key = account.resolve_api_key()
    use_model = model or account.models.get("haiku", "")

    if not api_key:
        msg = f"AI 账号 {account.id} 未配置密钥（{account.key_env}）"
        if raise_on_error:
            raise RuntimeError(msg)
        logger.error(msg)
        return ""

    payload = json.dumps({
        "model": use_model,
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": max_tokens,
    })
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(payload)
        payload_file = f.name
    try:
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
            msg = f"curl 失败 (exit {proc.returncode}): {(proc.stderr or '')[:500]}"
            if raise_on_error:
                raise RuntimeError(msg)
            logger.error(msg)
            return ""
        if not (proc.stdout or "").strip():
            msg = "AI API 返回空响应"
            if raise_on_error:
                raise RuntimeError(msg)
            logger.error(msg)
            return ""
        body = json.loads(proc.stdout)
        if "error" in body:
            msg = f"AI API 错误: {body['error']}"
            if raise_on_error:
                raise RuntimeError(msg)
            logger.error(msg)
            return ""
        return extract_claude_text(body)
    except subprocess.TimeoutExpired:
        msg = f"AI API 调用超时({curl_timeout}s)"
        if raise_on_error:
            raise RuntimeError(msg)
        logger.error(msg)
        return ""
    except json.JSONDecodeError as e:
        msg = f"AI 响应非 JSON: {e}"
        if raise_on_error:
            raise RuntimeError(msg)
        logger.error(msg)
        return ""
    finally:
        try:
            os.unlink(payload_file)
        except OSError:
            pass


def call_claude_for_scenario(
    scenario: str,
    user_content: str,
    *,
    raise_on_error: bool = False,
    **kwargs,
) -> str:
    """按 config/ai_config.py 中的场景配置调用 AI"""
    from config.ai_config import get_scenario

    cfg = get_scenario(scenario)
    return call_claude(
        user_content,
        max_tokens=kwargs.get("max_tokens", cfg.max_tokens),
        model=kwargs.get("model", cfg.model),
        curl_timeout=kwargs.get("curl_timeout", cfg.curl_timeout),
        proc_timeout=kwargs.get("proc_timeout", cfg.proc_timeout_resolved),
        raise_on_error=raise_on_error,
    )
