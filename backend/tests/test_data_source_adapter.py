import unittest

from services.data_source_adapter import DataSourceAdapter
from services.eastmoney_free import EastMoneyFreeSource
from routes.stock_other import build_limit_up_theme_summary


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
        return {1: '被买', 2: '被卖', 4: '中性'}.get(buy_sell_type, '中性')


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
        self.assertEqual(big_map['10:15'][0]['type'], '被买')
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

        self.assertEqual([d['direction'] for d in details], ['被买', '被买', '被卖'])

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
