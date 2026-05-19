#!/usr/bin/env python3
"""CLI：任务成功后发邮件。用法: job_notify_success.py <job_name> [detail] [log_file]"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.job_notify import send_job_success, tail_log_file


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: job_notify_success.py <job_name> [detail] [log_file]", file=sys.stderr)
        return 1
    job_name = sys.argv[1]
    detail = sys.argv[2] if len(sys.argv) > 2 else ""
    log_file = sys.argv[3] if len(sys.argv) > 3 else ""
    log_tail = tail_log_file(log_file, lines=50) if log_file else ""
    send_job_success(job_name, detail=detail, log_tail=log_tail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
