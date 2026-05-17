import unittest
from unittest.mock import patch

from flask import Flask

from routes.emotion_cycle import emotion_cycle_bp


def _auth_headers(role='user'):
    from utils.auth_middleware import generate_token
    token = generate_token(1, 'tester', role)
    return {'Authorization': f'Bearer {token}'}


class EmotionCycleCurrentRefreshTest(unittest.TestCase):
    def test_refresh_current_analysis_only_updates_latest_trading_day(self):
        app = Flask(__name__)
        app.register_blueprint(emotion_cycle_bp)

        records = [
            {"date": f"2026-05-{day:02d}", "limit_up_count": day}
            for day in range(8, 16)
        ]
        ai_result = {
            "date": "2026-05-15",
            "stage": "退潮期",
            "analysis": "盘中情绪走弱",
            "advice": "控制仓位",
            "recommendations": [],
        }

        with patch("routes.emotion_cycle._call_claude_batch", return_value=[ai_result]) as call_ai:
            with patch("routes.emotion_cycle._save_analysis_to_db", return_value=True) as save:
                response = app.test_client().post(
                    "/api/v1/emotion-analysis-refresh-current",
                    json={"records": records},
                )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"], ai_result)

        analyzed_records = call_ai.call_args.args[0]
        self.assertEqual(
            [record["date"] for record in analyzed_records],
            [
                "2026-05-10",
                "2026-05-11",
                "2026-05-12",
                "2026-05-13",
                "2026-05-14",
                "2026-05-15",
            ],
        )
        save.assert_called_once_with("20260515", ai_result)


class EmotionIntradayRefreshTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(emotion_cycle_bp)
        self.client = self.app.test_client()

    def test_intraday_refresh_saves_separate_field(self):
        records = [
            {"date": "2026-05-14", "limit_up_count": 40},
            {"date": "2026-05-15", "limit_up_count": 35},
        ]
        cycle_anchor = {"stage": "退潮期", "analysis": "锚点", "advice": "轻仓"}
        intraday_result = {
            "date": "2026-05-15",
            "stage": "退潮期",
            "analysis": "盘中分歧加大",
            "advice": "观望",
            "recommendations": [],
        }

        with patch("routes.emotion_cycle._fetch_emotion_records", return_value=records):
            with patch("routes.emotion_cycle._get_analysis_from_db", return_value=cycle_anchor):
                with patch(
                    "routes.emotion_cycle._call_claude_intraday",
                    return_value=intraday_result,
                ) as call_intraday:
                    with patch(
                        "routes.emotion_cycle._save_intraday_to_db",
                        return_value=True,
                    ) as save_intraday:
                        response = self.client.post(
                            "/api/v1/emotion-intraday-refresh",
                            headers=_auth_headers("user"),
                        )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["intraday"], intraday_result)
        self.assertEqual(payload["data"]["records"], records)
        call_intraday.assert_called_once()
        save_intraday.assert_called_once_with("20260515", intraday_result)

    def test_batch_storage_requires_admin(self):
        with patch("routes.emotion_cycle._call_claude_batch", return_value=[]):
            response = self.client.post(
                "/api/v1/emotion-analysis-with-storage",
                json={"records": [{"date": "2026-05-15"}]},
                headers=_auth_headers("user"),
            )
        self.assertEqual(response.status_code, 403)

        with patch("routes.emotion_cycle._call_claude_batch", return_value=[]):
            response = self.client.post(
                "/api/v1/emotion-analysis-with-storage",
                json={"records": [{"date": "2026-05-15"}]},
                headers=_auth_headers("admin"),
            )
        self.assertEqual(response.status_code, 200)


