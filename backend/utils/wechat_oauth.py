"""微信开放平台网站应用 OAuth：code 换 access_token，拉取用户信息。"""
import logging

import requests

logger = logging.getLogger(__name__)

ACCESS_TOKEN_URL = 'https://api.weixin.qq.com/sns/oauth2/access_token'
USERINFO_URL = 'https://api.weixin.qq.com/sns/userinfo'


class WeChatOAuthError(Exception):
    pass


def code2access_token(app_id, app_secret, code):
    """用扫码授权返回的 code 换取 access_token + openid/unionid。"""
    if not code:
        raise WeChatOAuthError('缺少 code')
    try:
        resp = requests.get(
            ACCESS_TOKEN_URL,
            params={
                'appid': app_id,
                'secret': app_secret,
                'code': code,
                'grant_type': 'authorization_code',
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise WeChatOAuthError(f'请求微信接口失败: {exc}') from exc

    data = resp.json() if resp.text else {}
    if data.get('errcode'):
        logger.warning('oauth2 access_token error: %s', data)
        raise WeChatOAuthError(f'微信授权失败: {data.get("errmsg", data.get("errcode"))}')

    access_token = data.get('access_token')
    openid = data.get('openid')
    if not access_token or not openid:
        raise WeChatOAuthError('未获取到 access_token/openid')
    return {
        'access_token': access_token,
        'openid': openid,
        'unionid': data.get('unionid'),
    }


def get_userinfo(access_token, openid):
    """拉取微信用户公开信息（昵称、头像、unionid）。失败不阻断登录。"""
    try:
        resp = requests.get(
            USERINFO_URL,
            params={'access_token': access_token, 'openid': openid, 'lang': 'zh_CN'},
            timeout=10,
        )
        data = resp.json() if resp.text else {}
    except requests.RequestException as exc:
        logger.warning('get userinfo failed: %s', exc)
        return {}

    if data.get('errcode'):
        logger.warning('userinfo error: %s', data)
        return {}
    return {
        'nickname': data.get('nickname'),
        'avatar': data.get('headimgurl'),
        'unionid': data.get('unionid'),
    }
