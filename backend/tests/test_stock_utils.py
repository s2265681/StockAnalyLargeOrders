import unittest
from unittest.mock import patch

from utils import stock_utils


class TestStockUtils(unittest.TestCase):
    def setUp(self):
        stock_utils._NAME_CACHE.clear()

    def test_placeholder_name_detection(self):
        self.assertTrue(stock_utils._is_placeholder_name('股票002971', '002971'))
        self.assertFalse(stock_utils._is_placeholder_name('和远气体', '002971'))

    @patch('utils.stock_utils._lookup_name_from_akshare', return_value=None)
    @patch('services.eastmoney_free.EastMoneyFreeSource')
    @patch('utils.stock_utils._lookup_name_from_db', return_value='和远气体')
    def test_prefers_db_name_over_placeholder(self, _db, _em_cls, _ak):
        name = stock_utils.get_stock_name_by_code('002971')
        self.assertEqual(name, '和远气体')
        self.assertEqual(stock_utils._NAME_CACHE['002971'], '和远气体')

    @patch('utils.stock_utils._lookup_name_from_db', return_value=None)
    @patch('utils.stock_utils._lookup_name_from_akshare', return_value='测试股份')
    @patch('services.eastmoney_free.EastMoneyFreeSource')
    def test_akshare_fallback(self, em_cls, _ak, _db):
        em_cls.return_value.get_realtime_quote.return_value = None
        name = stock_utils.get_stock_name_by_code('688143')
        self.assertEqual(name, '测试股份')


class TestLimitPrice(unittest.TestCase):
    def test_limit_up_rounds_half_up_not_bankers(self):
        # 3.75 * 1.1 = 4.125，交易所四舍五入为 4.13，Python round 会得到 4.12
        self.assertEqual(stock_utils.calc_limit_price(3.75, '000518'), 4.13)

    def test_is_at_limit_up_for_000518(self):
        self.assertTrue(stock_utils.is_at_limit_up(
            4.13, 3.75, '000518', '四环生物', change_percent=10.13
        ))

    def test_seal_order_would_detect_limit_up(self):
        from services.eastmoney_free import EastMoneyFreeSource
        from services.limit_up_monitor import LimitUpMonitor
        from services.alert_monitor import check_rule_condition

        src = EastMoneyFreeSource()
        code = '000518'
        quote = src.get_realtime_quote(code)
        if not quote:
            self.skipTest('行情不可用')
        ob = src.get_order_book(code)
        data = LimitUpMonitor().analyze(code, quote, ob)
        self.assertTrue(data['is_limit_up'], data)
        rule = {'alert_type': 'seal_order', 'threshold': 610000.0, 'direction': 'below'}
        self.assertTrue(check_rule_condition(rule, quote, data))


if __name__ == '__main__':
    unittest.main()
