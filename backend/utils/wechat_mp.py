"""微信小程序服务端能力：code2session 换取 openid。"""
import logging

import requests

from utils.env import getenv

logger = logging.getLogger(__name__)

JSCODE2SESSION_URL = 'https://api.weixin.qq.com/sns/jscode2session'


class WeChatMpError(Exception):
    pass


def _get_mp_credentials():
    # 小程序 AppID 默认复用支付 AppID（商户号绑的就是小程序 AppID）
    app_id = getenv('WECHAT_MP_APP_ID') or getenv('WECHAT_APP_ID')
    app_secret = getenv('WECHAT_MP_APP_SECRET')
    return app_id, app_secret


def is_mp_configured():
    app_id, app_secret = _get_mp_credentials()
    return bool(app_id and app_secret)


def code2session(js_code):
    """用 Taro.login() 拿到的 code 换取 openid。"""
    if not js_code:
        raise WeChatMpError('缺少登录 code')
    app_id, app_secret = _get_mp_credentials()
    if not app_id or not app_secret:
        raise WeChatMpError('小程序 AppID/AppSecret 未配置')

    try:
        resp = requests.get(
            JSCODE2SESSION_URL,
            params={
                'appid': app_id,
                'secret': app_secret,
                'js_code': js_code,
                'grant_type': 'authorization_code',
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise WeChatMpError(f'请求微信接口失败: {exc}') from exc

    data = resp.json() if resp.text else {}
    if data.get('errcode'):
        logger.warning('jscode2session error: %s', data)
        raise WeChatMpError(f'微信登录失败: {data.get("errmsg", data.get("errcode"))}')

    openid = data.get('openid')
    if not openid:
        raise WeChatMpError('未获取到 openid')
    return openid
