import unittest
from unittest.mock import patch

from routes.emotion_cycle import (
    _compute_rise_ratio,
    _fetch_market_breadth,
    _fetch_emotion_records,
    _build_same_slot_comparison_text,
    save_intraday_snapshot,
    _load_intraday_snapshots,
)


class ComputeRiseRatioTest(unittest.TestCase):
    def test_ratio_is_rise_over_fall(self):
        self.assertEqual(_compute_rise_ratio(2800, 2000), 1.4)

    def test_ratio_none_when_fall_zero(self):
        self.assertIsNone(_compute_rise_ratio(2800, 0))


class FetchMarketBreadthTest(unittest.TestCase):
    @patch("routes.emotion_cycle._curl_get_json")
    def test_fetch_from_ths(self, mock_curl):
        mock_curl.return_value = {"data": {"up": 2800, "down": 2000}}
        result = _fetch_market_breadth()
        self.assertEqual(result["rise_count"], 2800)
        self.assertEqual(result["fall_count"], 2000)
        self.assertEqual(result["rise_ratio"], 1.4)

    @patch("routes.emotion_cycle._curl_get_json")
    def test_fetch_from_index(self, mock_curl):
        mock_curl.side_effect = [
            Exception("ths fail"),
            {
                "data": {
                    "diff": [
                        {"f104": 612, "f105": 1890},
                        {"f104": 488, "f105": 1420},
                    ]
                }
            },
        ]
        result = _fetch_market_breadth()
        self.assertEqual(result["rise_count"], 1100)
        self.assertEqual(result["fall_count"], 3310)
        self.assertEqual(result["rise_ratio"], round(1100 / 3310, 2))


class EmotionRecordsRiseRatioTest(unittest.TestCase):
    @patch("routes.emotion_cycle.save_intraday_snapshot")
    @patch("routes.emotion_cycle._persist_breadth")
    @patch("routes.emotion_cycle._fetch_market_breadth")
    @patch("routes.emotion_cycle._fetch_zt_counts", return_value={})
    @patch("routes.emotion_cycle._merge_breadth_cache", side_effect=lambda r: r)
    @patch("routes.emotion_cycle._curl_get_json")
    def test_latest_record_gets_rise_ratio(self, mock_curl, _merge, _zt, mock_breadth, _persist, _snap):
        mock_breadth.return_value = {
            "rise_count": 2800,
            "fall_count": 2000,
            "rise_ratio": 1.4,
        }
        mock_curl.return_value = {
            "code": 20000,
            "data": {
                "colNameList": ["date1", "szbl", "lbjs", "ylgd", "zxgd", "dmqx", "drqx", "ztjs", "dbcgl", "dtjs", "ygmc", "zbjs"],
                "contentList": [
                    [20260519, 65.67, 19, 7, 7, 3, 74, 90, 59.04, 8, None, 14],
                    [20260520, None, 11, 8, 8, 16, 49, 61, 62.22, 22, "利仁科技", 19],
                ],
            },
        }
        records = _fetch_emotion_records()
        self.assertEqual(records[-1]["rise_ratio"], 1.4)
        self.assertEqual(records[-1]["rise_count"], 2800)
        self.assertEqual(records[-1]["fall_count"], 2000)
        self.assertNotIn("rise_ratio", records[0])


class SameSlotComparisonTest(unittest.TestCase):
    def setUp(self):
        self._orig = _load_intraday_snapshots()

    def tearDown(self):
        from routes.emotion_cycle import _save_intraday_snapshots
        _save_intraday_snapshots(self._orig)

    @patch("routes.emotion_cycle._current_intraday_slot", return_value="1030")
    def test_builds_prev_same_slot_text(self, _slot):
        save_intraday_snapshot(
            {
                "date": "2026-05-19",
                "rise_count": 1200,
                "fall_count": 800,
                "rise_ratio": 1.5,
                "limit_up_count": 40,
            },
            slot="1030",
        )
        text = _build_same_slot_comparison_text(
            [{"date": "2026-05-19", "limit_up_count": 90}],
        )
        self.assertIn("昨日同时段", text)
        self.assertIn("10:30", text)
        self.assertIn("1.5", text)
        self.assertIn("勿与昨日收盘全天", text)


if __name__ == "__main__":
    unittest.main()
