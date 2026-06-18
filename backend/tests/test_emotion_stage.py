import unittest

from utils.emotion_stage import calibrate_analysis_stage, infer_stage_from_metrics


def _row(date, zt, dt, lb, zxgd, drqx, dmqx, dbcgl):
    return {
        "date": date,
        "limit_up_count": zt,
        "limit_down_count": dt,
        "consec_limit": lb,
        "latest_height": zxgd,
        "big_profit_mood": drqx,
        "big_loss_mood": dmqx,
        "board_hit_rate": dbcgl,
    }


class InferStageFromMetricsTest(unittest.TestCase):
    def test_20260615_is_climax_at_peak(self):
        ctx = [
            _row("2026-06-10", 70, 22, 15, 4, 53, 16, 59.69),
            _row("2026-06-11", 69, 32, 11, 3, 54, 19, 51.43),
            _row("2026-06-12", 90, 16, 10, 4, 66, 14, 71.01),
        ]
        today = _row("2026-06-15", 144, 3, 11, 3, 102, 2, 64.44)
        self.assertEqual(infer_stage_from_metrics(today, ctx), "高潮期")

    def test_20260616_downgraded_after_peak_drop(self):
        ctx = [
            _row("2026-06-10", 70, 22, 15, 4, 53, 16, 59.69),
            _row("2026-06-11", 69, 32, 11, 3, 54, 19, 51.43),
            _row("2026-06-12", 90, 16, 10, 4, 66, 14, 71.01),
            _row("2026-06-15", 144, 3, 11, 3, 102, 2, 64.44),
        ]
        today = _row("2026-06-16", 117, 7, 29, 4, 92, 2, 83.33)
        self.assertEqual(infer_stage_from_metrics(today, ctx), "升温期")

    def test_20260617_not_climax(self):
        ctx = [
            _row("2026-06-12", 90, 16, 10, 4, 66, 14, 71.01),
            _row("2026-06-15", 144, 3, 11, 3, 102, 2, 64.44),
            _row("2026-06-16", 117, 7, 29, 4, 92, 2, 83.33),
        ]
        today = _row("2026-06-17", 86, 1, 19, 3, 80, 2, 58.97)
        self.assertEqual(infer_stage_from_metrics(today, ctx), "升温期")


class CalibrateAnalysisStageTest(unittest.TestCase):
    def test_downgrades_ai_climax_when_metrics_cooling(self):
        ctx = [_row("2026-06-15", 144, 3, 11, 3, 102, 2, 64.44)]
        today = _row("2026-06-16", 117, 7, 29, 4, 92, 2, 83.33)
        analysis = {"stage": "高潮期", "analysis": "市场极度亢奋", "advice": "持股"}
        result = calibrate_analysis_stage(analysis, today, ctx)
        self.assertEqual(result["stage"], "升温期")


if __name__ == "__main__":
    unittest.main()
