import unittest
from unittest.mock import patch

from flask import Flask

from routes.emotion_cycle import emotion_cycle_bp


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


if __name__ == "__main__":
    unittest.main()
