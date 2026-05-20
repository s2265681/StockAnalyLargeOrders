import unittest
from unittest.mock import patch
import sys, os
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
    from routes.alert_rules import alert_rules_bp
    app.register_blueprint(alert_rules_bp)
    return app


class TestAlertRulesAPI(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.client = self.app.test_client()
        self.auth_header = {'Authorization': 'Bearer test-token'}

    def _mock_auth(self, user_id=1):
        return patch('utils.auth_middleware.decode_token',
                     return_value={'user_id': user_id, 'username': 'test', 'role': 'user'})

    @patch('routes.alert_rules.execute_query', return_value=[])
    def test_list_rules_returns_empty(self, _mock_q):
        with self._mock_auth():
            resp = self.client.get('/api/alert-rules', headers=self.auth_header)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['items'], [])

    @patch('routes.alert_rules.execute_query', return_value=[{'cnt': 0}])
    @patch('routes.alert_rules.execute_insert', return_value=42)
    @patch('routes.alert_rules.get_stock_name_by_code', return_value='贵州茅台')
    def test_batch_create_single_rule(self, _mock_name, _mock_insert, _mock_q):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [{'code': '600519', 'alert_type': 'limit_up',
                                                     'threshold': None, 'direction': None,
                                                     'email': 'test@qq.com'}]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['created_ids'], [42])

    def test_batch_create_exceeds_limit(self):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [
                                        {'code': '600519', 'alert_type': 'limit_up', 'email': 'a@b.com'},
                                        {'code': '000001', 'alert_type': 'limit_up', 'email': 'a@b.com'},
                                        {'code': '300001', 'alert_type': 'limit_up', 'email': 'a@b.com'},
                                        {'code': '600000', 'alert_type': 'limit_up', 'email': 'a@b.com'},
                                    ]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('3', data['message'])

    def test_batch_create_missing_email(self):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [{'code': '600519', 'alert_type': 'limit_up'}]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('邮箱', data['message'])

    def test_batch_create_change_pct_missing_threshold(self):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [{'code': '600519', 'alert_type': 'change_pct',
                                                     'email': 'a@b.com'}]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('阈值', data['message'])

    @patch('routes.alert_rules.execute_write', return_value=1)
    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 1, 'status': 'triggered'}])
    def test_reactivate_rule(self, _mock_q, _mock_w):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/1/reactivate', headers=self.auth_header)
        data = resp.get_json()
        self.assertTrue(data['success'])

    @patch('routes.alert_rules.execute_write', return_value=1)
    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 1}])
    def test_delete_rule(self, _mock_q, _mock_w):
        with self._mock_auth():
            resp = self.client.delete('/api/alert-rules/1', headers=self.auth_header)
        data = resp.get_json()
        self.assertTrue(data['success'])

    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 99}])
    def test_delete_other_users_rule_rejected(self, _mock_q):
        with self._mock_auth(user_id=1):
            resp = self.client.delete('/api/alert-rules/1', headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('权限', data['message'])

    @patch('routes.alert_rules.execute_write', return_value=1)
    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 1}])
    def test_disable_rule(self, _mock_q, _mock_w):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/1/disable', headers=self.auth_header)
        data = resp.get_json()
        self.assertTrue(data['success'])

    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 99}])
    def test_disable_other_users_rule_rejected(self, _mock_q):
        with self._mock_auth(user_id=1):
            resp = self.client.post('/api/alert-rules/1/disable', headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('权限', data['message'])

    @patch('routes.alert_rules.execute_write', return_value=1)
    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 1}])
    def test_update_rule(self, _mock_q, _mock_w):
        with self._mock_auth():
            resp = self.client.put('/api/alert-rules/1',
                                   json={'threshold': 6.0, 'direction': 'above', 'email': 'new@qq.com'},
                                   headers=self.auth_header)
        data = resp.get_json()
        self.assertTrue(data['success'])

    @patch('routes.alert_rules.execute_query', return_value=[{'user_id': 99}])
    def test_update_other_users_rule_rejected(self, _mock_q):
        with self._mock_auth(user_id=1):
            resp = self.client.put('/api/alert-rules/1',
                                   json={'email': 'new@qq.com'},
                                   headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('权限', data['message'])

    @patch('routes.alert_rules.execute_query', return_value=[{'cnt': 20}])
    def test_batch_create_exceeds_user_limit(self, _mock_q):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [{'code': '600519', 'alert_type': 'limit_up',
                                                     'email': 'a@b.com'}]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('上限', data['message'])

    @patch('routes.alert_rules.execute_query', return_value=[{'cnt': 19}])
    @patch('routes.alert_rules.execute_insert', return_value=10)
    @patch('routes.alert_rules.get_stock_name_by_code', return_value='贵州茅台')
    def test_batch_create_at_limit_boundary_allowed(self, _mock_name, _mock_insert, _mock_q):
        with self._mock_auth():
            resp = self.client.post('/api/alert-rules/batch',
                                    json={'rules': [{'code': '600519', 'alert_type': 'limit_up',
                                                     'email': 'a@b.com'}]},
                                    headers=self.auth_header)
        data = resp.get_json()
        self.assertTrue(data['success'])


if __name__ == '__main__':
    unittest.main()
