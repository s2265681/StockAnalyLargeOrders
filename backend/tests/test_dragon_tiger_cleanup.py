import unittest
from unittest.mock import patch

from services.dragon_tiger_service import cleanup_dragon_tiger_older_than


class DragonTigerCleanupTest(unittest.TestCase):
    @patch("services.dragon_tiger_service.execute_write")
    def test_cleanup_deletes_three_tables(self, mock_write):
        mock_write.return_value = 2
        result = cleanup_dragon_tiger_older_than(days=7)

        self.assertEqual(len(result["cutoff"]), 8)
        self.assertEqual(mock_write.call_count, 3)
        cutoffs = {call.args[1][0] for call in mock_write.call_args_list}
        self.assertEqual(len(cutoffs), 1)
        self.assertEqual(result["cutoff"], cutoffs.pop())
        self.assertEqual(
            set(result["deleted"].keys()),
            {"dragon_tiger_ai", "dragon_tiger_seats", "dragon_tiger_daily"},
        )


if __name__ == "__main__":
    unittest.main()
