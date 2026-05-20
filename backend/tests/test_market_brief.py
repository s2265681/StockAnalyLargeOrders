import json
import sys
import os
import unittest
from unittest.mock import patch


SINA_SAMPLE = (
    'var hq_str_b_INDEXDOW="道琼斯指数,34061.32,33941.54,119.78,0.35,0.35%,05/20/2026,16:01:08";\n'
    'var hq_str_b_INDEXNASDAQ="纳斯达克,13456.78,13338.81,117.97,0.88,0.88%,05/20/2026,16:01:08";\n'
    'var hq_str_b_INDEXSP="标准普尔500,4321.00,4293.93,27.07,0.63,0.63%,05/20/2026,16:01:08";\n'
    'var hq_str_b_INDEXHK="恒生指数,18234.56,18293.00,-58.44,-0.32,-0.32%,05/20/2026,16:02:00";\n'
    'var hq_str_b_INDEXNK225="日经225,33567.00,33058.14,508.86,1.54,1.54%,05/20/2026,15:30:00";\n'
)


class TestParseSinaResponse(unittest.TestCase):
    def test_parses_five_indices(self):
        from services.market_brief_service import _parse_sina_response
        result = _parse_sina_response(SINA_SAMPLE)
        self.assertEqual(len(result), 5)

    def test_dow_values(self):
        from services.market_brief_service import _parse_sina_response
        result = _parse_sina_response(SINA_SAMPLE)
        dow = next(r for r in result if r['symbol'] == 'b_INDEXDOW')
        self.assertEqual(dow['name'], '道指')
        self.assertAlmostEqual(dow['close'], 34061.32)
        self.assertAlmostEqual(dow['change_pct'], 0.35)

    def test_negative_change(self):
        from services.market_brief_service import _parse_sina_response
        result = _parse_sina_response(SINA_SAMPLE)
        hk = next(r for r in result if r['symbol'] == 'b_INDEXHK')
        self.assertLess(hk['change_pct'], 0)

    def test_empty_response_raises(self):
        from services.market_brief_service import _parse_sina_response
        with self.assertRaises(RuntimeError):
            _parse_sina_response("garbage text no match")


class TestGetTodayBrief(unittest.TestCase):
    def test_returns_none_when_no_row(self):
        with patch('services.market_brief_service.execute_query', return_value=[]):
            from services.market_brief_service import get_today_brief
            self.assertIsNone(get_today_brief())

    def test_returns_dict_when_row_exists(self):
        overseas = [{"symbol": "b_INDEXDOW", "name": "道指", "close": 34061.32, "change_pct": 0.35}]
        fake_row = {
            'brief_date': '2026-05-20',
            'overseas_json': json.dumps(overseas),
            'ai_summary': '美股上涨，关注芯片。',
            'generated_at': '2026-05-20 08:30:12',
        }
        with patch('services.market_brief_service.execute_query', return_value=[fake_row]):
            from services.market_brief_service import get_today_brief
            result = get_today_brief()
        self.assertTrue(result is not None)
        self.assertEqual(result['brief_date'], '2026-05-20')
        self.assertEqual(result['overseas'][0]['name'], '道指')
        self.assertEqual(result['ai_summary'], '美股上涨，关注芯片。')


class TestFetchOverseasIndices(unittest.TestCase):
    def test_curl_nonzero_raises(self):
        from unittest.mock import MagicMock
        from services.market_brief_service import fetch_overseas_indices
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = 'connect failed'
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
        self.assertTrue(body['success'])
        self.assertFalse(body['data']['available'])

    def test_today_returns_data_when_available(self):
        overseas = [{"symbol": "b_INDEXDOW", "name": "道指", "close": 34061.32, "change_pct": 0.35}]
        fake_row = {
            'brief_date': '2026-05-20',
            'overseas_json': json.dumps(overseas),
            'ai_summary': '美股上涨。',
            'generated_at': '2026-05-20 08:30:00',
        }
        with patch('services.market_brief_service.execute_query', return_value=[fake_row]):
            resp = self.client.get('/api/market-brief/today')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.data)
        self.assertTrue(body['data']['available'])
        self.assertEqual(body['data']['brief_date'], '2026-05-20')
        self.assertEqual(len(body['data']['overseas']), 1)
        self.assertEqual(body['data']['ai_summary'], '美股上涨。')


if __name__ == '__main__':
    unittest.main()
