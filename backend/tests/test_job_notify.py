import unittest
from unittest.mock import patch

from utils import date_utils
from utils.job_notify import send_job_alert, tail_log_file


class TestJobNotify(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "u@example.com",
            "SMTP_PASS": "secret",
            "JOB_ALERT_EMAIL": "rock.shang@kalowave.com",
        },
        clear=False,
    )
    @patch("utils.job_notify.smtplib.SMTP_SSL")
    def test_send_job_alert(self, mock_smtp):
        self.assertTrue(send_job_alert("intraday", exit_code=1, detail="test"))
        mock_smtp.return_value.__enter__.return_value.sendmail.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "JOB_NOTIFY_ON_SUCCESS": "1",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "u@example.com",
            "SMTP_PASS": "secret",
        },
        clear=False,
    )
    @patch("utils.job_notify.smtplib.SMTP_SSL")
    def test_send_job_success(self, mock_smtp):
        from utils.job_notify import send_job_success
        self.assertTrue(send_job_success("intraday", detail="ok"))
        mock_smtp.return_value.__enter__.return_value.sendmail.assert_called_once()

    @patch.dict("os.environ", {"JOB_NOTIFY_ON_SUCCESS": "0"}, clear=False)
    @patch("utils.job_notify.smtplib.SMTP_SSL")
    def test_success_disabled(self, mock_smtp):
        from utils.job_notify import send_job_success
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
