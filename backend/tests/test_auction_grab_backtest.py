import unittest
from unittest.mock import patch

from services import auction_grab_backtest as bt
from services import auction_grab_recommendation as rec


class AuctionGrabBacktestTest(unittest.TestCase):
    def setUp(self):
        rec._emotion_records_cache.clear()

    def test_winrate_calculation(self):
        rows = [
            {"version": "v1", "stars": 3, "close_change_pct": 5.0, "next_day_change_pct": -1.0},
            {"version": "v1", "stars": 3, "close_change_pct": -2.0, "next_day_change_pct": 3.0},
            {"version": "v1", "stars": 1, "close_change_pct": 1.0, "next_day_change_pct": 0.5},
        ]
        s = bt.summarize_winrates(rows)["v1"]["star3"]["close"]
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["wins"], 1)
        self.assertEqual(s["winrate"], 0.5)

    @patch("services.auction_grab_recommendation.get_limit_up_stocks_by_date")
    @patch("services.auction_grab_recommendation.get_recent_trading_dates")
    @patch("services.auction_grab_recommendation._get_emotion_context")
    @patch("services.auction_grab_recommendation._prev_trading_date")
    def test_run_backtest_compares_v1_v2(
        self, mock_prev, mock_emotion, mock_dates, mock_limit_up
    ):
        mock_prev.return_value = "2026-05-14"
        mock_dates.return_value = ["20260514", "20260515"]
        mock_emotion.return_value = {
            "stage": "升温期",
            "stage_score": 28,
            "advice": "",
            "recommended_names": set(),
            "metrics": {"limit_up_count": 60, "board_hit_rate": 50, "rise_count": 2800},
        }
        mock_limit_up.return_value = []

        items_day = [
            {
                "code": "002915",
                "name": "中欣氟材",
                "grab_change_pct": 5.0,
                "grab_order_amount": 5000,
                "close_change_pct": 8.0,
                "next_day_change_pct": 2.0,
            },
            {
                "code": "000001",
                "name": "弱势",
                "grab_change_pct": 1.0,
                "grab_order_amount": 100,
                "close_change_pct": -1.0,
                "next_day_change_pct": -0.5,
            },
        ]

        def fetch(_date):
            return [dict(x) for x in items_day]

        def enrich(items, _date):
            pass

        result = bt.run_recommendation_backtest(
            ["2026-05-15"],
            fetch_items_fn=fetch,
            enrich_returns_fn=enrich,
        )
        self.assertEqual(result["days"], 1)
        self.assertIn("v1", result["summary"])
        self.assertIn("v2", result["summary"])

    @patch("services.auction_grab_recommendation.get_limit_up_stocks_by_date")
    @patch("services.auction_grab_recommendation.get_recent_trading_dates")
    @patch("services.auction_grab_recommendation._get_emotion_context")
    @patch("services.auction_grab_recommendation._prev_trading_date")
    def test_v2_uses_prev_day_context(self, mock_prev, mock_emotion, mock_dates, mock_limit_up):
        mock_prev.return_value = "2026-05-14"
        mock_dates.return_value = ["20260514"]
        mock_limit_up.return_value = []
        calls = []

        def emotion_side_effect(compact, dash):
            calls.append(dash)
            return {
                "stage": "修复期",
                "stage_score": 24,
                "advice": "",
                "recommended_names": set(),
                "metrics": {},
            }

        mock_emotion.side_effect = emotion_side_effect

        items = [
            {"code": "000001", "name": "A", "grab_change_pct": 5.0, "grab_order_amount": 1000},
        ]
        rec.score_items_v2(items, "2026-05-15", 0)
        self.assertIn("2026-05-14", calls)
        self.assertNotIn("2026-05-15", calls)


if __name__ == "__main__":
    unittest.main()
