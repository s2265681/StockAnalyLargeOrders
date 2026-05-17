"""定时任务失败邮件告警（SMTP 配置见 backend/.env）。"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_ALERT_EMAIL = "rock.shang@kalowave.com"


def _smtp_config() -> dict | None:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", os.getenv("SMTP_PASSWORD", "")).strip()
    if not host or not user or not password:
        return None
    port = int(os.getenv("SMTP_PORT", "465"))
    use_ssl = os.getenv("SMTP_SSL", "1").lower() in ("1", "true", "yes")
    sender = os.getenv("SMTP_FROM", user).strip()
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "use_ssl": use_ssl,
        "sender": sender,
    }


def send_job_alert(
    job_name: str,
    *,
    exit_code: int = 1,
    detail: str = "",
    log_tail: str = "",
) -> bool:
    """发送任务失败邮件，未配置 SMTP 时仅打日志。成功发送返回 True。"""
    cfg = _smtp_config()
    to_addr = os.getenv("JOB_ALERT_EMAIL", DEFAULT_ALERT_EMAIL).strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[NiuNIuNiu] 定时任务失败: {job_name} (exit={exit_code})"
    body_parts = [
        f"任务: {job_name}",
        f"时间: {now}",
        f"退出码: {exit_code}",
    ]
    if detail:
        body_parts.append(f"\n详情:\n{detail}")
    if log_tail:
        body_parts.append(f"\n日志末尾:\n{log_tail}")

    body = "\n".join(body_parts)

    if not cfg:
        logger.warning(
            "未配置 SMTP（SMTP_HOST/SMTP_USER/SMTP_PASS），跳过邮件: %s",
            subject,
        )
        return False

    msg = MIMEMultipart()
    msg["From"] = cfg["sender"]
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        if cfg["use_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context) as smtp:
                smtp.login(cfg["user"], cfg["password"])
                smtp.sendmail(cfg["sender"], [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"]) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(cfg["user"], cfg["password"])
                smtp.sendmail(cfg["sender"], [to_addr], msg.as_string())
        logger.info("已发送任务失败邮件 -> %s [%s]", to_addr, job_name)
        return True
    except Exception as e:
        logger.error("发送任务失败邮件异常: %s", e)
        return False


def tail_log_file(path: str, lines: int = 40) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.readlines()
        return "".join(content[-lines:])
    except OSError:
        return ""
