"""微信登录用的临时凭证存储（带 TTL 的进程内存）。

后端以单进程 eventlet 运行（见 ecosystem.config.js instances=1），
因此进程内 dict 足以承载 state / 一次性 ticket，无需 Redis。

- state：防 CSRF，随二维码下发，回调时校验，一次性消费。
- ticket：登录成功后签发的一次性凭证，前端用它换取真正的 JWT，
  避免 JWT 出现在重定向 URL、浏览器历史与访问日志中。
"""
import secrets
import threading
import time

_STATE_TTL = 300      # 二维码/授权有效期 5 分钟
_TICKET_TTL = 120     # ticket 换 token 窗口 2 分钟

_lock = threading.Lock()
_states = {}   # state -> expire_ts
_tickets = {}  # ticket -> (payload_dict, expire_ts)


def _purge(now=None):
    now = now or time.time()
    for k in [k for k, exp in _states.items() if exp < now]:
        _states.pop(k, None)
    for k in [k for k, (_, exp) in _tickets.items() if exp < now]:
        _tickets.pop(k, None)


def create_state():
    token = secrets.token_urlsafe(24)
    with _lock:
        _purge()
        _states[token] = time.time() + _STATE_TTL
    return token


def consume_state(state):
    """校验并一次性消费 state；有效返回 True。"""
    if not state:
        return False
    with _lock:
        _purge()
        exp = _states.pop(state, None)
    return exp is not None and exp >= time.time()


def create_ticket(payload):
    token = secrets.token_urlsafe(24)
    with _lock:
        _purge()
        _tickets[token] = (payload, time.time() + _TICKET_TTL)
    return token


def consume_ticket(ticket):
    """校验并一次性消费 ticket；有效返回 payload，否则 None。"""
    if not ticket:
        return None
    with _lock:
        _purge()
        entry = _tickets.pop(ticket, None)
    if not entry:
        return None
    payload, exp = entry
    return payload if exp >= time.time() else None
