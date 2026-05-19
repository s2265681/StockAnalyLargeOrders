import json
import time
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

    @patch("routes.ai_diagnosis.get_hot_stocks_for_diagnosis")
    def test_hot_stocks_route(self, mock_fn):
        mock_fn.return_value = {
            "searched": [{"code": "000001", "name": "平安银行", "rating": "偏多"}],
            "hot": [{"code": "300750", "name": "宁德时代"}],
        }
        resp = self.client.get("/api/v1/ai-diagnosis/hot-stocks")
        body = resp.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]["searched"]), 1)
        self.assertEqual(len(body["data"]["hot"]), 1)

    @patch("routes.ai_diagnosis.get_hot_stocks_for_diagnosis")
    def test_hot_stocks_route_error_returns_empty(self, mock_fn):
        mock_fn.side_effect = Exception("unexpected")
        resp = self.client.get("/api/v1/ai-diagnosis/hot-stocks")
        body = resp.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["searched"], [])
        self.assertEqual(body["data"]["hot"], [])


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

    @patch("services.ai_diagnosis_service.get_valid_trading_date")
    @patch("services.ai_diagnosis_service.get_next_trading_date")
    def test_session_date_before_open(self, next_mock, valid_mock):
        from datetime import datetime

        from services.ai_diagnosis_service import get_diagnosis_session_date

        valid_mock.return_value = "2026-05-18"
        next_mock.return_value = {"date": "2026-05-15"}
        now = datetime(2026, 5, 18, 8, 0, 0)
        self.assertEqual(get_diagnosis_session_date(now), "20260515")

    @patch("services.ai_diagnosis_service.get_valid_trading_date")
    def test_session_date_after_open(self, valid_mock):
        from datetime import datetime

        from services.ai_diagnosis_service import get_diagnosis_session_date

        valid_mock.return_value = "2026-05-18"
        now = datetime(2026, 5, 18, 10, 0, 0)
        self.assertEqual(get_diagnosis_session_date(now), "20260518")

    @patch("services.ai_diagnosis_service.get_valid_trading_date")
    def test_session_date_weekend(self, valid_mock):
        from datetime import datetime

        from services.ai_diagnosis_service import get_diagnosis_session_date

        valid_mock.return_value = "2026-05-15"
        now = datetime(2026, 5, 16, 10, 0, 0)
        self.assertEqual(get_diagnosis_session_date(now), "20260515")

    @patch("services.ai_diagnosis_service.save_cache")
    @patch("services.ai_diagnosis_service.build_snapshot")
    @patch("services.ai_diagnosis_service._call_claude")
    @patch("services.ai_diagnosis_service._parse_report_json")
    @patch("services.ai_diagnosis_service.get_diagnosis_session_date")
    @patch("services.ai_diagnosis_service.get_cache")
    @patch("services.ai_diagnosis_service.purge_stale_cache")
    def test_run_diagnosis_purges_stale_on_new_session(
        self,
        purge_mock,
        cache_mock,
        session_mock,
        parse_mock,
        claude_mock,
        snap_mock,
        save_mock,
    ):
        from services.ai_diagnosis_service import run_diagnosis

        session_mock.return_value = "20260518"
        cache_mock.return_value = None
        snap_mock.return_value = {"code": "000001", "date": "20260518"}
        claude_mock.return_value = '{"rating":"中性","summary":"新"}'
        parse_mock.return_value = {"rating": "中性", "summary": "新", "buy_points": [], "sell_points": []}

        run_diagnosis("000001")

        purge_mock.assert_called_once_with("000001", "20260518")
        save_mock.assert_called_once()

    @patch("services.ai_diagnosis_service.get_diagnosis_session_date")
    @patch("services.ai_diagnosis_service.get_cache")
    @patch("services.ai_diagnosis_service.purge_stale_cache")
    @patch("services.ai_diagnosis_service.build_snapshot")
    def test_run_diagnosis_cache_hit_skips_purge(
        self, snap_mock, purge_mock, cache_mock, session_mock
    ):
        from services.ai_diagnosis_service import run_diagnosis

        session_mock.return_value = "20260518"
        cache_mock.return_value = {
            "snapshot": {"code": "000001"},
            "report": {"rating": "中性", "summary": "缓存"},
        }

        result = run_diagnosis("000001")

        self.assertTrue(result["cached"])
        purge_mock.assert_not_called()
        snap_mock.assert_not_called()


class TestGetHotStocksForDiagnosis(unittest.TestCase):
    def setUp(self):
        # 每次测试前清空热股缓存
        import services.ai_diagnosis_service as svc
        svc._HOT_STOCKS_CACHE["data"] = None
        svc._HOT_STOCKS_CACHE["ts"] = 0.0

    @patch("services.ai_diagnosis_service._fetch_ths_hot_top5")
    @patch("services.ai_diagnosis_service.execute_query")
    def test_returns_searched_and_hot(self, mock_query, mock_hot):
        mock_hot.return_value = [{"code": "300750", "name": "宁德时代"}]
        mock_query.return_value = [
            {
                "code": "000001",
                "snapshot_json": '{"quote": {"name": "平安银行"}, "basic": {}}',
                "report_json": '{"rating": "偏多"}',
            }
        ]
        from services.ai_diagnosis_service import get_hot_stocks_for_diagnosis
        result = get_hot_stocks_for_diagnosis()
        self.assertEqual(result["hot"], [{"code": "300750", "name": "宁德时代"}])
        self.assertEqual(len(result["searched"]), 1)
        self.assertEqual(result["searched"][0]["code"], "000001")
        self.assertEqual(result["searched"][0]["name"], "平安银行")
        self.assertEqual(result["searched"][0]["rating"], "偏多")

    @patch("services.ai_diagnosis_service._fetch_ths_hot_top5")
    @patch("services.ai_diagnosis_service.execute_query")
    def test_hot_cache_not_refetched_within_ttl(self, mock_query, mock_hot):
        mock_hot.return_value = [{"code": "600519", "name": "贵州茅台"}]
        mock_query.return_value = []
        from services.ai_diagnosis_service import get_hot_stocks_for_diagnosis
        get_hot_stocks_for_diagnosis()
        get_hot_stocks_for_diagnosis()
        self.assertEqual(mock_hot.call_count, 1)

    @patch("services.ai_diagnosis_service._fetch_ths_hot_top5")
    @patch("services.ai_diagnosis_service.execute_query")
    def test_db_error_returns_empty_searched(self, mock_query, mock_hot):
        mock_hot.return_value = []
        mock_query.side_effect = Exception("DB down")
        from services.ai_diagnosis_service import get_hot_stocks_for_diagnosis
        result = get_hot_stocks_for_diagnosis()
        self.assertEqual(result["searched"], [])


if __name__ == "__main__":
    unittest.main()
