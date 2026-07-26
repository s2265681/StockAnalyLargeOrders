import unittest
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

CFG = {
    'enabled': True,
    'app_id': 'wx_test_appid',
    'app_secret': 'secret',
    'redirect_uri': 'https://www.stockai.xin/api/auth/wechat/callback',
    'frontend_url': 'https://www.stockai.xin',
}


def _make_app():
    from utils.env import load_env
    load_env()
    from flask import Flask
    app = Flask(__name__)
    from routes.auth import auth_bp
    app.register_blueprint(auth_bp)
    return app


class TestWechatLogin(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.client = self.app.test_client()
        # 每个用例前清空进程内 state/ticket，避免相互污染
        import utils.oauth_state as store
        store._states.clear()
        store._tickets.clear()

    # ---- qrcode ----
    @patch('routes.auth.get_wechat_login_config', return_value=CFG)
    def test_qrcode_returns_authorize_url_with_state(self, _cfg):
        resp = self.client.get('/api/auth/wechat/qrcode')
        body = resp.get_json()
        self.assertTrue(body['success'])
        self.assertIn('wx_test_appid', body['data']['authorize_url'])
        self.assertIn('snsapi_login', body['data']['authorize_url'])
        self.assertTrue(body['data']['state'])

    @patch('routes.auth.get_wechat_login_config',
           return_value={**CFG, 'enabled': False})
    def test_qrcode_disabled(self, _cfg):
        resp = self.client.get('/api/auth/wechat/qrcode')
        self.assertFalse(resp.get_json()['success'])

    # ---- callback ----
    @patch('routes.auth._find_or_create_wechat_user',
           return_value={'id': 42, 'username': '微信用户_abc', 'role': 'user'})
    @patch('routes.auth.get_userinfo',
           return_value={'nickname': '小明', 'avatar': 'http://x/a.png', 'unionid': 'U1'})
    @patch('routes.auth.code2access_token',
           return_value={'access_token': 'AT', 'openid': 'OPENID1', 'unionid': 'U1'})
    @patch('routes.auth.get_wechat_login_config', return_value=CFG)
    def test_callback_success_redirects_with_ticket(self, _cfg, _tok, _info, _user):
        from utils.oauth_state import create_state, consume_ticket
        state = create_state()
        resp = self.client.get(f'/api/auth/wechat/callback?code=CODE&state={state}')
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers['Location']
        self.assertIn('/wechat-callback?ticket=', loc)
        # ticket 有效且可换出用户
        ticket = loc.split('ticket=')[1]
        payload = consume_ticket(ticket)
        self.assertEqual(payload['user']['id'], 42)
        self.assertTrue(payload['token'])

    @patch('routes.auth.get_wechat_login_config', return_value=CFG)
    def test_callback_invalid_state(self, _cfg):
        resp = self.client.get('/api/auth/wechat/callback?code=CODE&state=bogus')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('error=invalid_state', resp.headers['Location'])

    @patch('routes.auth.get_wechat_login_config', return_value=CFG)
    def test_callback_missing_code(self, _cfg):
        from utils.oauth_state import create_state
        state = create_state()
        resp = self.client.get(f'/api/auth/wechat/callback?state={state}')
        self.assertIn('error=denied', resp.headers['Location'])

    @patch('routes.auth.code2access_token',
           side_effect=__import__('utils.wechat_oauth', fromlist=['WeChatOAuthError']).WeChatOAuthError('bad'))
    @patch('routes.auth.get_wechat_login_config', return_value=CFG)
    def test_callback_exchange_failure(self, _cfg, _tok):
        from utils.oauth_state import create_state
        state = create_state()
        resp = self.client.get(f'/api/auth/wechat/callback?code=CODE&state={state}')
        self.assertIn('error=exchange_failed', resp.headers['Location'])

    # ---- exchange ----
    def test_exchange_valid_ticket(self):
        from utils.oauth_state import create_ticket
        ticket = create_ticket({'token': 'JWT', 'user': {'id': 7, 'username': 'u', 'role': 'user'}})
        resp = self.client.post('/api/auth/wechat/exchange', json={'ticket': ticket})
        body = resp.get_json()
        self.assertTrue(body['success'])
        self.assertEqual(body['data']['token'], 'JWT')

    def test_exchange_ticket_is_single_use(self):
        from utils.oauth_state import create_ticket
        ticket = create_ticket({'token': 'JWT', 'user': {'id': 7}})
        self.client.post('/api/auth/wechat/exchange', json={'ticket': ticket})
        resp2 = self.client.post('/api/auth/wechat/exchange', json={'ticket': ticket})
        self.assertFalse(resp2.get_json()['success'])

    def test_exchange_invalid_ticket(self):
        resp = self.client.post('/api/auth/wechat/exchange', json={'ticket': 'nope'})
        self.assertFalse(resp.get_json()['success'])


class TestOAuthStateStore(unittest.TestCase):

    def test_state_single_use(self):
        from utils.oauth_state import create_state, consume_state
        s = create_state()
        self.assertTrue(consume_state(s))
        self.assertFalse(consume_state(s))

    def test_state_expired(self):
        import utils.oauth_state as store
        s = store.create_state()
        store._states[s] = 0  # 强制过期
        self.assertFalse(store.consume_state(s))


if __name__ == '__main__':
    unittest.main()
