"""微信支付 API v3 客户端（Native 扫码支付）"""
import json
import logging
import secrets
import time
from base64 import b64decode, b64encode

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config.wechat_pay import get_wechat_pay_config

logger = logging.getLogger(__name__)

API_BASE = 'https://api.mch.weixin.qq.com'
_client = None


class WeChatPayError(Exception):
    pass


def _load_private_key(pem_text):
    return serialization.load_pem_private_key(pem_text.encode('utf-8'), password=None)


def _load_public_key(pem_text):
    return serialization.load_pem_public_key(pem_text.encode('utf-8'))


def _sign(private_key, message):
    signature = private_key.sign(
        message.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return b64encode(signature).decode('utf-8')


def _build_authorization(private_key, mch_id, cert_serial_no, method, url_path, body):
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    message = '\n'.join([method, url_path, timestamp, nonce, body, ''])
    signature = _sign(private_key, message)
    token = (
        f'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{mch_id}",nonce_str="{nonce}",signature="{signature}",'
        f'timestamp="{timestamp}",serial_no="{cert_serial_no}"'
    )
    return token


class WeChatPayClient:
    def __init__(self, config):
        self.config = config
        self.private_key = _load_private_key(config['private_key'])
        self.verify_public_key = _load_public_key(config['verify_key'])

    def _request(self, method, url_path, payload=None):
        body = '' if payload is None else json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        headers = {
            'Authorization': _build_authorization(
                self.private_key,
                self.config['mch_id'],
                self.config['cert_serial_no'],
                method,
                url_path,
                body,
            ),
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'StockAnalyLargeOrders/1.0',
        }
        if self.config.get('verify_mode') == 'public_key' and self.config.get('public_key_id'):
            headers['Wechatpay-Serial'] = self.config['public_key_id']
        response = requests.request(
            method,
            f'{API_BASE}{url_path}',
            data=body.encode('utf-8') if body else None,
            headers=headers,
            timeout=15,
        )
        if response.status_code >= 400:
            logger.error('WeChat Pay API error %s %s: %s', method, url_path, response.text)
            raise WeChatPayError(response.text or f'HTTP {response.status_code}')
        if not response.text:
            return {}
        return response.json()

    def create_native_order(self, order_no, description, amount_yuan, expire_minutes=30):
        total_fen = int(round(float(amount_yuan) * 100))
        if total_fen <= 0:
            raise WeChatPayError('支付金额必须大于 0')

        expire_time = time.strftime(
            '%Y-%m-%dT%H:%M:%S+08:00',
            time.localtime(time.time() + expire_minutes * 60),
        )
        payload = {
            'appid': self.config['app_id'],
            'mchid': self.config['mch_id'],
            'description': description,
            'out_trade_no': order_no,
            'notify_url': self.config['notify_url'],
            'time_expire': expire_time,
            'amount': {
                'total': total_fen,
                'currency': 'CNY',
            },
        }
        result = self._request('POST', '/v3/pay/transactions/native', payload)
        code_url = result.get('code_url')
        if not code_url:
            raise WeChatPayError('未获取到支付二维码链接')
        return code_url

    def create_jsapi_order(self, order_no, description, amount_yuan, openid, expire_minutes=30):
        """小程序/JSAPI 下单，返回 prepay_id。"""
        total_fen = int(round(float(amount_yuan) * 100))
        if total_fen <= 0:
            raise WeChatPayError('支付金额必须大于 0')
        if not openid:
            raise WeChatPayError('缺少支付用户 openid')

        expire_time = time.strftime(
            '%Y-%m-%dT%H:%M:%S+08:00',
            time.localtime(time.time() + expire_minutes * 60),
        )
        payload = {
            'appid': self.config['app_id'],
            'mchid': self.config['mch_id'],
            'description': description,
            'out_trade_no': order_no,
            'notify_url': self.config['notify_url'],
            'time_expire': expire_time,
            'amount': {
                'total': total_fen,
                'currency': 'CNY',
            },
            'payer': {
                'openid': openid,
            },
        }
        result = self._request('POST', '/v3/pay/transactions/jsapi', payload)
        prepay_id = result.get('prepay_id')
        if not prepay_id:
            raise WeChatPayError('未获取到 prepay_id')
        return prepay_id

    def build_miniprogram_pay_params(self, prepay_id):
        """由 prepay_id 生成 wx.requestPayment 所需参数（RSA 签名）。"""
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        package = f'prepay_id={prepay_id}'
        message = '\n'.join([self.config['app_id'], timestamp, nonce, package, ''])
        pay_sign = _sign(self.private_key, message)
        return {
            'timeStamp': timestamp,
            'nonceStr': nonce,
            'package': package,
            'signType': 'RSA',
            'paySign': pay_sign,
        }

    def query_order(self, order_no):
        url_path = f'/v3/pay/transactions/out-trade-no/{order_no}?mchid={self.config["mch_id"]}'
        return self._request('GET', url_path)

    def verify_notify_signature(self, headers, body):
        timestamp = headers.get('Wechatpay-Timestamp', '')
        nonce = headers.get('Wechatpay-Nonce', '')
        signature = headers.get('Wechatpay-Signature', '')
        if not timestamp or not nonce or not signature:
            raise WeChatPayError('缺少微信支付回调签名头')

        message = '\n'.join([timestamp, nonce, body, ''])
        try:
            self.verify_public_key.verify(
                b64decode(signature),
                message.encode('utf-8'),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception as exc:
            raise WeChatPayError('回调签名校验失败') from exc

    def decrypt_notify_resource(self, resource):
        api_v3_key = self.config['api_v3_key'].encode('utf-8')
        nonce = resource.get('nonce', '').encode('utf-8')
        ciphertext = b64decode(resource.get('ciphertext', ''))
        associated_data = resource.get('associated_data', '').encode('utf-8')
        plaintext = AESGCM(api_v3_key).decrypt(nonce, ciphertext, associated_data)
        return json.loads(plaintext.decode('utf-8'))


def get_wechat_pay_client():
    global _client
    config = get_wechat_pay_config()
    if not config['enabled']:
        return None
    if _client is None:
        _client = WeChatPayClient(config)
    return _client


def is_wechat_pay_enabled():
    return get_wechat_pay_config()['enabled']
