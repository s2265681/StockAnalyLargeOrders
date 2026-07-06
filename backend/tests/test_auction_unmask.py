import unittest

from services.auction_unmask import (
    is_valid_stock_code,
    resolve_masked_row,
    unmask_stockapi_rows,
    _decode_smartbox_name,
    _pick_best_candidate,
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

    def test_resolve_masked_row_uses_zf_field(self):
        row = {"code": "00****", "name": "冰轮****", "zf": 10.0, "price": 0}
        fixed = resolve_masked_row(row)
        self.assertIsNotNone(fixed)
        self.assertEqual(fixed["code"], "000811")

    def test_resolve_masked_row_short_name_with_price(self):
        row = {
            "code": "60****",
            "name": "国****",
            "zf": 5.49,
            "price": 23.82,
            "bk": "军用雷达、低空经济",
        }
        fixed = resolve_masked_row(row)
        self.assertIsNotNone(fixed)
        self.assertEqual(fixed["code"], "600562")
        self.assertIn("国睿", fixed["name"])

    def test_pick_best_candidate_prefers_price_match(self):
        candidates = [
            {"code": "600562", "name": "国睿科技"},
            {"code": "600877", "name": "电科芯片"},
        ]
        hit = _pick_best_candidate(candidates, target_zf=5.49, target_price=23.82, name_prefix='')
        self.assertIsNotNone(hit)
        self.assertEqual(hit["code"], "600562")


if __name__ == "__main__":
    unittest.main()
