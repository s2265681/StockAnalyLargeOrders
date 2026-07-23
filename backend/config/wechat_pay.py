"""微信支付配置"""
import os
from pathlib import Path
from utils.env import getenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _read_key_file(path_value):
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = _BACKEND_DIR / path
    if not path.is_file():
        return None
    return path.read_text(encoding='utf-8')


def get_wechat_pay_config():
    """读取微信支付配置；未启用或缺少必填项时返回 enabled=False。"""
    enabled = getenv('WECHAT_PAY_ENABLED', '0') in ('1', 'true', 'True', 'yes')
    app_id = getenv('WECHAT_APP_ID')
    mch_id = getenv('WECHAT_MCH_ID')
    api_v3_key = getenv('WECHAT_API_V3_KEY')
    cert_serial_no = getenv('WECHAT_CERT_SERIAL_NO')
    notify_url = getenv('WECHAT_NOTIFY_URL')
    public_key_id = getenv('WECHAT_PAY_PUBLIC_KEY_ID')

    private_key = getenv('WECHAT_PRIVATE_KEY')
    if not private_key:
        private_key = _read_key_file(getenv('WECHAT_PRIVATE_KEY_PATH', 'certs/apiclient_key.pem'))

    public_key = getenv('WECHAT_PAY_PUBLIC_KEY')
    if not public_key:
        public_key = _read_key_file(getenv('WECHAT_PAY_PUBLIC_KEY_PATH', 'certs/pub_key.pem'))

    platform_cert = getenv('WECHAT_PLATFORM_CERT')
    if not platform_cert:
        platform_cert = _read_key_file(getenv('WECHAT_PLATFORM_CERT_PATH', 'certs/wechatpay_platform.pem'))

    verify_mode = 'public_key' if public_key and public_key_id else 'platform_cert'
    verify_key = public_key if verify_mode == 'public_key' else platform_cert

    missing = []
    if enabled:
        for name, value in [
            ('WECHAT_APP_ID', app_id),
            ('WECHAT_MCH_ID', mch_id),
            ('WECHAT_API_V3_KEY', api_v3_key),
            ('WECHAT_CERT_SERIAL_NO', cert_serial_no),
            ('WECHAT_NOTIFY_URL', notify_url),
            ('WECHAT_PRIVATE_KEY / WECHAT_PRIVATE_KEY_PATH', private_key),
        ]:
            if not value:
                missing.append(name)

        if verify_mode == 'public_key':
            if not public_key_id:
                missing.append('WECHAT_PAY_PUBLIC_KEY_ID')
            if not public_key:
                missing.append('WECHAT_PAY_PUBLIC_KEY / WECHAT_PAY_PUBLIC_KEY_PATH')
        elif not platform_cert:
            missing.append('WECHAT_PLATFORM_CERT / WECHAT_PLATFORM_CERT_PATH（或改用公钥模式）')

    return {
        'enabled': enabled and not missing,
        'missing': missing,
        'verify_mode': verify_mode,
        'app_id': app_id,
        'mch_id': mch_id,
        'api_v3_key': api_v3_key,
        'cert_serial_no': cert_serial_no,
        'notify_url': notify_url,
        'private_key': private_key,
        'verify_key': verify_key,
        'public_key': public_key,
        'public_key_id': public_key_id,
        'platform_cert': platform_cert,
    }
