import unittest
import types
from unittest.mock import patch

from flask import Flask

from services.data_source_adapter import DataSourceAdapter
from services.eastmoney_free import EastMoneyFreeSource
from routes.stock_other import (
    build_limit_up_theme_summary,
    stock_other_bp,
    _build_market_sentiment_from_emotion,
    _resolve_echelon_theme,
    _apply_echelon_theme_to_data,
)


class FakeSource:
    def __init__(self):
        self.timeshare_calls = []

    def get_realtime_quote(self, code):
        return {
            'code': code,
            'name': '测试股票',
            'price': 10.8,
            'yesterday_close': 10.0,
            'open': 10.1,
            'high': 11.0,
            'low': 9.9,
            'volume': 100000,
            'turnover': 1080000,
            'change_percent': 8.0,
        }

    def get_tick_details(self, code, dt=None):
        return {
            'details': [
                {'time': '09:31:02', 'price': 10.1, 'volume': 400, 'amount': 404000, 'type': 1},
                {'time': '09:32:08', 'price': 10.2, 'volume': 1200, 'amount': 1224000, 'type': 2},
                {'time': '10:15:30', 'price': 10.5, 'volume': 3200, 'amount': 3360000, 'type': 1},
                {'time': '14:55:01', 'price': 10.8, 'volume': 800, 'amount': 864000, 'type': 2},
            ],
            'pos': 0,
        }

    def get_timeshare(self, code, dt=None):
        self.timeshare_calls.append(dt)
        return [
            {'time': '09:30', 'price': 10.0, 'avg_price': 10.0, 'volume': 100, 'amount': 100000.0},
            {'time': '09:31', 'price': 10.2, 'avg_price': 10.1, 'volume': 1500, 'amount': 1530000.0},
        ]

    def get_daily_kline(self, code, dt):
        return {
            'open': 10.0,
            'close': 10.2,
            'high': 10.4,
            'low': 9.9,
            'volume': 10000,
            'turnover': 10200000,
            'preclose': 9.8,
            'change_percent': 4.08,
        }

    def get_order_book(self, code):
        return {
            'bids': [
                {'level': 1, 'price': 10.19, 'volume': 1200, 'amount': 1222800.0},
                {'level': 2, 'price': 10.18, 'volume': 800, 'amount': 814400.0},
            ],
            'asks': [
                {'level': 1, 'price': 10.21, 'volume': 600, 'amount': 612600.0},
                {'level': 2, 'price': 10.22, 'volume': 500, 'amount': 511000.0},
            ],
            'spread': 0.02,
            'bid_amount': 2037200.0,
            'ask_amount': 1123600.0,
        }

    def infer_direction(self, buy_sell_type):
        return {1: '主买', 2: '主卖', 4: '中性'}.get(buy_sell_type, '中性')



class EmptyHistoryTickSource(FakeSource):
    def get_tick_details(self, code, dt=None):
        return {'details': [], 'pos': 0}


class QuoteFailureSource(FakeSource):
    def get_realtime_quote(self, code):
        return None


class LimitUpQuoteFailureSource(QuoteFailureSource):
    def get_daily_kline(self, code, dt):
        return None


class HolidayFallbackSource(FakeSource):
    def get_timeshare(self, code, dt=None):
        self.timeshare_calls.append(dt)
        if dt == '2026-05-01':
            return []
        return super().get_timeshare(code, dt=dt)


class FastHistoricalTimeshareSource(FakeSource):
    def get_realtime_quote(self, code):
        raise AssertionError('historical lightweight timeshare should not wait for realtime quote')

    def get_order_book(self, code):
        raise AssertionError('historical lightweight timeshare should not wait for order book')


class DataSourceAdapterAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.adapter = DataSourceAdapter(use_l2=False)
        self.fake_source = FakeSource()
        self.adapter.source = self.fake_source
        self.adapter.source_name = 'fake'

    def test_big_map_uses_all_large_orders_grouped_on_price_minutes(self):
        result = self.adapter._build_dashboard('000001', dt='2026-05-01')

        big_map = result['data']['big_map']
        self.assertEqual(len(result['data']['large_orders']), 4)
        self.assertEqual(set(big_map.keys()), {'09:31', '09:32', '10:15', '14:55'})
        self.assertEqual(big_map['10:15'][0]['amount'], 336.0)
        self.assertEqual(big_map['10:15'][0]['price'], 10.5)
        self.assertEqual(big_map['10:15'][0]['type'], '主买')
        self.assertEqual(result['data']['order_book']['bids'][0]['price'], 10.19)
        self.assertGreater(result['data']['order_book']['bid_amount'], result['data']['order_book']['ask_amount'])

    def test_simulated_dashboard_only_returns_data_up_to_simulate_time(self):
        result = self.adapter._build_dashboard('000001', dt='2026-05-01', simulate_time='09:31')

        self.assertEqual([p['time'] for p in result['data']['timeshare']], ['09:30', '09:31'])
        self.assertEqual([o['time'] for o in result['data']['large_orders']], ['09:31:02'])
        self.assertEqual(set(result['data']['big_map'].keys()), {'09:31'})
        self.assertTrue(result['data']['simulation']['enabled'])
        self.assertEqual(result['data']['simulation']['simulate_time'], '09:31')

    def test_dashboard_uses_fallback_quote_when_realtime_quote_fails(self):
        self.adapter.source = QuoteFailureSource()

        result = self.adapter._build_dashboard('000001', dt='2026-05-01')

        self.assertTrue(result['success'])
        self.assertEqual(result['data']['stock_info']['price'], 10.2)
        self.assertEqual(result['data']['stock_info']['yesterday_close'], 9.8)

    def test_limit_up_quote_infers_previous_close_from_change_percent(self):
        quote = self.adapter._get_limit_up_quote('603399', '2026-04-30')

        if quote is None:
            self.skipTest('涨停池接口当前不可用')

        self.assertEqual(quote['price'], 19.39)
        self.assertLess(quote['yesterday_close'], quote['price'])
        self.assertGreater(quote['change_percent'], 9)

    def test_dashboard_preserves_limit_up_fallback_quote_for_historical_timeshare(self):
        self.adapter.source = LimitUpQuoteFailureSource()
        self.adapter._get_limit_up_quote = lambda code, dt: {
            'code': code,
            'name': '涨停测试',
            'price': 11.0,
            'yesterday_close': 10.0,
            'open': 11.0,
            'high': 11.0,
            'low': 11.0,
            'volume': 0,
            'turnover': 0,
            'change_percent': 10.0,
        }

        result = self.adapter._build_dashboard('000001', dt='2026-04-30')

        self.assertEqual(result['data']['stock_info']['yesterday_close'], 10.0)
        self.assertEqual(result['data']['stock_info']['change_percent'], 10.0)

    def test_statistics_tracks_neutral_orders_without_counting_as_sell(self):
        details = [
            {'time': '09:31:02', 'price': 10.1, 'volume': 400, 'amount': 404000, 'direction': '中性'},
            {'time': '09:32:08', 'price': 10.2, 'volume': 1200, 'amount': 1224000, 'direction': '被卖'},
        ]

        stats = self.adapter._calculate_statistics(details)

        self.assertEqual(stats['above_30']['neutral_count'], 1)
        self.assertEqual(stats['above_30']['neutral_amount'], 40.4)
        self.assertEqual(stats['above_30']['sell_count'], 0)
        self.assertEqual(stats['above_100']['sell_count'], 1)

    def test_neutral_ticks_are_inferred_to_buy_or_sell_for_chart_display(self):
        details = [
            {'time': '09:31:00', 'price': 10.00, 'volume': 100, 'amount': 100000, 'type': 1},
            {'time': '09:32:00', 'price': 10.10, 'volume': 400, 'amount': 404000, 'type': 4},
            {'time': '09:33:00', 'price': 10.05, 'volume': 400, 'amount': 402000, 'type': 4},
        ]

        self.adapter._annotate_directions(details)

        self.assertEqual([d['direction'] for d in details], ['主买', '被买', '被卖'])

    def test_history_dashboard_falls_back_to_minute_amount_orders_when_ticks_empty(self):
        adapter = DataSourceAdapter(use_l2=False)
        adapter.source = EmptyHistoryTickSource()
        adapter.source_name = 'fake'

        result = adapter._build_dashboard('000001', dt='2026-04-30')

        orders = result['data']['large_orders']
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['time'], '09:31')
        self.assertEqual(orders[0]['direction'], '被买')
        self.assertEqual(orders[0]['amount'], 153.0)
        self.assertEqual(result['data']['big_map']['09:31'][0]['amount'], 153.0)

    def test_historical_lightweight_timeshare_skips_realtime_quote_and_order_book(self):
        adapter = DataSourceAdapter(use_l2=False)
        adapter.source = FastHistoricalTimeshareSource()
        adapter.source_name = 'fake'
        adapter._get_fallback_stock_name = lambda code: '测试股票'

        result = adapter._build_timeshare('000001', dt='2026-05-15')

        self.assertTrue(result['success'])
        self.assertEqual(len(result['data']['timeshare']), 2)
        self.assertEqual(result['data']['stock_info']['price'], 10.2)
        self.assertEqual(result['data']['stock_info']['yesterday_close'], 9.8)
        self.assertEqual(result['data']['stock_info']['change_percent'], 4.08)
        self.assertEqual(result['data']['order_book']['source'], 'empty')
        self.assertEqual(result['data']['session_snapshot'], {})

    def test_chart_stock_info_uses_trends2_pre_close(self):
        adapter = DataSourceAdapter(use_l2=False)
        timeshare = [
            {'time': '09:31', 'price': 10.0, 'volume': 100, 'amount': 100000},
            {'time': '09:32', 'price': 10.5, 'volume': 200, 'amount': 210000},
        ]
        info = adapter._chart_stock_info_from_timeshare(
            '000001', timeshare, {'pre_close': 9.8, 'name': '平安银行'},
        )
        self.assertEqual(info['yesterday_close'], 9.8)
        self.assertEqual(info['price'], 10.5)
        self.assertEqual(info['name'], '平安银行')
        self.assertAlmostEqual(info['change_percent'], 7.14, places=1)

    def test_timeshare_mismatch_detects_stale_trends2(self):
        adapter = DataSourceAdapter(use_l2=False)
        stale_ts = [{'time': '09:31', 'price': 39.44, 'volume': 100, 'amount': 100000}]
        quote = {'price': 48.17, 'yesterday_close': 49.39}
        self.assertTrue(adapter._timeshare_mismatch_with_quote(stale_ts, quote))
        good_ts = [{'time': '09:31', 'price': 48.0, 'volume': 100, 'amount': 100000}]
        self.assertFalse(adapter._timeshare_mismatch_with_quote(good_ts, quote))

    def test_timeshare_looks_flat_detects_stuck_trends2(self):
        adapter = DataSourceAdapter(use_l2=False)
        flat_ts = [{'time': f'10:{i:02d}', 'price': 38.19, 'volume': 100, 'amount': 100000}
                   for i in range(40)]
        varied_ts = flat_ts + [{'time': '11:00', 'price': 39.0, 'volume': 100, 'amount': 100000}]
        self.assertTrue(adapter._timeshare_looks_flat(flat_ts))
        self.assertFalse(adapter._timeshare_looks_flat(varied_ts))

    def test_maybe_refresh_timeshare_uses_playwright_fallback(self):
        adapter = DataSourceAdapter(use_l2=False)
        stale_ts = [{'time': '09:31', 'price': 39.44, 'volume': 100, 'amount': 100000}]
        good_ts = [
            {'time': '09:31', 'price': 48.0, 'volume': 100, 'amount': 100000},
            {'time': '09:32', 'price': 48.2, 'volume': 120, 'amount': 120000},
        ]
        quote = {'price': 48.17, 'yesterday_close': 49.39}

        class FakePw:
            def get_timeshare(self, code, dt=None):
                return good_ts

        with patch('services.data_source_adapter._get_playwright_source', return_value=FakePw()):
            refreshed = adapter._maybe_refresh_timeshare('002741', '2026-06-17', stale_ts, quote)

        self.assertEqual(refreshed[-1]['price'], 48.2)

