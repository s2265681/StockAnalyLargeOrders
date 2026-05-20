import unittest
from unittest.mock import patch

from routes.emotion_cycle import _fetch_rise_count, _fetch_emotion_records


class FetchRiseCountTest(unittest.TestCase):
    @patch("routes.emotion_cycle._curl_get_json")
    def test_fetch_rise_count_from_index(self, mock_curl):
        mock_curl.return_value = {
            "data": {
                "diff": [
                    {"f104": 612, "f105": 1890},
                    {"f104": 488, "f105": 1420},
                ]
            }
        }
        self.assertEqual(_fetch_rise_count(), 1100)

    @patch("routes.emotion_cycle._curl_get_json")
    def test_fetch_rise_count_returns_none_when_empty(self, mock_curl):
        mock_curl.return_value = {"data": {"diff": []}}
        self.assertIsNone(_fetch_rise_count())


class EmotionRecordsRiseCountTest(unittest.TestCase):
    @patch("routes.emotion_cycle._persist_rise_count")
    @patch("routes.emotion_cycle._fetch_rise_count", return_value=1050)
    @patch("routes.emotion_cycle._fetch_zt_counts", return_value={})
    @patch("routes.emotion_cycle._merge_rise_count_cache", side_effect=lambda r: r)
    @patch("routes.emotion_cycle._curl_get_json")
    def test_latest_record_gets_rise_count(self, mock_curl, _merge, _zt, _rise, _persist):
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
        self.assertNotIn("rise_pct", records[-1])
        self.assertEqual(records[-1]["rise_count"], 1050)
        self.assertNotIn("rise_count", records[0])


if __name__ == "__main__":
    unittest.main()
