import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jobs import emotion_cycle_daily


class EmotionCycleDailyTest(unittest.TestCase):
    """测试 emotion_cycle_daily.py 每日任务"""

    @patch('jobs.emotion_cycle_daily.StockAPI')
    @patch('jobs.emotion_cycle_daily.analyze_one_date')
    def test_uses_stockapi_latest_trading_day_by_default(self, mock_analyze, mock_api_class):
        """默认使用 StockAPI 返回的最新交易日"""
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api
        mock_api.get_latest_trading_day.return_value = '20260515'
        mock_api.fetch_all_emotion_records.return_value = []
        mock_analyze.return_value = 'saved'

        emotion_cycle_daily.main(target_date=None, force=False)

        mock_api.get_latest_trading_day.assert_called_once()
        mock_analyze.assert_called_once()
        call_args = mock_analyze.call_args
        self.assertEqual(call_args[0][0], '20260515')  # target_dt

    @patch('jobs.emotion_cycle_daily.StockAPI')
    @patch('jobs.emotion_cycle_daily.analyze_one_date')
    def test_accepts_manual_target_date(self, mock_analyze, mock_api_class):
        """可以手动指定目标日期"""
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api
        mock_api.fetch_all_emotion_records.return_value = []
        mock_analyze.return_value = 'saved'

        emotion_cycle_daily.main(target_date='20260510', force=False)

        mock_api.get_latest_trading_day.assert_not_called()
        mock_analyze.assert_called_once()
        call_args = mock_analyze.call_args
        self.assertEqual(call_args[0][0], '20260510')

    @patch('jobs.emotion_cycle_daily.StockAPI')
    @patch('jobs.emotion_cycle_daily.analyze_one_date')
    def test_exits_nonzero_when_stockapi_fails(self, mock_analyze, mock_api_class):
        """StockAPI 拉取失败则 exit 非 0（cron 日志可见）"""
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api
        mock_api.get_latest_trading_day.side_effect = Exception("StockAPI error")

        with self.assertRaises(SystemExit) as cm:
            emotion_cycle_daily.main(target_date=None, force=False)

        self.assertNotEqual(cm.exception.code, 0)

    @patch('jobs.emotion_cycle_daily.StockAPI')
    @patch('jobs.emotion_cycle_daily.analyze_one_date')
    def test_exits_nonzero_when_analyze_fails(self, mock_analyze, mock_api_class):
        """analyze_one_date 返回 'failed' 则 exit 非 0"""
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api
        mock_api.get_latest_trading_day.return_value = '20260515'
        mock_api.fetch_all_emotion_records.return_value = []
        mock_analyze.return_value = 'failed'

        with self.assertRaises(SystemExit) as cm:
            emotion_cycle_daily.main(target_date=None, force=False)

        self.assertNotEqual(cm.exception.code, 0)

    @patch('jobs.emotion_cycle_daily.StockAPI')
    @patch('jobs.emotion_cycle_daily.analyze_one_date')
    def test_logs_skipped_when_already_analyzed(self, mock_analyze, mock_api_class):
        """如果 DB 已有该日分析则记录 skipped 但正常退出"""
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api
        mock_api.get_latest_trading_day.return_value = '20260515'
        mock_api.fetch_all_emotion_records.return_value = []
        mock_analyze.return_value = 'skipped'

        # Should not raise SystemExit
        emotion_cycle_daily.main(target_date=None, force=False)

        mock_analyze.assert_called_once()

    @patch('jobs.emotion_cycle_daily.StockAPI')
    @patch('jobs.emotion_cycle_daily.analyze_one_date')
    def test_passes_force_flag_to_analyze(self, mock_analyze, mock_api_class):
        """force=True 会传给 analyze_one_date"""
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api
        mock_api.get_latest_trading_day.return_value = '20260515'
        mock_api.fetch_all_emotion_records.return_value = []
        mock_analyze.return_value = 'saved'

        emotion_cycle_daily.main(target_date='20260515', force=True)

        call_args = mock_analyze.call_args
        self.assertTrue(call_args[1].get('force'))

    @patch('jobs.emotion_cycle_daily.StockAPI')
    @patch('jobs.emotion_cycle_daily.analyze_one_date')
    def test_exits_nonzero_when_fetch_emotion_records_fails(self, mock_analyze, mock_api_class):
        """fetch_all_emotion_records 失败则 exit 非 0"""
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api
        mock_api.get_latest_trading_day.return_value = '20260515'
        mock_api.fetch_all_emotion_records.side_effect = Exception("Fetch failed")

        with self.assertRaises(SystemExit) as cm:
            emotion_cycle_daily.main(target_date=None, force=False)

        self.assertNotEqual(cm.exception.code, 0)


class BackfillEmotionCycleTest(unittest.TestCase):
    """测试 backfill_emotion_cycle.py 回填任务"""

    @patch('jobs.backfill_emotion_cycle.time.sleep')
    @patch('jobs.backfill_emotion_cycle.analyze_one_date')
    @patch('jobs.backfill_emotion_cycle._fetch_emotion_records')
    def test_processes_records_reverse_chronologically(self, mock_fetch, mock_analyze, mock_sleep):
        """按日期从新到旧逆序遍历"""
        mock_fetch.return_value = [
            {'date': '2026-03-10', 'limit_up_count': 1},
            {'date': '2026-03-11', 'limit_up_count': 2},
            {'date': '2026-03-12', 'limit_up_count': 3},
        ]
        mock_analyze.side_effect = ['saved', 'skipped', 'saved']

        import jobs.backfill_emotion_cycle as backfill
        backfill.main(force=False)

        # 应该从最新的日期开始（2026-03-12）
        calls = mock_analyze.call_args_list
        self.assertEqual(calls[0][0][0], '20260312')  # 第一个调用应该是最新的
        self.assertEqual(calls[1][0][0], '20260311')
        self.assertEqual(calls[2][0][0], '20260310')  # 最后是最旧的

        # sleep 应该被调用两次（每日之间）
        self.assertEqual(mock_sleep.call_count, 2)


class BackfillEmotionDailyAnalysisTest(unittest.TestCase):
    """测试 backfill_emotion_daily_analysis.py 正序回填"""

    @patch('jobs.backfill_emotion_daily_analysis.time.sleep')
    @patch('jobs.backfill_emotion_daily_analysis.analyze_daily_one_date')
    @patch('jobs.backfill_emotion_daily_analysis._get_intraday_from_db')
    @patch('jobs.backfill_emotion_daily_analysis._fetch_emotion_records')
    def test_processes_oldest_first(self, mock_fetch, mock_get_db, mock_analyze, mock_sleep):
        mock_fetch.return_value = [
            {'date': '2026-03-10'},
            {'date': '2026-03-11'},
            {'date': '2026-03-12'},
        ]
        mock_get_db.return_value = None
        mock_analyze.side_effect = ['saved', 'saved', 'saved']

        import jobs.backfill_emotion_daily_analysis as backfill
        backfill.main(force=False)

        calls = mock_analyze.call_args_list
        self.assertEqual(calls[0][0][0], '20260310')
        self.assertEqual(calls[1][0][0], '20260311')
        self.assertEqual(calls[2][0][0], '20260312')


if __name__ == '__main__':
    unittest.main()
