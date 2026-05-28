#!/usr/bin/env python3
"""CLI：任务失败时发邮件。用法: job_notify_failure.py <job_name> <exit_code> [log_file]"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.job_notify import send_job_alert, tail_log_file
from utils.claude_client import get_last_api_error


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: job_notify_failure.py <job_name> <exit_code> [log_file]", file=sys.stderr)
        return 1
    job_name = sys.argv[1]
    exit_code = int(sys.argv[2])
    log_file = sys.argv[3] if len(sys.argv) > 3 else ""
    log_tail = tail_log_file(log_file) if log_file else ""
    api_err = get_last_api_error()
    if api_err and api_err not in log_tail:
        log_tail = (log_tail + "\nAPI: " + api_err).strip() if log_tail else ("API: " + api_err)
    send_job_alert(job_name, exit_code=exit_code, log_tail=log_tail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
