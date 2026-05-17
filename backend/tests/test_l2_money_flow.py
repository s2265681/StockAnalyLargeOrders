import unittest
from unittest.mock import patch

from flask import Flask

from routes.l2_dashboard import l2_dashboard_bp


class L2MoneyFlowRouteTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(l2_dashboard_bp)

    def test_l2_money_flow_uses_ths_moneyflow_shape(self):
        ths_moneyflow = {
            'success': True,
            'date': '20260515',
            'items': [
                {
                    'time': '0930',
                    'super_big_in': 20000.0,
                    'super_big_out': 5000.0,
                    'big_in': 10000.0,
                    'big_out': 3000.0,
                    'mid_in': 7000.0,
                    'mid_out': 9000.0,
                    'small_in': 4000.0,
                    'small_out': 8000.0,
                },
                {
                    'time': '0931',
                    'super_big_in': 30000.0,
                    'super_big_out': 10000.0,
                    'big_in': 15000.0,
                    'big_out': 5000.0,
                    'mid_in': 9000.0,
                    'mid_out': 6000.0,
                    'small_in': 9000.0,
                    'small_out': 3000.0,
                },
            ],
            'summary': {},
            'source': 'ths',
        }

        with patch('routes.l2_dashboard.get_moneyflow', return_value=ths_moneyflow):
            response = self.app.test_client().get('/api/v1/l2_money_flow?code=600578&dt=2026-05-15')

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['source'], 'ths')
        self.assertEqual(payload['data']['date'], '20260515')
        self.assertEqual(payload['data']['time'], ['09:30', '09:31'])
        self.assertEqual(payload['data']['chaoda_delta'], ['1.500', '0.500'])
        self.assertEqual(payload['data']['sanhu_delta'], ['-0.400', '1.000'])
        self.assertGreater(float(payload['data']['chaoda'][-1]), float(payload['data']['sanhu'][-1]))
        self.assertEqual(payload['data']['zhuli'], payload['data']['chaoda'])

    def test_l2_money_flow_returns_unavailable_when_both_sources_empty(self):
        with patch('routes.l2_dashboard.get_moneyflow', return_value={'success': False, 'items': []}), \
             patch('routes.stock_timeshare.get_eastmoney_money_flow_data', return_value=None):
            response = self.app.test_client().get('/api/v1/l2_money_flow?code=002342&dt=2026-05-15')

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['message'], '资金流数据暂不可用')
        self.assertIsNone(payload['data'])

    def test_l2_money_flow_falls_back_to_eastmoney_for_shenzhen(self):
        """同花顺对深市恒空，回退东财 fflow（累计净流入→分钟delta），
        形状必须与同花顺一致，避免沪深不一致导致主力/散户线时有时无。"""
        eastmoney_raw = {
            'time': ['09:30', '09:31'],
            'chaoda': ['10.000', '25.000'],   # 超大单累计净(万)
            'dadan': ['5.000', '8.000'],      # 大单累计净
            'zhongdan': ['2.000', '1.000'],   # 中单累计净
            'sanhu': ['-3.000', '-6.000'],    # 小单累计净
            'zhuli': ['15.000', '33.000'],
        }
        with patch('routes.l2_dashboard.get_moneyflow', return_value={'success': False, 'items': []}), \
             patch('routes.stock_timeshare.get_eastmoney_money_flow_data', return_value=eastmoney_raw):
            response = self.app.test_client().get('/api/v1/l2_money_flow?code=300750&dt=2026-05-15')

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        data = payload['data']
        self.assertEqual(data['source'], 'eastmoney_fflow')
        self.assertEqual(data['time'], ['09:30', '09:31'])
        # 累计净 → 分钟净: 超大 [10,15], 小单 [-3,-3]
        self.assertEqual(data['chaoda_delta'], ['10.000', '15.000'])
        self.assertEqual(data['sanhu_delta'], ['-3.000', '-3.000'])
        self.assertEqual(data['zhuli'], data['chaoda'])
        self.assertEqual(data['summary']['main_net_wan'], 33.0)
        self.assertEqual(len(data['chaoda']), 2)


class ThsMoneyflowSessionTest(unittest.TestCase):
    def test_session_ignores_env_proxy(self):
        """后端常被从带失效代理的 shell 启动，资金流 session 必须绕过环境代理，
        否则主力/散户线会随启动环境时有时无。"""
        import services.ths_moneyflow as m
        self.assertFalse(m._SESSION.trust_env)


if __name__ == '__main__':
    unittest.main()
