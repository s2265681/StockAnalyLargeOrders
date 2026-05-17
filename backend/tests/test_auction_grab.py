import unittest
from unittest.mock import patch

from routes import auction_grab
from services.eastmoney_free import EastMoneyFreeSource


class AuctionGrabProcessedCacheTest(unittest.TestCase):
    def setUp(self):
        auction_grab._processed_cache.clear()

    def test_processed_cache_miss_returns_none_tuple(self):
        items, meta = auction_grab._get_processed_payload('20260515', 0, False)
        self.assertIsNone(items)
        self.assertIsNone(meta)

    def test_processed_cache_roundtrip(self):
        items = [{'code': '000001', 'recommend_stars': 2}]
        meta = {'stage': '修复期', 'hint': 'test'}

        auction_grab._set_processed_payload('20260515', 0, items, meta)
        loaded_items, loaded_meta = auction_grab._get_processed_payload('20260515', 0, False)

        self.assertEqual(loaded_meta, meta)
        self.assertEqual(loaded_items[0]['code'], '000001')
        loaded_items[0]['recommend_stars'] = 0
        self.assertEqual(items[0]['recommend_stars'], 2)

    def test_processed_cache_kept_when_codes_unchanged(self):
        items = [{'code': '000001', 'recommend_stars': 3}]
        auction_grab._set_processed_payload('20260515', 0, items, {'stage': '修复期'})
        auction_grab._invalidate_processed_if_codes_changed(
            '20260515', 0, [{'code': '000001', 'grab_order_amount': 99}]
        )
        loaded, _ = auction_grab._get_processed_payload('20260515', 0, False)
        self.assertEqual(loaded[0]['recommend_stars'], 3)

    def test_processed_cache_cleared_when_codes_changed(self):
        items = [{'code': '000001', 'recommend_stars': 3}]
        auction_grab._set_processed_payload('20260515', 0, items, {'stage': '修复期'})
        auction_grab._invalidate_processed_if_codes_changed(
            '20260515', 0, [{'code': '000002'}]
        )
        loaded, _ = auction_grab._get_processed_payload('20260515', 0, False)
        self.assertIsNone(loaded)


class AuctionGrabDailyChangeTest(unittest.TestCase):
    def setUp(self):
        auction_grab._kline_cache.clear()
        auction_grab._processed_cache.clear()

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
