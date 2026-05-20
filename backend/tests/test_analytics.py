import unittest
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _make_app():
    from utils.env import load_env
    load_env()
    import eventlet
    eventlet.monkey_patch()
    from flask import Flask
    from flask_cors import CORS
    app = Flask(__name__)
    CORS(app)
    from routes.analytics import analytics_bp
    app.register_blueprint(analytics_bp)
    return app


class TestAnalyticsAPI(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.client = self.app.test_client()
        self.auth_header = {'Authorization': 'Bearer test-token'}

    def _mock_auth(self, user_id=1, role='user'):
        return patch(
            'utils.auth_middleware.decode_token',
            return_value={'user_id': user_id, 'username': 'test', 'role': role},
        )

    @patch('routes.analytics.execute_write')
    def test_page_visit_records_dashboard(self, mock_write):
        with self._mock_auth():
            resp = self.client.post(
                '/api/analytics/page-visit',
                json={'page': 'stock-dashboard'},
                headers=self.auth_header,
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['success'])
        mock_write.assert_called_once()
        args = mock_write.call_args[0][1]
        self.assertEqual(args[0], 1)
        self.assertEqual(args[1], 'stock-dashboard')

    def test_page_visit_rejects_unknown_page(self):
        with self._mock_auth():
            resp = self.client.post(
                '/api/analytics/page-visit',
                json={'page': 'other'},
                headers=self.auth_header,
            )
        self.assertFalse(resp.get_json()['success'])

    @patch('routes.analytics.execute_query', return_value=[{'cnt': 5}])
    def test_dashboard_dau_logged_in(self, _mock_q):
        with self._mock_auth(role='user'):
            resp = self.client.get(
                '/api/analytics/dashboard-dau',
                headers=self.auth_header,
            )
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['count'], 5)
        self.assertEqual(data['data']['page'], 'stock-dashboard')


if __name__ == '__main__':
    unittest.main()
