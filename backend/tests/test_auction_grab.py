import unittest
from unittest.mock import patch

from routes import auction_grab
from services.eastmoney_free import EastMoneyFreeSource


class AuctionGrabDailyChangeTest(unittest.TestCase):
    def setUp(self):
        auction_grab._kline_cache.clear()

    def test_enrich_uses_simple_daily_change_fallback_when_daily_kline_is_empty(self):
        class FakeSource:
            def get_daily_kline(self, code, dt):
                return None

            def get_daily_change_percent(self, code, dt):
                return {
                    ('002309', '2026-05-14'): 10.0,
                    ('002309', '2026-05-15'): -10.06,
                }.get((code, dt))

        items = [{'code': '002309', 'name': '中利集团'}]

        with patch('routes.auction_grab.EastMoneyFreeSource', return_value=FakeSource()):
            auction_grab._enrich_close_and_next_change(items, '2026-05-14')

        self.assertEqual(items[0]['close_change_pct'], 10.0)
        self.assertEqual(items[0]['next_day_change_pct'], -10.06)

    @patch('services.eastmoney_free._subprocess_fetch_json')
    def test_tencent_daily_change_calculates_target_close_against_previous_close(self, fetch_json):
        fetch_json.return_value = {
            'code': 0,
            'data': {
                'sz002309': {
                    'qfqday': [
                        ['2026-05-13', '4.600', '4.700', '4.800', '4.560', '4398306.000'],
                        ['2026-05-14', '5.170', '5.170', '5.170', '5.170', '1193124.000'],
                    ]
                }
            },
        }

        value = EastMoneyFreeSource().get_daily_change_percent('002309', '2026-05-14')

        self.assertEqual(value, 10.0)


if __name__ == '__main__':
    unittest.main()
