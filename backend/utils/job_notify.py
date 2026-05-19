"""定时任务邮件告警（SMTP 配置见 backend/.env）。"""
from __future__ import annotations

import ast
import logging
import os
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_ALERT_EMAIL = "s2265681@163.com"
_ENV_LOADED = False

# 任务展示名（邮件正文）
JOB_LABELS: dict[str, str] = {
    "intraday": "盘中刷新（梯队 + 情绪周期 + 买卖指导）",
    "dragon_tiger": "龙虎榜 AI 补全",
    "auction_grab": "竞价抢筹同步",
    "echelon_intraday": "涨停梯队盘中刷新",
    "unknown": "未知任务",
}

# 从日志中提取「有用行」的关键词
_USEFUL_KEYWORDS = (
    "结果",
    "补全",
    "入库",
    "梯队",
    "情绪",
    "买卖",
    "竞价",
    "早盘",
    "尾盘",
    "龙虎榜",
    "sync",
    "saved",
    "skipped",
    "failed",
    "完成",
    "失败",
    "异常",
    "ERROR",
    "WARNING",
    "条",
    "date=",
    "period=",
    "退出码",
    "休市",
    "跳过",
)

_LOG_MSG_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d+)?\s+\[\w+\]\s+\S+:\s*(.+)$"
)
_BANNER_RE = re.compile(r"^=+\s*.+\s*=+$")


def _load_backend_env() -> None:
    """加载 backend/.env（手动执行 notify 脚本时与 cron 的 source .env 一致）。"""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(backend_dir, ".env")
    if not os.path.isfile(env_path):
        _ENV_LOADED = True
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError as e:
        logger.warning("读取 .env 失败: %s", e)
    _ENV_LOADED = True


def _smtp_config() -> dict | None:
    _load_backend_env()
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


def notify_on_success_enabled() -> bool:
    _load_backend_env()
    return os.getenv("JOB_NOTIFY_ON_SUCCESS", "1").lower() in ("1", "true", "yes")


def job_display_name(job_name: str) -> str:
    return JOB_LABELS.get(job_name, job_name)


def format_duration(seconds: int | None) -> str:
    """将秒数格式化为可读耗时。"""
    if seconds is None:
        return "—"
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds} 秒"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} 分 {secs} 秒" if secs else f"{minutes} 分"
    hours, minutes = divmod(minutes, 60)
    if minutes:
        return f"{hours} 小时 {minutes} 分"
    return f"{hours} 小时"


