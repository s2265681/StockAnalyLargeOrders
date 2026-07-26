"""认证相关 API：注册、登录、修改密码、微信扫码登录"""
import logging
import secrets
from urllib.parse import urlencode

from flask import Blueprint, request, redirect

from werkzeug.security import generate_password_hash, check_password_hash
from utils.response import v1_success_response, v1_error_response
from utils.db import execute_query, execute_write, execute_insert
from utils.auth_middleware import generate_token, login_required
from config.wechat_login import get_wechat_login_config
from utils.wechat_oauth import code2access_token, get_userinfo, WeChatOAuthError
from utils.oauth_state import create_state, consume_state, create_ticket, consume_ticket

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

WECHAT_AUTHORIZE_URL = 'https://open.weixin.qq.com/connect/qrconnect'


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    body = request.get_json(silent=True) or {}
    username = (body.get('username') or '').strip()
    password = body.get('password', '')
    phone = (body.get('phone') or '').strip() or None

    if not username or len(username) < 2 or len(username) > 20:
        return v1_error_response('用户名需要2-20个字符')
    if not password or len(password) < 6:
        return v1_error_response('密码至少6个字符')

    existing = execute_query('SELECT id FROM users WHERE username = %s', (username,))
    if existing:
        return v1_error_response('用户名已存在')

    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    try:
        execute_write(
            'INSERT INTO users (username, password_hash, phone) VALUES (%s, %s, %s)',
            (username, password_hash, phone)
        )
    except Exception as e:
        logger.error(f'注册失败: {e}')
        return v1_error_response('注册失败，请稍后重试')

    user = execute_query('SELECT id, username, role FROM users WHERE username = %s', (username,))
    if user:
        u = user[0]
        token = generate_token(u['id'], u['username'], u['role'])
        return v1_success_response(data={
            'token': token,
            'user': {'id': u['id'], 'username': u['username'], 'role': u['role']}
        }, message='注册成功')

    return v1_error_response('注册异常')


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get('username') or '').strip()
    password = body.get('password', '')

    if not username or not password:
        return v1_error_response('请输入用户名和密码')

    user = execute_query(
        'SELECT id, username, password_hash, role FROM users WHERE username = %s', (username,)
    )
    if not user:
        return v1_error_response('用户名或密码错误')

    u = user[0]
    if not check_password_hash(u['password_hash'], password):
        return v1_error_response('用户名或密码错误')

    token = generate_token(u['id'], u['username'], u['role'])
    return v1_success_response(data={
        'token': token,
        'user': {'id': u['id'], 'username': u['username'], 'role': u['role']}
    }, message='登录成功')


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    body = request.get_json(silent=True) or {}
    old_password = body.get('old_password', '')
    new_password = body.get('new_password', '')

    if not old_password or not new_password:
        return v1_error_response('请输入旧密码和新密码')
    if len(new_password) < 6:
        return v1_error_response('新密码至少6个字符')

    user_id = request.current_user['user_id']
    user = execute_query('SELECT password_hash FROM users WHERE id = %s', (user_id,))
    if not user:
        return v1_error_response('用户不存在')

    if not check_password_hash(user[0]['password_hash'], old_password):
        return v1_error_response('旧密码错误')

    new_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    execute_write('UPDATE users SET password_hash = %s WHERE id = %s', (new_hash, user_id))
    return v1_success_response(message='密码修改成功')


# ---------------------------------------------------------------------------
# 微信网页扫码登录（开放平台网站应用 snsapi_login）
# ---------------------------------------------------------------------------

def _gen_username_from_nickname(nickname):
    base = (nickname or '微信用户').strip()[:12] or '微信用户'
    for _ in range(6):
        candidate = f'{base}_{secrets.token_hex(3)}'
        if not execute_query('SELECT id FROM users WHERE username = %s', (candidate,)):
            return candidate
    return f'wx_{secrets.token_hex(6)}'