if __name__ == '__main__':
    unittest.main()


class EastMoneyFreeSourceParseTest(unittest.TestCase):
    def test_parse_trend_item_uses_volume_and_average_price_fields(self):
        item = '2026-04-30 09:31,11.46,11.56,11.56,11.46,48413,55725414.00,11.509'

        parsed = EastMoneyFreeSource.parse_trend_item(item)

        self.assertEqual(parsed['time'], '09:31')
        self.assertEqual(parsed['price'], 11.46)
        self.assertEqual(parsed['volume'], 48413)
        self.assertEqual(parsed['amount'], 55725414.0)
        self.assertEqual(parsed['avg_price'], 11.509)

    def test_parse_trends2_response_extracts_pre_close(self):
        source = EastMoneyFreeSource()
        payload = {
            'rc': 0,
            'data': {
                'prePrice': 21.09,
                'name': '宏昌电子',
                'trends': [
                    '2026-06-17 09:31,21.50,21.50,21.50,21.50,1000,2150000.00,21.50',
                ],
            },
        }
        parsed = source._parse_trends2_response(payload)
        self.assertEqual(parsed['pre_close'], 21.09)
        self.assertEqual(parsed['name'], '宏昌电子')
        self.assertEqual(len(parsed['timeshare']), 1)

    def test_akshare_minute_fallback_filters_target_date(self):
        rows = EastMoneyFreeSource._build_timeshare_from_minute_records([
            {'day': '2026-05-14 15:00:00', 'close': 10.8, 'volume': 1000},
            {'day': '2026-05-15 09:31:00', 'close': 11.03, 'volume': 4536800},
            {'day': '2026-05-15 09:32:00', 'close': 11.04, 'volume': 1718400},
        ], '2026-05-15')

        self.assertEqual([row['time'] for row in rows], ['09:31', '09:32'])
        self.assertEqual(rows[0]['price'], 11.03)
        self.assertEqual(rows[0]['volume'], 45368)
        self.assertGreater(rows[1]['avg_price'], rows[0]['avg_price'])

    def test_history_timeshare_prefers_akshare_minute_source(self):
        source = EastMoneyFreeSource()
        expected_rows = [{'time': '09:31', 'price': 11.03, 'volume': 45368, 'amount': 50040904.0, 'avg_price': 11.03}]
        source._get_minute_timeshare_akshare = lambda code, dt: expected_rows

        with patch('services.eastmoney_free._safe_request') as eastmoney_request:
            eastmoney_request.return_value = None
            rows = source._get_history_timeshare('000001', '2026-05-15')

        eastmoney_request.assert_not_called()
        self.assertEqual(rows, expected_rows)

    def test_daily_kline_falls_back_to_tencent_and_resolves_latest_trading_day(self):
        """东财日K不可达 + 请求日为周末时，用腾讯日K回退并取≤dt的最近交易日，
        昨收必须是上一交易日收盘价（修复涨停板被画成 0% 的根因）。"""
        source = EastMoneyFreeSource()
        tencent_payload = {
            'code': 0,
            'data': {
                'sh600578': {
                    'day': [
                        ['2026-05-13', '5.45', '5.79', '5.79', '5.41', '100'],
                        ['2026-05-14', '6.37', '6.37', '6.37', '6.10', '100'],
                        ['2026-05-15', '6.50', '7.01', '7.01', '5.88', '100'],
                    ]
                }
            },
        }

        def fake_fetch(url, headers=None, cookies=None, timeout=10):
            if 'gtimg.cn' in url:
                return tencent_payload
            return None  # 东财 push2his 不可达

        with patch('services.eastmoney_free._safe_request', return_value=None), \
             patch('services.eastmoney_free._subprocess_fetch_json', side_effect=fake_fetch):
            # 2026-05-17 是周日，必须回退到最近交易日 2026-05-15
            kline = source.get_daily_kline('600578', '2026-05-17')

        self.assertIsNotNone(kline)
        self.assertEqual(kline['preclose'], 6.37)
        self.assertEqual(kline['close'], 7.01)
        self.assertEqual(kline['open'], 6.50)
        self.assertEqual(kline['high'], 7.01)
        self.assertEqual(kline['low'], 5.88)
        self.assertAlmostEqual(kline['change_percent'], 10.05, places=1)


