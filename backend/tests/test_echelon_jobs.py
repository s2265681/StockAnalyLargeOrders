import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jobs import echelon_daily


class EchelonDailyTest(unittest.TestCase):
    @patch("jobs.echelon_daily.build_echelon_one_date", return_value="saved")
    @patch("jobs.echelon_daily.get_valid_trading_date", return_value="2026-05-15")
    def test_default_date_uses_latest_trading_day(self, _date, mock_build):
        with patch.object(sys, "argv", ["echelon_daily.py"]):
            echelon_daily.main()
        mock_build.assert_called_once_with("20260515", force=False)

    @patch("jobs.echelon_daily.build_echelon_one_date", return_value="saved")
    def test_force_flag(self, mock_build):
        with patch.object(sys, "argv", ["echelon_daily.py", "force"]):
            with patch("jobs.echelon_daily.get_valid_trading_date", return_value="2026-05-15"):
                echelon_daily.main()
        mock_build.assert_called_once_with("20260515", force=True)

    @patch("jobs.echelon_daily.build_echelon_one_date", return_value="failed")
    def test_exits_nonzero_on_failed(self, mock_build):
        with patch.object(sys, "argv", ["echelon_daily.py", "20260515", "force"]):
            with self.assertRaises(SystemExit) as cm:
                echelon_daily.main()
        self.assertEqual(cm.exception.code, 1)
        mock_build.assert_called_once_with("20260515", force=True)


if __name__ == "__main__":
    unittest.main()
