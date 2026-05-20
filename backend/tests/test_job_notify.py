import unittest
from unittest.mock import patch

from utils import date_utils
from utils.job_notify import (
    build_job_email,
    distill_summary_points,
    extract_core_log_lines,
    extract_current_run_log,
    format_duration,
    send_job_alert,
    send_job_success,
    tail_log_file,
)


class TestJobNotify(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(8), "8 秒")
        self.assertEqual(format_duration(65), "1 分 5 秒")
        self.assertEqual(format_duration(120), "2 分")
        self.assertEqual(format_duration(None), "—")

    def test_extract_core_log_lines(self):
        log = """\
2026-05-19 15:30:01 [INFO] intraday_refresh: ===== 盘中刷新开始 date=20260519 =====
2026-05-19 15:30:05 [INFO] intraday_refresh: 涨停梯队: ok
2026-05-19 15:30:20 [INFO] intraday_refresh: 情绪周期研判: ok
2026-05-19 15:30:35 [INFO] intraday_refresh: 盘中买卖指导: ok
2026-05-19 15:30:36 [INFO] intraday_refresh: ===== 盘中刷新完成 date=20260519 =====
"""
        core = extract_core_log_lines(log)
        self.assertIn("涨停梯队: ok", core)
        self.assertIn("情绪周期研判: ok", core)
        self.assertNotIn("盘中刷新开始", core)

    def test_distill_dragon_tiger_result(self):
        log = "2026-05-19 18:00:01 [INFO] x: 当日补全结果: {'total': 8, 'saved': 2, 'skipped': 5, 'failed': 1, 'no_data': 0}\n"
        points = distill_summary_points(log_tail=log)
        self.assertEqual(points, ["AI共8只/新2/跳5/败1"])

    def test_distill_summary_points(self):
        log = """\
2026-05-19 15:30:05 [INFO] x: 涨停梯队: ok
2026-05-19 15:30:20 [INFO] x: 情绪周期研判: ok
2026-05-19 15:30:35 [INFO] x: 盘中买卖指导: ok
"""
        points = distill_summary_points(log_tail=log)
        self.assertEqual(points, ["梯队✓", "情绪✓", "买卖✓"])

    def test_extract_current_run_log(self):
        log = """\
2026-05-20 10:37:18 [echelon_intraday] 失败 exit=1 耗时=135s
2026-05-20 11:07:18 [echelon_intraday] 失败 exit=1 耗时=134s
2026-05-20 12:23:01 [INFO] echelon_intraday: ===== 梯队盘中刷新开始 date=20260520 =====
2026-05-20 12:23:29 [INFO] echelon_intraday: 涨停梯队: saved
2026-05-20 12:23:29 [INFO] echelon_intraday: ===== 梯队盘中刷新完成 date=20260520 =====
"""
        current = extract_current_run_log(log, job_name="echelon_intraday")
        self.assertIn("梯队盘中刷新开始", current)
        self.assertIn("涨停梯队: saved", current)
        self.assertNotIn("10:37:18", current)
        self.assertNotIn("AI 分组未返回有效标签", current)

    def test_success_email_excludes_old_failures(self):
        log = """\
2026-05-20 10:37:18 [echelon_intraday] 失败 exit=1 耗时=135s
2026-05-20 11:07:18 [INFO] routes.limit_up_echelon: 离线生成涨停梯队失败: AI 分组未返回有效标签
2026-05-20 12:23:01 [INFO] echelon_intraday: ===== 梯队盘中刷新开始 date=20260520 =====
2026-05-20 12:23:29 [INFO] echelon_intraday: 涨停梯队: saved
2026-05-20 12:23:29 [INFO] echelon_intraday: ===== 梯队盘中刷新完成 date=20260520 =====
"""
        subject, body = build_job_email(
            "echelon_intraday",
            success=True,
            duration_secs=29,
            log_tail=log,
        )
        self.assertIn("成功", subject)
        self.assertIn("梯队✓", body)
        self.assertNotIn("未返回有效标签", body)
        self.assertNotIn("构建失败", body)
        self.assertNotIn("exit=1", body)

        subject, body = build_job_email(
            "intraday",
            success=True,
            duration_secs=42,
            log_tail="2026-05-19 15:30:05 [INFO] x: 涨停梯队: ok\n",
        )
        self.assertIn("成功", subject)
        self.assertIn("42 秒", subject)
        self.assertIn("✅ 成功 · 42 秒", body)
        self.assertIn("梯队✓", body)
        self.assertNotIn("1. 状态", body)

    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "u@example.com",
            "SMTP_PASS": "secret",
            "JOB_ALERT_EMAIL": "s2265681@163.com",
            "JOB_DURATION_SECS": "10",
        },
        clear=False,
    )
    @patch("utils.job_notify.smtplib.SMTP_SSL")
    def test_send_job_alert(self, mock_smtp):
        self.assertTrue(send_job_alert("intraday", exit_code=1, detail="test error"))
        mock_smtp.return_value.__enter__.return_value.sendmail.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "JOB_NOTIFY_ON_SUCCESS": "1",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "u@example.com",
            "SMTP_PASS": "secret",
            "JOB_DURATION_SECS": "5",
        },
        clear=False,
    )
    @patch("utils.job_notify.smtplib.SMTP_SSL")
    def test_send_job_success(self, mock_smtp):
        self.assertTrue(
            send_job_success(
                "dragon_tiger",
                log_tail="2026-05-19 18:00:01 [INFO] x: 当日补全结果: {'saved': 3}\n",
            )
        )
        mock_smtp.return_value.__enter__.return_value.sendmail.assert_called_once()

    @patch.dict("os.environ", {"JOB_NOTIFY_ON_SUCCESS": "0"}, clear=False)
    @patch("utils.job_notify.smtplib.SMTP_SSL")
    def test_success_disabled(self, mock_smtp):
        self.assertFalse(send_job_success("intraday"))
        mock_smtp.return_value.__enter__.return_value.sendmail.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    def test_send_without_smtp_skips(self):
        with patch.dict("os.environ", {}, clear=True):
            import os
            for k in list(os.environ.keys()):
                if k.startswith("SMTP_"):
                    del os.environ[k]
        self.assertFalse(send_job_alert("intraday", exit_code=1))


class TestTradingDay(unittest.TestCase):
    def test_weekend_not_trading(self):
        self.assertFalse(date_utils.is_trading_day("2026-05-17"))

    @patch("utils.date_utils._is_trading_day_eastmoney", return_value=True)
    def test_weekday_trading(self, _mock):
        self.assertTrue(date_utils.is_trading_day("2026-05-15"))


class TestTailLog(unittest.TestCase):
    def test_tail_missing(self):
        self.assertEqual(tail_log_file("/nonexistent.log"), "")


if __name__ == "__main__":
    unittest.main()