class LimitUpThemeSummaryTest(unittest.TestCase):
    def test_groups_limit_up_stocks_by_theme_and_marks_current_stock(self):
        rows = [
            {'代码': '000001', '名称': '平安银行', '最新价': 11.49, '所属行业': '银行', '涨停统计': '1/1', '连板数': 1, '封板资金': 1000},
            {'代码': '600000', '名称': '浦发银行', '最新价': 10.0, '所属行业': '银行', '涨停统计': '1/1', '连板数': 1, '封板资金': 800},
            {'代码': '000002', '名称': '万科A', '最新价': 9.0, '所属行业': '房地产', '涨停统计': '1/1', '连板数': 1, '封板资金': 300},
        ]

        result = build_limit_up_theme_summary(rows, '000001')

        self.assertEqual(result['current_theme'], '银行')
        self.assertEqual(result['current_theme_count'], 2)
        self.assertEqual(result['themes'][0]['theme'], '银行')
        self.assertEqual(result['themes'][0]['count'], 2)

    def test_limit_up_themes_falls_back_when_theme_tables_are_missing(self):
        app = Flask(__name__)
        app.register_blueprint(stock_other_bp)

        fake_ak = types.SimpleNamespace(
            stock_zt_pool_em=lambda date: FakeDataFrame([
                {'代码': '000001', '名称': '平安银行', '最新价': 11.49, '所属行业': '银行', '涨停统计': '1/1', '连板数': 1, '封板资金': 1000},
            ]),
            stock_zt_pool_dtgc_em=lambda date: FakeDataFrame([]),
        )

        with patch.dict('sys.modules', {'akshare': fake_ak}):
            with patch('services.theme_service.get_limit_up_stocks_by_date', side_effect=Exception("Table 'stock.limit_up_stocks' doesn't exist")):
                response = app.test_client().get('/api/v1/limit_up_themes?code=000001&dt=2026-05-15')

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['code'], 200)
        self.assertEqual(payload['data']['data_source'], 'akshare.stock_zt_pool_em')
        self.assertEqual(payload['data']['current_theme'], '银行')


