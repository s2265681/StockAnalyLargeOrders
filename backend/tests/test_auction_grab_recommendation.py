import unittest
from unittest.mock import patch

from services import auction_grab_recommendation as rec


class AuctionGrabRecommendationTest(unittest.TestCase):
    def setUp(self):
        rec._emotion_records_cache.clear()

    @patch("services.auction_grab_recommendation.get_limit_up_stocks_by_date")
    @patch("services.auction_grab_recommendation.get_recent_trading_dates")
    @patch("services.auction_grab_recommendation._get_emotion_context")
    def test_assigns_top_two_three_stars(self, mock_emotion, mock_dates, mock_limit_up):
        mock_dates.return_value = ["20260515"]
        mock_emotion.return_value = {
            "stage": "升温期",
            "stage_score": 28,
            "advice": "加仓参与主线",
            "recommended_names": {"中欣氟材"},
            "metrics": {
                "limit_up_count": 65,
                "board_hit_rate": 55,
                "rise_count": 58,
                "limit_down_count": 10,
            },
        }
        mock_limit_up.return_value = [
            {
                "code": "002915",
                "name": "中欣氟材",
                "tag_name": "化工",
                "boards": 2,
                "is_leader": 1,
                "leader_role": "龙头",
                "industry": "化工",
            },
            {
                "code": "000001",
                "name": "弱势股",
                "tag_name": "其他",
                "boards": 1,
                "is_leader": 0,
                "industry": "银行",
            },
        ]

        items = [
            {
                "code": "002915",
                "name": "中欣氟材",
                "grab_change_pct": 5.0,
                "grab_order_amount": 5000,
            },
            {
                "code": "000001",
                "name": "弱势股",
                "grab_change_pct": 1.0,
                "grab_order_amount": 100,
            },
            {
                "code": "000002",
                "name": "普通股",
                "grab_change_pct": 4.0,
                "grab_order_amount": 800,
            },
        ]

        meta = rec.enrich_auction_recommendations(items, "2026-05-15", 0)
        stars = [i["recommend_stars"] for i in items]
        self.assertEqual(sum(1 for s in stars if s == 3), 2)
        self.assertEqual(items[0]["recommend_stars"], 3)
        self.assertIn("recommend_reason", items[0])
        self.assertEqual(meta["stage"], "升温期")

    def test_assign_stars_caps_three_star_count(self):
        scored = [
            {"composite_score": 90, "recommend_stars": 0},
            {"composite_score": 85, "recommend_stars": 0},
            {"composite_score": 80, "recommend_stars": 0},
            {"composite_score": 75, "recommend_stars": 0},
        ]
        rec._assign_stars(scored)
        three_count = sum(1 for r in scored if r["recommend_stars"] == 3)
        self.assertLessEqual(three_count, 2)


if __name__ == "__main__":
    unittest.main()
