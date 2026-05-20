import unittest
from unittest.mock import patch, MagicMock


class TestAlertNotify(unittest.TestCase):

    def test_build_alert_email_change_pct_above(self):
        from utils.alert_notify import build_alert_email
        rule = {'code': '600519', 'stock_name': '贵州茅台', 'alert_type': 'change_pct',
                'threshold': 5.0, 'direction': 'above'}
        quote = {'change_percent': 6.2, 'price': 1800.0}
        subject, body = build_alert_email(rule, quote, {})
        self.assertIn('600519', subject)
        self.assertIn('涨跌幅', subject)
        self.assertIn('6.2', body)
        self.assertIn('涨超5.0%', body)

    def test_build_alert_email_change_pct_below(self):
        from utils.alert_notify import build_alert_email
        rule = {'code': '000001', 'stock_name': '平安银行', 'alert_type': 'change_pct',
                'threshold': 3.0, 'direction': 'below'}
        quote = {'change_percent': -4.0, 'price': 9.6}
        subject, body = build_alert_email(rule, quote, {})
        self.assertIn('跌超3.0%', body)

    def test_build_alert_email_limit_up(self):
        from utils.alert_notify import build_alert_email
        rule = {'code': '000001', 'stock_name': '平安银行', 'alert_type': 'limit_up',
                'threshold': None, 'direction': None}
        quote = {'change_percent': 10.01, 'price': 12.50}
        subject, body = build_alert_email(rule, quote, {'is_limit_up': True})
        self.assertIn('涨停', subject)
        self.assertIn('000001', subject)

    def test_build_alert_email_limit_down(self):
        from utils.alert_notify import build_alert_email
        rule = {'code': '600036', 'stock_name': '招商银行', 'alert_type': 'limit_down',
                'threshold': None, 'direction': None}
        quote = {'change_percent': -10.01, 'price': 36.0}
        subject, body = build_alert_email(rule, quote, {'is_limit_up': False})
        self.assertIn('跌停', subject)
        self.assertIn('600036', subject)
        self.assertIn('-10.01', body)

    def test_build_alert_email_seal_order(self):
        from utils.alert_notify import build_alert_email
        rule = {'code': '300001', 'stock_name': '特锐德', 'alert_type': 'seal_order',
                'threshold': 500.0, 'direction': None}
        quote = {'change_percent': 10.01, 'price': 5.50}
        subject, body = build_alert_email(rule, quote, {'is_limit_up': True, 'seal_volume_lots': 300})
        self.assertIn('封单', subject)
        self.assertIn('300 手', body)
        self.assertIn('500.0 手', body)

    @patch('utils.alert_notify._smtp_config')
    @patch('smtplib.SMTP_SSL')
    def test_send_stock_alert_calls_smtp(self, mock_smtp_cls, mock_config):
        mock_config.return_value = {
            'host': 'smtp.163.com', 'port': 465, 'user': 'a@163.com',
            'password': 'pass', 'use_ssl': True, 'sender': 'a@163.com',
        }
        mock_smtp_instance = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_smtp_instance
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        from utils.alert_notify import send_stock_alert
        rule = {'code': '600519', 'stock_name': '贵州茅台', 'alert_type': 'limit_up',
                'threshold': None, 'direction': None}
        result = send_stock_alert(rule, {'change_percent': 10.0, 'price': 1800.0},
                                  {'is_limit_up': True}, to_email='test@qq.com')
        self.assertTrue(result)
        mock_smtp_instance.sendmail.assert_called_once()

    @patch('utils.alert_notify._smtp_config')
    def test_send_stock_alert_no_smtp_returns_false(self, mock_config):
        mock_config.return_value = None
        from utils.alert_notify import send_stock_alert
        result = send_stock_alert({'code': '600519', 'stock_name': '茅台',
                                   'alert_type': 'limit_up', 'threshold': None, 'direction': None},
                                  {}, {}, to_email='test@qq.com')
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
