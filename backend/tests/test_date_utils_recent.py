import unittest
from unittest.mock import patch

from utils.date_utils import get_recent_trading_dates


class GetRecentTradingDatesTest(unittest.TestCase):
    @patch("utils.date_utils.get_valid_trading_date")
    def test_returns_five_dates_oldest_first(self, mock_valid):
        mock_valid.side_effect = [
            "2026-05-17",
            "2026-05-16",
            "2026-05-15",
            "2026-05-14",
            "2026-05-13",
            "2026-05-12",
        ]
        dates = get_recent_trading_dates(5)
        self.assertEqual(
            dates,
            ["20260513", "20260514", "20260515", "20260516", "20260517"],
        )


if __name__ == "__main__":
    unittest.main()
