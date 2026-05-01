"""
Flask应用主文件
"""
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
    l2_dashboard_bp
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
    logger.info("启动股票数据API服务")
    socketio.run(app, debug=True, host='0.0.0.0', port=9001)