class MarketSentimentFromEmotionTest(unittest.TestCase):
    @patch('routes.stock_other._get_emotion_stage', return_value='升温期')
    @patch('routes.limit_up_echelon._get_emotion_record')
    def test_uses_emotion_cycle_limit_counts(self, mock_record, _mock_stage):
        mock_record.return_value = {'limit_up_count': 54, 'limit_down_count': 0}
        sentiment = _build_market_sentiment_from_emotion('20260515')
        self.assertEqual(sentiment['limit_up_count'], 54)
        self.assertEqual(sentiment['limit_down_count'], 0)
        self.assertEqual(sentiment['sentiment_label'], '偏强')
        self.assertEqual(sentiment['emotion_stage'], '升温期')


class EchelonThemeResolveTest(unittest.TestCase):
    @patch('services.theme_service.load_echelon_from_db')
    def test_in_pool_stock_gets_echelon_tag(self, mock_load):
        mock_load.return_value = {
            'stocks': [{'code': '600578', 'tag_name': '电力', 'name': '京能电力'}],
            'theme_ranking': [{'theme': '电力', 'count': 4}],
        }
        resolved = _resolve_echelon_theme('600578', '20260515')
        self.assertEqual(resolved['echelon_theme'], '电力')
        self.assertEqual(resolved['echelon_theme_count'], 4)
        self.assertTrue(resolved['in_limit_up_pool'])

    @patch('services.theme_service.load_echelon_from_db')
    def test_off_pool_stock_matches_industry_to_echelon(self, mock_load):
        mock_load.return_value = {
            'stocks': [{'code': '601991', 'tag_name': '电力', 'name': '大唐发电'}],
            'theme_ranking': [{'theme': '电力', 'count': 4}],
        }
        resolved = _resolve_echelon_theme('600578', '20260515', industry='电力')
        self.assertEqual(resolved['echelon_theme'], '电力')
        self.assertEqual(resolved['echelon_theme_count'], 4)
        self.assertFalse(resolved['in_limit_up_pool'])

    @patch('routes.stock_other._resolve_echelon_theme')
    def test_apply_updates_current_theme_fields(self, mock_resolve):
        mock_resolve.return_value = {
            'echelon_theme': '电力',
            'echelon_theme_count': 4,
            'in_limit_up_pool': False,
        }
        data = {'current_stock': {'code': '600578', 'name': '京能电力'}, 'current_theme': '', 'current_theme_count': 0}
        out = _apply_echelon_theme_to_data(data, '600578', '20260515', '电力')
        self.assertEqual(out['current_theme'], '电力')
        self.assertEqual(out['current_theme_count'], 4)
        self.assertIn('涨停梯队', out['current_stock']['reason'])


class FakeDataFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        if orient != 'records':
            raise ValueError(f'unsupported orient: {orient}')
        return self._rows

    def __len__(self):
        return len(self._rows)