def _find_or_create_wechat_user(openid, unionid, nickname, avatar):
    """按 unionid 优先、openid 兜底查用户；不存在则自动建户。返回用户行 dict。"""
    row = None
    if unionid:
        rows = execute_query(
            'SELECT id, username, role FROM users WHERE wechat_unionid = %s', (unionid,)
        )
        row = rows[0] if rows else None
    if not row:
        rows = execute_query(
            'SELECT id, username, role FROM users WHERE wechat_openid = %s', (openid,)
        )
        row = rows[0] if rows else None

    if row:
        # 回填可能新增的 unionid / 更新头像昵称
        execute_write(
            'UPDATE users SET wechat_unionid = COALESCE(%s, wechat_unionid), '
            'nickname = %s, avatar = %s WHERE id = %s',
            (unionid, nickname, avatar, row['id'])
        )
        return row

    username = _gen_username_from_nickname(nickname)
    user_id = execute_insert(
        'INSERT INTO users (username, wechat_openid, wechat_unionid, nickname, avatar, role) '
        'VALUES (%s, %s, %s, %s, %s, %s)',
        (username, openid, unionid, nickname, avatar, 'user')
    )
    return {'id': user_id, 'username': username, 'role': 'user'}


@auth_bp.route('/api/auth/wechat/qrcode', methods=['GET'])
def wechat_qrcode():
    """下发扫码登录授权 URL。前端可直接 window.location 跳转或内嵌二维码。"""
    cfg = get_wechat_login_config()
    if not cfg['enabled']:
        return v1_error_response('微信登录未配置')

    state = create_state()
    params = {
        'appid': cfg['app_id'],
        'redirect_uri': cfg['redirect_uri'],
        'response_type': 'code',
        'scope': 'snsapi_login',
        'state': state,
    }
    authorize_url = f'{WECHAT_AUTHORIZE_URL}?{urlencode(params)}#wechat_redirect'
    return v1_success_response(data={
        'authorize_url': authorize_url,
        'state': state,
        'app_id': cfg['app_id'],
        'redirect_uri': cfg['redirect_uri'],
    })


@auth_bp.route('/api/auth/wechat/callback', methods=['GET'])
def wechat_callback():
    """微信授权回调：校验 state → 换 token → 建/查用户 → 带 ticket 跳回前端。"""
    cfg = get_wechat_login_config()
    code = request.args.get('code', '')
    state = request.args.get('state', '')
    frontend = cfg['frontend_url'] or ''

    def _fail(reason):
        return redirect(f'{frontend}/wechat-callback?{urlencode({"error": reason})}')

    if not cfg['enabled']:
        return _fail('not_configured')
    if not code:
        return _fail('denied')
    if not consume_state(state):
        return _fail('invalid_state')

    try:
        token_data = code2access_token(cfg['app_id'], cfg['app_secret'], code)
    except WeChatOAuthError as exc:
        logger.warning('wechat callback token exchange failed: %s', exc)
        return _fail('exchange_failed')

    info = get_userinfo(token_data['access_token'], token_data['openid'])
    unionid = token_data.get('unionid') or info.get('unionid')

    try:
        user = _find_or_create_wechat_user(
            token_data['openid'], unionid, info.get('nickname'), info.get('avatar')
        )
    except Exception as exc:  # 建户写库失败
        logger.exception('wechat user provisioning failed: %s', exc)
        return _fail('user_failed')

    jwt_token = generate_token(user['id'], user['username'], user['role'])
    ticket = create_ticket({
        'token': jwt_token,
        'user': {'id': user['id'], 'username': user['username'], 'role': user['role']},
    })
    return redirect(f'{frontend}/wechat-callback?{urlencode({"ticket": ticket})}')


@auth_bp.route('/api/auth/wechat/exchange', methods=['POST'])
def wechat_exchange():
    """前端回调页用一次性 ticket 换取 JWT。"""
    body = request.get_json(silent=True) or {}
    ticket = body.get('ticket', '')
    payload = consume_ticket(ticket)
    if not payload:
        return v1_error_response('登录凭证无效或已过期，请重新扫码')
    return v1_success_response(data=payload, message='登录成功')
