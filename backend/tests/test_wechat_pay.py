"""订单与微信支付相关测试"""
import json
import unittest
from unittest.mock import patch, MagicMock

from services.order_service import PLANS, get_plan, mark_order_paid
from config.wechat_pay import get_wechat_pay_config


class TestWeChatPayConfig(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict('os.environ', {}, clear=True):
            config = get_wechat_pay_config()
            self.assertFalse(config['enabled'])

    def test_enabled_requires_all_fields(self):
        env = {
            'WECHAT_PAY_ENABLED': '1',
            'WECHAT_APP_ID': 'wx123',
            'WECHAT_MCH_ID': 'mch123',
            'WECHAT_API_V3_KEY': 'a' * 32,
            'WECHAT_CERT_SERIAL_NO': 'serial',
            'WECHAT_NOTIFY_URL': 'https://example.com/notify',
            'WECHAT_PRIVATE_KEY': '-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----',
            'WECHAT_PLATFORM_CERT': '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----',
        }
        with patch.dict('os.environ', env, clear=True):
            config = get_wechat_pay_config()
            self.assertTrue(config['enabled'])
            self.assertEqual(config['missing'], [])

    def test_enabled_with_missing_fields(self):
        env = {'WECHAT_PAY_ENABLED': '1', 'WECHAT_APP_ID': 'wx123'}
        with patch.dict('os.environ', env, clear=True):
            config = get_wechat_pay_config()
            self.assertFalse(config['enabled'])
            self.assertTrue(len(config['missing']) > 0)


class TestOrderService(unittest.TestCase):
    def test_get_plan(self):
        plan = get_plan('monthly')
        self.assertEqual(plan['amount'], 380.00)
        self.assertEqual(plan['days'], 30)

    @patch('services.order_service.execute_write')
    @patch('services.order_service.execute_query')
    def test_mark_order_paid_idempotent(self, mock_query, mock_write):
        mock_query.return_value = [{'id': 1, 'user_id': 9, 'plan_type': 'monthly', 'status': 'paid'}]
        result = mark_order_paid('NN001', 'wechat', 'wx_tx_1')
        self.assertTrue(result)
        mock_write.assert_not_called()

    @patch('services.order_service.activate_subscription')
    @patch('services.order_service.execute_write')
    @patch('services.order_service.execute_query')
    def test_mark_order_paid_pending(self, mock_query, mock_write, mock_activate):
        mock_query.return_value = [{'id': 1, 'user_id': 9, 'plan_type': 'monthly', 'status': 'pending'}]
        result = mark_order_paid('NN001', 'wechat', 'wx_tx_1')
        self.assertTrue(result)
        mock_write.assert_called_once()
        mock_activate.assert_called_once_with(9, 'monthly')


class TestWeChatPayClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes
            import datetime

            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            cls.private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode('utf-8')

            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, 'wechat-test'),
            ])
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.utcnow())
                .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=1))
                .sign(private_key, hashes.SHA256())
            )
            cls.platform_pem = cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
            cls.crypto_available = True
        except ImportError:
            cls.crypto_available = False

    @patch('utils.wechat_pay_client.requests.request')
    def test_create_native_order(self, mock_request):
        if not self.crypto_available:
            self.skipTest('cryptography not available')

        from utils.wechat_pay_client import WeChatPayClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({'code_url': 'weixin://wxpay/bizpayurl?pr=abc'})
        mock_request.return_value = mock_response

        config = {
            'app_id': 'wx_test',
            'mch_id': 'mch_test',
            'api_v3_key': 'a' * 32,
            'cert_serial_no': 'serial_test',
            'notify_url': 'https://example.com/notify',
            'private_key': self.private_pem,
            'platform_cert': self.platform_pem,
        }

        client = WeChatPayClient(config)
        code_url = client.create_native_order('NN001', '测试订单', 0.01)
        self.assertEqual(code_url, 'weixin://wxpay/bizpayurl?pr=abc')
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        self.assertIn('/v3/pay/transactions/native', mock_request.call_args[0][1])
        self.assertIn('WECHATPAY2-SHA256-RSA2048', call_kwargs['headers']['Authorization'])


if __name__ == '__main__':
    unittest.main()
