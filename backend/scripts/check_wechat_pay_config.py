#!/usr/bin/env python3
"""检查微信支付配置是否齐全（不输出密钥内容）。"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from utils.env import load_env  # noqa: E402

load_env()

from config.wechat_pay import get_wechat_pay_config  # noqa: E402


def main():
    config = get_wechat_pay_config()
    print('=== 微信支付配置检查 ===\n')

    checks = [
        ('WECHAT_PAY_ENABLED', config['enabled'] or '未完全就绪'),
        ('验签模式', config.get('verify_mode') or '未设置'),
        ('WECHAT_MCH_ID', config.get('mch_id') or '未设置'),
        ('WECHAT_APP_ID', config.get('app_id') or '未设置（等网站应用审核）'),
        ('WECHAT_API_V3_KEY', '已设置' if config.get('api_v3_key') else '未设置'),
        ('WECHAT_CERT_SERIAL_NO', config.get('cert_serial_no') or '未设置'),
        ('WECHAT_NOTIFY_URL', config.get('notify_url') or '未设置'),
        ('商户私钥', '已加载' if config.get('private_key') else '未找到'),
    ]

    if config.get('verify_mode') == 'public_key':
        checks.extend([
            ('微信支付公钥', '已加载' if config.get('public_key') else '未找到'),
            ('WECHAT_PAY_PUBLIC_KEY_ID', config.get('public_key_id') or '未设置'),
        ])
    else:
        checks.append(('平台证书', '已加载' if config.get('platform_cert') else '未找到'))

    for name, value in checks:
        print(f'  {name}: {value}')

    if config['missing']:
        print('\n仍缺失:')
        for item in config['missing']:
            print(f'  - {item}')
    else:
        print('\n所有必填项已就绪，可启用微信支付。')

    if not config.get('app_id'):
        print('\n提示: AppID 需等开放平台网站应用审核通过后再配置。')

    return 0 if config['enabled'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