def _strip_log_prefix(line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    m = _LOG_MSG_RE.match(line)
    if m:
        return m.group(1).strip()
    if "] " in line and ": " in line:
        _, _, msg = line.partition(": ")
        if msg:
            return msg.strip()
    return line


def extract_core_log_lines(log_text: str, max_lines: int = 12) -> str:
    """从日志末尾提取与业务相关的核心行（去掉时间戳等噪音）。"""
    if not log_text or not log_text.strip():
        return ""

    useful: list[str] = []
    seen: set[str] = set()
    for raw in log_text.strip().splitlines():
        msg = _strip_log_prefix(raw)
        if not msg or msg in seen:
            continue
        # 跳过 ===== 开始/完成 ===== 类横幅行
        if _BANNER_RE.match(msg):
            continue
        if msg.replace("=", "").strip() == "":
            continue
        if any(kw in msg for kw in _USEFUL_KEYWORDS):
            seen.add(msg)
            useful.append(msg)

    if not useful:
        fallback: list[str] = []
        for raw in log_text.strip().splitlines()[-max_lines:]:
            msg = _strip_log_prefix(raw)
            if msg and msg not in seen:
                seen.add(msg)
                fallback.append(msg)
        useful = fallback

    return "\n".join(useful[-max_lines:])


def _fmt_compact_date(d: str) -> str:
    if len(d) == 8 and d.isdigit():
        return f"{int(d[4:6])}月{int(d[6:8])}日"
    return d


def _try_parse_dict_suffix(text: str) -> dict | None:
    """解析日志里 `前缀: {...}` 或 `result={...}` 形式的 dict。"""
    for sep in (": ", "=", " result="):
        if sep in text:
            _, _, tail = text.partition(sep) if sep != " result=" else text.partition("result=")
            tail = tail.strip()
            if tail.startswith("{") and tail.endswith("}"):
                try:
                    val = ast.literal_eval(tail)
                    if isinstance(val, dict):
                        return val
                except (SyntaxError, ValueError):
                    pass
    if text.strip().startswith("{") and text.strip().endswith("}"):
        try:
            val = ast.literal_eval(text.strip())
            if isinstance(val, dict):
                return val
        except (SyntaxError, ValueError):
            pass
    return None


def _condense_point(msg: str) -> str:
    """将单条日志消息压缩为简短要点。"""
    msg = msg.strip()
    if not msg:
        return ""

    # date=20260519 result={...}
    m = re.match(r"date=(\d{8})\s+result=(\{.+})$", msg)
    if m:
        d, data = m.group(1), _try_parse_dict_suffix(m.group(2)) or {}
        if "saved" in data or "total" in data:
            return (
                f"{_fmt_compact_date(d)} AI共{data.get('total', 0)}只"
                f"/新{data.get('saved', 0)}"
                f"/跳{data.get('skipped', 0)}"
                f"/败{data.get('failed', 0)}"
            )
        if "stocks" in data:
            src = data.get("source", "")
            return f"{_fmt_compact_date(d)} 榜单{data.get('stocks', 0)}只({src})"

    data = _try_parse_dict_suffix(msg)
    if data:
        if "saved" in data or "total" in data:
            return (
                f"AI共{data.get('total', 0)}只"
                f"/新{data.get('saved', 0)}"
                f"/跳{data.get('skipped', 0)}"
                f"/败{data.get('failed', 0)}"
            )
        if "stocks" in data:
            return f"同步{data.get('stocks', 0)}只席位{data.get('seats', '')}"

    m = re.match(r"(早盘|尾盘)\s+period=\d+\s+入库\s+(\d+)\s*条", msg)
    if m:
        return f"{m.group(1)}{m.group(2)}条"

    m = re.match(r"(涨停梯队|情绪周期研判|盘中买卖指导):\s*(.+)", msg)
    if m:
        label, val = m.group(1), m.group(2).strip()
        short = {"涨停梯队": "梯队", "情绪周期研判": "情绪", "盘中买卖指导": "买卖"}.get(
            label, label
        )
        mark = "✓" if val.lower() in ("ok", "saved", "skipped") else val
        return f"{short}{mark}"

    if "failed=" in msg and "近" in msg:
        m = re.search(r"failed=(\d+)", msg)
        if m:
            return f"近5日补全失败{m.group(1)}项"

    if msg.startswith("未拉取到") or msg.startswith("未能解析"):
        return msg

    # 去掉冗长前缀
    for prefix in ("当日补全结果: ", "sync date=", "date="):
        if msg.startswith(prefix):
            return _condense_point(msg[len(prefix) :])

    if len(msg) > 80:
        return msg[:77] + "…"
    return msg


def distill_summary_points(
    detail: str = "",
    log_tail: str = "",
    max_points: int = 8,
) -> list[str]:
    """提炼核心要点列表（去重、压缩）。"""
    raw_lines: list[str] = []
    if detail and detail.strip() not in ("执行成功", ""):
        raw_lines.append(detail.strip())

    core = extract_core_log_lines(log_tail, max_lines=20)
    if core:
        raw_lines.extend(core.splitlines())

    points: list[str] = []
    seen: set[str] = set()
    for line in raw_lines:
        p = _condense_point(line)
        if p and p not in seen:
            seen.add(p)
            points.append(p)
    return points[-max_points:]


def build_job_email(
    job_name: str,
    *,
    success: bool,
    exit_code: int = 0,
    duration_secs: int | None = None,
    detail: str = "",
    log_tail: str = "",
) -> tuple[str, str]:
    """构建邮件主题与正文。返回 (subject, body)。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    label = job_display_name(job_name)
    status_icon = "成功" if success else "失败"
    status_tag = "✅" if success else "❌"
    duration_str = format_duration(duration_secs)

    subject = f"[NiuNIuNiu] {status_tag} {job_name} {status_icon} · {duration_str}"

    points = distill_summary_points(detail=detail, log_tail=log_tail)
    if not points:
        points = ["无业务摘要，详见服务器日志"]

    headline = (
        f"{status_tag} {status_icon} · {duration_str} · {job_name}（{label}） · {now}"
    )
    if not success:
        headline += f" · 退出码 {exit_code}"

    # 正文：首行元信息 + 一行合并的核心结果（手机上一屏看完）
    body = "【NiuNIuNiu】\n" + headline + "\n\n" + "；".join(points)
    return subject, body


def _send_email(subject: str, body: str, job_name: str, kind: str) -> bool:
    cfg = _smtp_config()
    to_addr = os.getenv("JOB_ALERT_EMAIL", DEFAULT_ALERT_EMAIL).strip()
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
        logger.info("已发送任务%s邮件 -> %s [%s]", kind, to_addr, job_name)
        return True
    except Exception as e:
        logger.error("发送任务邮件异常: %s", e)
        return False


def send_job_notification(
    job_name: str,
    *,
    success: bool,
    exit_code: int = 0,
    duration_secs: int | None = None,
    detail: str = "",
    log_tail: str = "",
) -> bool:
    """发送统一格式的任务结果邮件。"""
    if success and not notify_on_success_enabled():
        return False
    subject, body = build_job_email(
        job_name,
        success=success,
        exit_code=exit_code,
        duration_secs=duration_secs,
        detail=detail,
        log_tail=log_tail,
    )
    kind = "完成" if success else "失败"
    return _send_email(subject, body, job_name, kind)


def parse_duration_env() -> int | None:
    """从环境变量 JOB_DURATION_SECS 解析耗时（由 job_lib.sh 写入）。"""
    raw = os.getenv("JOB_DURATION_SECS", "").strip()
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def send_job_alert(
    job_name: str,
    *,
    exit_code: int = 1,
    detail: str = "",
    log_tail: str = "",
    duration_secs: int | None = None,
) -> bool:
    """发送任务失败邮件，未配置 SMTP 时仅打日志。成功发送返回 True。"""
    if duration_secs is None:
        duration_secs = parse_duration_env()
    return send_job_notification(
        job_name,
        success=False,
        exit_code=exit_code,
        duration_secs=duration_secs,
        detail=detail,
        log_tail=log_tail,
    )


def send_job_success(
    job_name: str,
    *,
    detail: str = "",
    log_tail: str = "",
    duration_secs: int | None = None,
) -> bool:
    """任务成功完成后发送提醒邮件。"""
    if duration_secs is None:
        duration_secs = parse_duration_env()
    return send_job_notification(
        job_name,
        success=True,
        duration_secs=duration_secs,
        detail=detail,
        log_tail=log_tail,
    )


def tail_log_file(path: str, lines: int = 40) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.readlines()
        return "".join(content[-lines:])
    except OSError:
        return ""
