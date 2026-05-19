"""
Flask应用主文件
"""
from utils.env import load_env

load_env()

import eventlet
eventlet.monkey_patch()

import logging
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

from routes import (
    stock_basic_bp,
    stock_timeshare_bp,
    stock_tick_bp,
    stock_other_bp,
    l2_dashboard_bp,
    emotion_cycle_bp,
    limit_up_echelon_bp,
    theme_manage_bp,
    auction_grab_bp,
    dragon_tiger_bp,
    auth_bp,
    user_bp,
    orders_bp,
    ai_diagnosis_bp,
    ai_account_bp,
)

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def register_blueprints(app):
    app.register_blueprint(stock_basic_bp)
    app.register_blueprint(stock_timeshare_bp)
    app.register_blueprint(stock_tick_bp)
    app.register_blueprint(stock_other_bp)
    app.register_blueprint(l2_dashboard_bp)
    app.register_blueprint(emotion_cycle_bp)
    app.register_blueprint(limit_up_echelon_bp)
    app.register_blueprint(theme_manage_bp)
    app.register_blueprint(auction_grab_bp)
    app.register_blueprint(dragon_tiger_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(ai_diagnosis_bp)
    app.register_blueprint(ai_account_bp)


register_blueprints(app)

from websocket_manager import register_websocket_events, start_push_loop
register_websocket_events(socketio)
start_push_loop(socketio)


@app.route('/health')
def health():
    return {
        'status': 'healthy',
        'message': '股票数据API服务运行正常',
        'version': '5.0.0',
    }


@app.route('/api/v1/data_source_status')
def data_source_status():
    """检测东方财富数据源可用性（被动，不发额外请求，不加剧限流）"""
    from services.eastmoney_free import EastMoneyFreeSource
    health = EastMoneyFreeSource.get_health()
    return {'success': True, 'data': health}


@app.route('/api/v1/set_cookie', methods=['POST'])
def set_cookie():
    """设置东方财富登录 Cookie，用于访问历史逐笔等需要登录的接口。
    Body: { "cookie": "<浏览器复制的 Cookie 字符串>" }
    """
    from flask import request as req
    from services.eastmoney_free import EastMoneyFreeSource
    body = req.get_json(silent=True) or {}
    cookie_str = (body.get('cookie') or '').strip()
    if not cookie_str:
        return {'success': False, 'message': 'cookie 字段不能为空'}, 400
    EastMoneyFreeSource.set_em_cookie(cookie_str)
    return {'success': True, 'message': 'Cookie 已更新，历史逐笔接口将使用新 Cookie'}


@app.route('/api/v1/get_cookie_status')
def get_cookie_status():
    """返回当前 Cookie 是否已设置"""
    from services.eastmoney_free import EastMoneyFreeSource
    return {'success': True, 'data': EastMoneyFreeSource.get_cookie_status()}


@app.route('/')
def index():
    return {
        'message': '股票数据API服务',
        'version': '5.0.0',
        'endpoints': {
            'health': '/health',
            'base_info': '/api/v1/base_info?code=000001',
            'quote': '/api/v1/quote?code=000001',
            'dadan': '/api/v1/dadan?code=000001',
            'dadantongji': '/api/v1/dadantongji?code=000001',
            'l2_dashboard': '/api/v1/l2_dashboard?code=000001',
            'limit_up_themes': '/api/v1/limit_up_themes?code=000001',
            'trading_date': '/api/trading-date/current',
        }
    }


@app.errorhandler(404)
def not_found(error):
    return {'code': 404, 'message': '接口不存在'}, 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"内部服务器错误: {error}")
    return {'code': 500, 'message': '内部服务器错误', 'error': str(error)}, 500


@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"未处理的异常: {error}")
    return {'code': 500, 'message': '服务器异常', 'error': str(error)}, 500


@app.before_request
def log_request():
    from flask import request
    logger.info(f"{request.method} {request.path} - {request.remote_addr}")


@app.after_request
def log_response(response):
    from flask import request
    logger.info(f"{request.method} {request.path} - {response.status_code}")
    return response


if __name__ == '__main__':
    import os

    logger.info("启动股票数据API服务")
    _debug = os.environ.get('FLASK_DEBUG', '0').strip().lower() in ('1', 'true', 'yes')
    socketio.run(
        app,
        debug=_debug,
        use_reloader=_debug,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 9001)),
    )
