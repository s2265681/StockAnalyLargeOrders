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

    def test_l2_money_flow_returns_unavailable_when_ths_is_empty(self):
        with patch('routes.l2_dashboard.get_moneyflow', return_value={'success': False, 'items': []}):
            with patch('routes.l2_dashboard.adapter.get_orders_data') as get_orders_data:
                response = self.app.test_client().get('/api/v1/l2_money_flow?code=002342&dt=2026-05-15')

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['message'], '资金流数据暂不可用')
        self.assertIsNone(payload['data'])
        get_orders_data.assert_not_called()


if __name__ == '__main__':
    unittest.main()
