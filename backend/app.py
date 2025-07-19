"""
重构后的Flask应用主文件
整合所有拆分的模块
"""
import logging
from flask import Flask
from flask_cors import CORS

# 导入所有路由蓝图
from routes import (
    stock_basic_bp,
    stock_timeshare_bp,
    stock_tick_bp,
    stock_realtime_bp,
    stock_other_bp,
    l2_data_bp
)

# 创建Flask应用
app = Flask(__name__)
CORS(app)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 注册所有蓝图
def register_blueprints(app):
    """注册所有蓝图"""
    app.register_blueprint(stock_basic_bp)      # 股票基本信息接口
    app.register_blueprint(stock_timeshare_bp)  # 股票分时数据接口
    app.register_blueprint(stock_tick_bp)       # 股票成交明细接口
    app.register_blueprint(stock_realtime_bp)   # 股票实时数据接口
    app.register_blueprint(stock_other_bp)      # 其他功能接口
    app.register_blueprint(l2_data_bp)          # L2大单逐笔成交数据接口

# 注册蓝图
register_blueprints(app)

# 健康检查端点
@app.route('/health')
def health():
    """健康检查"""
    return {
        'status': 'healthy',
        'message': '股票数据API服务运行正常',
        'version': '4.0.0 - 模块化版本',
        'timestamp': '2025-07-19T01:58:00Z'
    }

# 根路径重定向到健康检查
@app.route('/')
def index():
    """根路径"""
    return {
        'message': '股票数据API服务',
        'version': '4.0.0 - 模块化版本',
        'status': 'running',
        'documentation': {
            'health': '/health',
            'stock_basic': '/api/stock/basic?code=000001',
            'stock_timeshare': '/api/stock/timeshare?code=000001',
            'stock_large_orders': '/api/stock/large-orders?code=000001',
            'stock_realtime': '/api/stock/realtime?code=000001',
            'trading_date': '/api/trading-date/current'
        },
        'modules': [
            'stock_basic - 股票基本信息',
            'stock_timeshare - 股票分时数据', 
            'stock_tick - 股票成交明细',
            'stock_realtime - 股票实时数据',
            'stock_other - 其他功能'
        ]
    }

# 错误处理
@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return {
        'code': 404,
        'message': '接口不存在',
        'error': str(error),
        'available_endpoints': [
            '/api/stock/basic',
            '/api/stock/timeshare',
            '/api/stock/large-orders',
            '/api/stock/realtime',
            '/api/v1/base_info',
            '/api/v1/quote',
            '/api/v1/dadan',
            '/api/v1/dadantongji',
            '/health'
        ]
    }, 404

@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    logger.error(f"内部服务器错误: {error}")
    return {
        'code': 500,
        'message': '内部服务器错误',
        'error': str(error)
    }, 500

@app.errorhandler(Exception)
def handle_exception(error):
    """全局异常处理"""
    logger.error(f"未处理的异常: {error}")
    return {
        'code': 500,
        'message': '服务器异常',
        'error': str(error),
        'type': type(error).__name__
    }, 500

# 请求日志中间件
@app.before_request
def log_request():
    """记录请求日志"""
    from flask import request
    logger.info(f"{request.method} {request.path} - {request.remote_addr}")

@app.after_request
def log_response(response):
    """记录响应日志"""
    from flask import request
    logger.info(f"{request.method} {request.path} - {response.status_code}")
    return response

if __name__ == '__main__':
    # 启动应用
    logger.info("启动股票数据API服务 - 模块化版本")
    logger.info("可用模块:")
    logger.info("  - stock_basic: 股票基本信息")
    logger.info("  - stock_timeshare: 股票分时数据")
    logger.info("  - stock_tick: 股票成交明细")
    logger.info("  - stock_realtime: 股票实时数据")
    logger.info("  - stock_other: 其他功能")
    
    app.run(debug=True, host='0.0.0.0', port=9001) 