class AnalyzeOneDateTest(unittest.TestCase):
    def _records(self):
        return [
            {"date": f"2026-05-{day:02d}", "limit_up_count": day}
            for day in range(8, 16)
        ]

    def test_skips_when_already_in_db(self):
        from routes.emotion_cycle import analyze_one_date
        with patch(
            "routes.emotion_cycle._get_analysis_from_db",
            return_value={
                "stage": "退潮期",
                "analysis": "盘中情绪走弱",
                "advice": "控制仓位",
                "recommendations": [],
            },
        ):
            with patch("routes.emotion_cycle._call_claude_batch") as call_ai:
                with patch("routes.emotion_cycle._save_analysis_to_db") as save:
                    status = analyze_one_date("20260515", self._records())
        self.assertEqual(status, "skipped")
        call_ai.assert_not_called()
        save.assert_not_called()

    def test_uses_prior_five_days_as_context_and_saves(self):
        from routes.emotion_cycle import analyze_one_date
        ai_result = {
            "date": "2026-05-15",
            "stage": "退潮期",
            "analysis": "走弱",
            "advice": "轻仓",
            "recommendations": [],
        }
        with patch("routes.emotion_cycle._get_analysis_from_db", return_value=None):
            with patch(
                "routes.emotion_cycle._call_claude_batch",
                return_value=[ai_result],
            ) as call_ai:
                with patch(
                    "routes.emotion_cycle._save_analysis_to_db",
                    return_value=True,
                ) as save:
                    status = analyze_one_date("20260515", self._records())
        self.assertEqual(status, "saved")
        analyzed = call_ai.call_args.args[0]
        self.assertEqual(
            [r["date"] for r in analyzed],
            ["2026-05-10", "2026-05-11", "2026-05-12",
             "2026-05-13", "2026-05-14", "2026-05-15"],
        )
        save.assert_called_once_with("20260515", ai_result)

    def test_returns_failed_when_target_missing_in_ai_result(self):
        from routes.emotion_cycle import analyze_one_date
        with patch("routes.emotion_cycle._get_analysis_from_db", return_value=None):
            with patch(
                "routes.emotion_cycle._call_claude_batch",
                return_value=[{"date": "2026-05-14", "stage": "退潮期"}],
            ):
                with patch("routes.emotion_cycle._save_analysis_to_db") as save:
                    status = analyze_one_date("20260515", self._records())
        self.assertEqual(status, "failed")
        save.assert_not_called()

    def test_force_true_bypasses_db_skip(self):
        from routes.emotion_cycle import analyze_one_date
        ai_result = {"date": "2026-05-15", "stage": "退潮期"}
        with patch(
            "routes.emotion_cycle._get_analysis_from_db",
            return_value={"stage": "旧"},
        ):
            with patch(
                "routes.emotion_cycle._call_claude_batch",
                return_value=[ai_result],
            ):
                with patch(
                    "routes.emotion_cycle._save_analysis_to_db",
                    return_value=True,
                ) as save:
                    status = analyze_one_date(
                        "20260515", self._records(), force=True
                    )
        self.assertEqual(status, "saved")
        save.assert_called_once_with("20260515", ai_result)

    def test_re_analyzes_when_db_has_placeholder(self):
        """DB 有占位符（待生成）时应该重新分析，不跳过"""
        from routes.emotion_cycle import analyze_one_date
        ai_result = {
            "date": "2026-05-15",
            "stage": "退潮期",
            "analysis": "real analysis",
            "advice": "control",
            "recommendations": [],
        }
        with patch(
            "routes.emotion_cycle._get_analysis_from_db",
            return_value={"stage": "待生成"},
        ) as mock_get:
            with patch(
                "routes.emotion_cycle._call_claude_batch",
                return_value=[ai_result],
            ) as mock_claude:
                with patch(
                    "routes.emotion_cycle._save_analysis_to_db",
                    return_value=True,
                ) as mock_save:
                    status = analyze_one_date("20260515", self._records(), force=False)
        self.assertEqual(status, "saved")
        mock_claude.assert_called_once()  # 应该被调用，而不是跳过
        mock_save.assert_called_once_with("20260515", ai_result)


if __name__ == "__main__":
    unittest.main()
