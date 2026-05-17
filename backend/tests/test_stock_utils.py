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


if __name__ == '__main__':
    unittest.main()
