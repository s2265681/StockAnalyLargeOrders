import json
import unittest
from unittest.mock import patch, MagicMock


SINA_SAMPLE_NEW = (
    'var hq_str_gb_dji="道琼斯,49363.88,-0.65,2026-05-20 04:46:24";\n'
    'var hq_str_gb_ixic="纳斯达克,25870.71,-0.84,2026-05-20 09:49:03";\n'
    'var hq_str_gb_inx="标普500指数,7353.61,-0.67,2026-05-20 04:46:04";\n'
    'var hq_str_rt_hkHSI="HSI,恒生指数,25709.62,25797.85,25713.53,25555.06,25651.12,-146.73,-0.57";\n'
    'var hq_str_gb_nikkei="";\n'
)

SINA_SAMPLE_EMPTY_LEGACY = (
    'var hq_str_b_INDEXDOW="";\nvar hq_str_b_INDEXNASDAQ="";\n'
)


class TestParseSinaResponse(unittest.TestCase):
    def test_parses_new_symbols(self):
        from services.market_brief_service import _parse_sina_response
        result = _parse_sina_response(SINA_SAMPLE_NEW)
        self.assertGreaterEqual(len(result), 4)
        dow = next(r for r in result if r['name'] == '道指')
        self.assertAlmostEqual(dow['change_pct'], -0.65)
        hk = next(r for r in result if r['name'] == '恒指')
        self.assertAlmostEqual(hk['change_pct'], -0.57)

    def test_empty_legacy_raises(self):
        from services.market_brief_service import _parse_sina_response
        with self.assertRaises(RuntimeError):
            _parse_sina_response(SINA_SAMPLE_EMPTY_LEGACY)


class TestMarketBriefFetchers(unittest.TestCase):
    def test_format_news_for_prompt(self):
        from services.market_brief_fetchers import format_news_for_prompt
        text = format_news_for_prompt([
            {'source': '同花顺', 'title': '测试标题', 'time': '10:00'},
        ])
        self.assertIn('同花顺', text)
        self.assertIn('测试标题', text)

    def test_fetch_overseas_eastmoney_parse(self):
        from services.market_brief_fetchers import _fetch_overseas_eastmoney
        em_json = json.dumps({
            'data': {'diff': [
                {'f12': 'DJIA', 'f14': '道琼斯', 'f2': 1, 'f3': 0.1},
                {'f12': 'NDX', 'f14': '纳斯达克', 'f2': 2, 'f3': 0.2},
                {'f12': 'SPX', 'f14': '标普500', 'f2': 3, 'f3': 0.3},
                {'f12': 'HSI', 'f14': '恒生指数', 'f2': 4, 'f3': -0.1},
                {'f12': 'N225', 'f14': '日经225', 'f2': 5, 'f3': 1.0},
            ]}
        })
        with patch('services.market_brief_fetchers._curl_get', return_value=em_json):
            rows = _fetch_overseas_eastmoney()
        self.assertEqual(len(rows), 5)


class TestMarketBriefEmail(unittest.TestCase):
    def test_build_email_body(self):
        from services.market_brief_service import build_market_brief_email_body
        body = build_market_brief_email_body(
            '2026-05-20',
            [{'name': '道指', 'change_pct': 0.5}],
            [{'source': '同花顺', 'title': '测试新闻', 'time': ''}],
            '【海外】美股偏强\n【关注】科技',
        )
        self.assertIn('盘前资讯', body)
        self.assertIn('道指', body)
        self.assertIn('同花顺', body)
        self.assertIn('AI 盘前摘要', body)


class TestGetTodayBrief(unittest.TestCase):
    def test_returns_none_when_no_row(self):
        with patch('services.market_brief_service.execute_query', return_value=[]):
            from services.market_brief_service import get_today_brief
            self.assertIsNone(get_today_brief())

    def test_returns_dict_when_row_exists(self):
        overseas = [{"symbol": "gb_dji", "name": "道指", "close": 34061.32, "change_pct": 0.35}]
        fake_row = {
            'brief_date': '2026-05-20',
            'overseas_json': json.dumps(overseas),
            'news_json': json.dumps([{'source': '同花顺', 'title': '测试'}]),
            'ai_summary': '美股上涨，关注芯片。',
            'generated_at': '2026-05-20 08:30:12',
        }
        with patch('services.market_brief_service.execute_query', return_value=[fake_row]):
            from services.market_brief_service import get_today_brief
            result = get_today_brief()
        self.assertIsNotNone(result)
        self.assertEqual(len(result['news']), 1)


class TestFetchOverseasIndices(unittest.TestCase):
    def test_curl_nonzero_raises(self):
        from services.market_brief_fetchers import fetch_overseas_indices
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b'connect failed'
        with patch('subprocess.run', return_value=mock_result):
            with self.assertRaises(RuntimeError):
                fetch_overseas_indices()


def _make_app():
    from utils.env import load_env
    load_env()
    import eventlet
    eventlet.monkey_patch()
    from flask import Flask
    from flask_cors import CORS
    app = Flask(__name__)
    CORS(app)
    from routes.market_brief import market_brief_bp
    app.register_blueprint(market_brief_bp)
    return app


class TestMarketBriefAPI(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.client = self.app.test_client()

    def test_today_returns_unavailable_when_no_data(self):
        with patch('services.market_brief_service.execute_query', return_value=[]):
            resp = self.client.get('/api/market-brief/today')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.data)
        self.assertFalse(body['data']['available'])

    def test_today_returns_data_when_available(self):
        overseas = [{"symbol": "gb_dji", "name": "道指", "close": 34061.32, "change_pct": 0.35}]
        fake_row = {
            'brief_date': '2026-05-20',
            'overseas_json': json.dumps(overseas),
            'news_json': '[]',
            'ai_summary': '美股上涨。',
            'generated_at': '2026-05-20 08:30:00',
        }
        with patch('services.market_brief_service.execute_query', return_value=[fake_row]):
            resp = self.client.get('/api/market-brief/today')
        body = json.loads(resp.data)
        self.assertTrue(body['data']['available'])


if __name__ == '__main__':
    unittest.main()
