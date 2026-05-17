import unittest
from unittest.mock import patch

from flask import Flask

from routes.dragon_tiger import dragon_tiger_bp


class DragonTigerAiCacheTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(dragon_tiger_bp)
        self.client = self.app.test_client()

    @patch("routes.dragon_tiger.get_ai_analysis", return_value="所属题材：人工智能")
    def test_cache_returns_analysis_when_present(self, _mock_get):
        res = self.client.get(
            "/api/v1/dragon-tiger/ai-analysis-cache",
            query_string={"date": "20260515", "code": "000001"},
        )
        payload = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["analysis"], "所属题材：人工智能")

    @patch("routes.dragon_tiger.get_ai_analysis", return_value=None)
    def test_cache_returns_not_generated_message(self, _mock_get):
        res = self.client.get(
            "/api/v1/dragon-tiger/ai-analysis-cache",
            query_string={"date": "20260515", "code": "000001"},
        )
        payload = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertIsNone(payload["data"])
        self.assertEqual(payload["message"], "还未生成")

    @patch("routes.dragon_tiger.get_ai_analysis", return_value="旧版无题材字段")
    def test_post_compat_readonly_no_generation(self, mock_get):
        with patch("routes.dragon_tiger._call_claude") as mock_claude:
            res = self.client.post(
                "/api/v1/dragon-tiger/ai-analysis",
                json={"date": "20260515", "code": "000001"},
            )
        payload = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertIsNone(payload["data"])
        mock_claude.assert_not_called()
        mock_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
