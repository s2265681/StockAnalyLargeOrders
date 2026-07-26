"""微信网页扫码登录（开放平台网站应用 snsapi_login）配置。

注意：网站应用的 AppID/AppSecret 独立于微信支付/小程序，不可复用。
"""
from utils.env import getenv


def get_wechat_login_config():
    """读取网页扫码登录配置；缺少 AppID/AppSecret 时 enabled=False。"""
    app_id = getenv('WECHAT_WEB_APP_ID')
    app_secret = getenv('WECHAT_WEB_APP_SECRET')
    # 微信回调地址（须与开放平台“授权回调域”一致，指向后端 callback 端点）
    redirect_uri = getenv('WECHAT_WEB_REDIRECT_URI')
    # 登录完成后跳回的前端地址（回调页负责用 ticket 换 JWT）
    frontend_url = getenv('WECHAT_WEB_FRONTEND_URL', 'https://www.stockai.xin')

    return {
        'enabled': bool(app_id and app_secret and redirect_uri),
        'app_id': app_id,
        'app_secret': app_secret,
        'redirect_uri': redirect_uri,
        'frontend_url': frontend_url.rstrip('/'),
    }


def is_wechat_login_enabled():
    return get_wechat_login_config()['enabled']
