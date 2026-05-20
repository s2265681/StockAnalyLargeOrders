import unittest


class TestCheckRuleCondition(unittest.TestCase):

    def _check(self, rule, quote, limit_up_data):
        from services.alert_monitor import check_rule_condition
        return check_rule_condition(rule, quote, limit_up_data)

    def test_change_pct_above_triggered(self):
        rule = {'alert_type': 'change_pct', 'threshold': 5.0, 'direction': 'above'}
        self.assertTrue(self._check(rule, {'change_percent': 6.2, 'price': 100.0, 'yesterday_close': 94.2}, {}))

    def test_change_pct_above_not_triggered(self):
        rule = {'alert_type': 'change_pct', 'threshold': 5.0, 'direction': 'above'}
        self.assertFalse(self._check(rule, {'change_percent': 3.1, 'price': 100.0, 'yesterday_close': 96.9}, {}))

    def test_change_pct_above_exact_boundary(self):
        rule = {'alert_type': 'change_pct', 'threshold': 5.0, 'direction': 'above'}
        self.assertTrue(self._check(rule, {'change_percent': 5.0, 'price': 100.0, 'yesterday_close': 95.0}, {}))

    def test_change_pct_below_triggered(self):
        rule = {'alert_type': 'change_pct', 'threshold': 3.0, 'direction': 'below'}
        self.assertTrue(self._check(rule, {'change_percent': -4.0, 'price': 96.0, 'yesterday_close': 100.0}, {}))

    def test_change_pct_below_not_triggered(self):
        rule = {'alert_type': 'change_pct', 'threshold': 3.0, 'direction': 'below'}
        self.assertFalse(self._check(rule, {'change_percent': -1.5, 'price': 98.5, 'yesterday_close': 100.0}, {}))

    def test_limit_up_triggered(self):
        rule = {'alert_type': 'limit_up', 'threshold': None, 'direction': None}
        self.assertTrue(self._check(rule, {}, {'is_limit_up': True}))

    def test_limit_up_not_triggered(self):
        rule = {'alert_type': 'limit_up', 'threshold': None, 'direction': None}
        self.assertFalse(self._check(rule, {}, {'is_limit_up': False}))

    def test_limit_down_triggered(self):
        rule = {'alert_type': 'limit_down', 'threshold': None, 'direction': None}
        quote = {'change_percent': -10.01, 'price': 8.99, 'yesterday_close': 10.0}
        self.assertTrue(self._check(rule, quote, {'is_limit_up': False}))

    def test_limit_down_not_triggered(self):
        rule = {'alert_type': 'limit_down', 'threshold': None, 'direction': None}
        quote = {'change_percent': -3.0, 'price': 9.7, 'yesterday_close': 10.0}
        self.assertFalse(self._check(rule, quote, {'is_limit_up': False}))

    def test_seal_order_below_triggered(self):
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': 'below'}
        self.assertTrue(self._check(rule, {}, {'is_limit_up': True, 'seal_volume_lots': 300}))

    def test_seal_order_below_not_triggered(self):
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': 'below'}
        self.assertFalse(self._check(rule, {}, {'is_limit_up': True, 'seal_volume_lots': 800}))

    def test_seal_order_below_default_triggered(self):
        # direction=None 默认走 below 逻辑
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': None}
        self.assertTrue(self._check(rule, {}, {'is_limit_up': True, 'seal_volume_lots': 300}))

    def test_seal_order_above_triggered(self):
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': 'above'}
        self.assertTrue(self._check(rule, {}, {'is_limit_up': True, 'seal_volume_lots': 800}))

    def test_seal_order_above_not_triggered(self):
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': 'above'}
        self.assertFalse(self._check(rule, {}, {'is_limit_up': True, 'seal_volume_lots': 300}))

    def test_seal_order_above_exact_boundary(self):
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': 'above'}
        self.assertTrue(self._check(rule, {}, {'is_limit_up': True, 'seal_volume_lots': 500}))

    def test_seal_order_not_limit_up(self):
        rule = {'alert_type': 'seal_order', 'threshold': 500.0, 'direction': 'below'}
        self.assertFalse(self._check(rule, {}, {'is_limit_up': False, 'seal_volume_lots': 300}))

    def test_quote_none_returns_false(self):
        rule = {'alert_type': 'change_pct', 'threshold': 5.0, 'direction': 'above'}
        self.assertFalse(self._check(rule, None, {}))

    def test_change_pct_missing_threshold_returns_false(self):
        rule = {'alert_type': 'change_pct', 'threshold': None, 'direction': 'above'}
        self.assertFalse(self._check(rule, {'change_percent': 10.0}, {}))


if __name__ == '__main__':
    unittest.main()
