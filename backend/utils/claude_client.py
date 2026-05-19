"""AnyRouter 中转站 Claude API 客户端（Anthropic /v1/messages 格式）"""
import json
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

CLAUDE_API_URL = os.environ.get(
    "CLAUDE_API_URL",
    "https://a-ocnfniawgw.cn-shanghai.fcapp.run/v1/messages",
)
CLAUDE_API_KEY = os.environ.get(
    "CLAUDE_API_KEY",
    "sk-SE4nYndjR8x28mpxC0A7ybImSvpVa3fICo1WMVAV4Hkplb4D",
)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


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
    """调用 Claude API，返回助手回复文本"""
    if proc_timeout is None:
        proc_timeout = curl_timeout + 5
    use_model = model or CLAUDE_MODEL

    if not CLAUDE_API_KEY:
        msg = "CLAUDE_API_KEY 未配置"
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
                CLAUDE_API_URL,
                "-H", f"Authorization: Bearer {CLAUDE_API_KEY}",
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
            msg = "Claude API 返回空响应"
            if raise_on_error:
                raise RuntimeError(msg)
            logger.error(msg)
            return ""
        body = json.loads(proc.stdout)
        if "error" in body:
            msg = f"Claude API 错误: {body['error']}"
            if raise_on_error:
                raise RuntimeError(msg)
            logger.error(msg)
            return ""
        return extract_claude_text(body)
    except subprocess.TimeoutExpired:
        msg = f"Claude API 调用超时({curl_timeout}s)"
        if raise_on_error:
            raise RuntimeError(msg)
        logger.error(msg)
        return ""
    except json.JSONDecodeError as e:
        msg = f"Claude 响应非 JSON: {e}"
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
    """按 config/ai_config.py 中的场景配置调用 Claude"""
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
