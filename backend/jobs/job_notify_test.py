#!/usr/bin/env python3
"""发送一封测试邮件，预览当前任务通知格式。

用法（需在 backend/.env 配置 SMTP）：
  cd backend && ./venv/bin/python jobs/job_notify_test.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.job_notify import build_job_email, send_job_notification

SAMPLE_LOG = """\
2026-05-19 15:30:05 [INFO] intraday_refresh: 涨停梯队: ok
2026-05-19 15:30:20 [INFO] intraday_refresh: 情绪周期研判: ok
2026-05-19 15:30:35 [INFO] intraday_refresh: 盘中买卖指导: ok
2026-05-19 18:00:01 [INFO] dragon_tiger_ai_daily: 当日补全结果: {'total': 8, 'saved': 2, 'skipped': 5, 'failed': 1, 'no_data': 0}
2026-05-19 09:30:01 [INFO] auction_grab_sync: 早盘 period=0 入库 25 条
"""


def main() -> int:
    os.environ["JOB_DURATION_SECS"] = "42"
    subject, body = build_job_email(
        "intraday",
        success=True,
        duration_secs=42,
        log_tail=SAMPLE_LOG,
    )
    print("主题:", subject)
    print("正文:\n", body, sep="")
    print("---")
    ok = send_job_notification(
        "intraday",
        success=True,
        duration_secs=42,
        log_tail=SAMPLE_LOG,
    )
    if ok:
        print("已发送测试邮件，请查收 JOB_ALERT_EMAIL 邮箱。")
        return 0
    print("发送失败：请在 backend/.env 配置 SMTP_HOST / SMTP_USER / SMTP_PASS / JOB_ALERT_EMAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
