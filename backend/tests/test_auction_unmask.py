import unittest

from services.auction_unmask import (
    is_valid_stock_code,
    resolve_masked_row,
    unmask_stockapi_rows,
    _decode_smartbox_name,
)


class AuctionUnmaskTest(unittest.TestCase):
    def test_is_valid_stock_code(self):
        self.assertTrue(is_valid_stock_code("600673"))
        self.assertFalse(is_valid_stock_code("00****"))

    def test_decode_smartbox_name(self):
        self.assertEqual(_decode_smartbox_name("\\u51b0\\u8f6e\\u73af\\u5883"), "冰轮环境")

    def test_unmask_skips_already_valid(self):
        rows = [{"code": "600673", "name": "东阳光", "qczf": 3.0}]
        self.assertEqual(unmask_stockapi_rows(rows), rows)

    def test_resolve_masked_row_冰轮(self):
        row = {"code": "00****", "name": "冰轮****", "qczf": 10.0, "qcwtje": 1e9}
        fixed = resolve_masked_row(row)
        self.assertIsNotNone(fixed)
        self.assertEqual(fixed["code"], "000811")
        self.assertIn("冰轮", fixed["name"])


if __name__ == "__main__":
    unittest.main()
