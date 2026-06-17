import unittest
from unittest.mock import patch

from services import auction_grab_service as ag_store
from utils.stock_code import is_valid_stock_code


class AuctionGrabServiceTest(unittest.TestCase):
    def test_items_from_raw_api(self):
        raw = [
            {
                "code": "600673",
                "name": "东阳光",
                "openAmt": 12000000,
                "qczf": 9.99,
                "qccje": 5000000,
                "qcwtje": 8000000,
                "time": "2026-05-07",
            }
        ]
        items = ag_store.items_from_raw_api(raw, "2026-05-07")
        self.assertEqual(items[0]["code"], "600673")
        self.assertEqual(items[0]["open_amount"], 1200.0)
        self.assertEqual(items[0]["grab_order_amount"], 800.0)

    def test_items_from_raw_api_skips_masked_codes(self):
        raw = [
            {"code": "00****", "name": "冰轮****", "openAmt": 1, "qczf": 10, "qccje": 1, "qcwtje": 1},
            {"code": "600673", "name": "东阳光", "openAmt": 12000000, "qczf": 9.99, "qccje": 5000000, "qcwtje": 8000000},
        ]
        items = ag_store.items_from_raw_api(raw, "2026-06-17")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["code"], "600673")

    def test_is_valid_stock_code(self):
        self.assertTrue(is_valid_stock_code("600673"))
        self.assertTrue(is_valid_stock_code("673"))
        self.assertFalse(is_valid_stock_code("00****"))
        self.assertFalse(is_valid_stock_code(""))

    def test_sort_items_by_turnover(self):
        items = [
            {"grab_order_amount": 100, "grab_turnover": 50, "open_amount": 10, "grab_change_pct": 1},
            {"grab_order_amount": 10, "grab_turnover": 500, "open_amount": 20, "grab_change_pct": 2},
        ]
        sorted_items = ag_store.sort_items(items, "cjje")
        self.assertEqual(sorted_items[0]["grab_turnover"], 500)

    @patch("services.auction_grab_service.execute_query")
    def test_load_items(self, mock_query):
        mock_query.return_value = [
            {
                "code": "000001",
                "name": "平安",
                "open_amount": 100,
                "grab_change_pct": 3.5,
                "grab_turnover": 80,
                "grab_order_amount": 90,
                "close_change_pct": 1.2,
                "next_day_change_pct": -0.5,
                "source_time": "2026-05-07",
            }
        ]
        items = ag_store.load_items("20260507", 0)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["close_change_pct"], 1.2)

    @patch("services.auction_grab_service.execute_many")
    @patch("services.auction_grab_service.execute_write")
    def test_replace_snapshot(self, mock_write, mock_many):
        mock_many.return_value = 1
        n = ag_store.replace_snapshot(
            "20260507",
            0,
            [
                {
                    "code": "000001",
                    "name": "平安",
                    "open_amount": 1,
                    "grab_change_pct": 2,
                    "grab_turnover": 3,
                    "grab_order_amount": 4,
                }
            ],
        )
        self.assertEqual(n, 1)
        mock_write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
