import json
import unittest
from unittest.mock import patch

from flask import Flask

from routes.ai_diagnosis import ai_diagnosis_bp


class AiDiagnosisRouteTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(ai_diagnosis_bp)
        self.client = self.app.test_client()

    def test_post_diagnosis_invalid_code(self):
        resp = self.client.post("/api/v1/ai-diagnosis", json={"code": "abc"})
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(body["success"])

    @patch("routes.ai_diagnosis.run_diagnosis")
    def test_post_diagnosis_success(self, run_mock):
        run_mock.return_value = {
            "code": "000001",
            "date": "20260517",
            "snapshot": {"code": "000001"},
            "report": {"rating": "中性", "summary": "测试"},
            "cached": False,
        }
        resp = self.client.post("/api/v1/ai-diagnosis", json={"code": "000001"})
        body = resp.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["report"]["rating"], "中性")

    @patch("routes.ai_diagnosis.get_cache")
    def test_get_cache_hit(self, cache_mock):
        cache_mock.return_value = {
            "snapshot": {"code": "000001"},
            "report": {"summary": "缓存"},
        }
        resp = self.client.get("/api/v1/ai-diagnosis/cache?code=000001&date=20260517")
        body = resp.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["report"]["summary"], "缓存")

    @patch("routes.ai_diagnosis.run_chat")
    def test_chat_requires_message(self, chat_mock):
        resp = self.client.post(
            "/api/v1/ai-diagnosis/chat",
            json={"code": "000001", "message": ""},
        )
        body = resp.get_json()
        self.assertFalse(body["success"])
        chat_mock.assert_not_called()

    @patch("routes.ai_diagnosis.run_chat")
    def test_chat_success(self, chat_mock):
        chat_mock.return_value = {"reply": "建议观望"}
        resp = self.client.post(
            "/api/v1/ai-diagnosis/chat",
            json={
                "code": "000001",
                "message": "能追吗？",
                "context": {"report": {}, "snapshot": {}},
            },
        )
        body = resp.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["reply"], "建议观望")


class AiDiagnosisServiceTest(unittest.TestCase):
    def test_normalize_code(self):
        from services.ai_diagnosis_service import normalize_code

        self.assertEqual(normalize_code("1"), "000001")
        self.assertEqual(normalize_code("600519"), "600519")
        self.assertEqual(normalize_code("sz000001"), "000001")

    def test_parse_report_json(self):
        from services.ai_diagnosis_service import _parse_report_json

        raw = '说明文字\n{"rating": "偏多", "summary": "ok"}'
        parsed = _parse_report_json(raw)
        self.assertEqual(parsed["rating"], "偏多")
        self.assertEqual(parsed["position_advice"], "观望")

    def test_parse_report_json_with_fence(self):
        from services.ai_diagnosis_service import _parse_report_json

        raw = """```json
{"rating": "中性", "summary": "测试", "buy_points": ["回踩5日线"], "sell_points": []}
```"""
        parsed = _parse_report_json(raw)
        self.assertEqual(parsed["rating"], "中性")
        self.assertEqual(len(parsed["buy_points"]), 1)

    def test_fallback_report_from_text(self):
        from services.ai_diagnosis_service import _fallback_report_from_text

        report = _fallback_report_from_text("这是一段纯文本分析")
        self.assertTrue(report["sections"])
        self.assertEqual(report["rating"], "中性")

    def test_normalize_point_items(self):
        from services.ai_diagnosis_service import _normalize_point_items

        items = _normalize_point_items(["10.50元：回踩5日线企稳", {"price": "11.2", "reason": "突破前高"}])
        self.assertEqual(items[0]["price"], "10.50元")
        self.assertEqual(items[1]["reason"], "突破前高")


if __name__ == "__main__":
    unittest.main()
