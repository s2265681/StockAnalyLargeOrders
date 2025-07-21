#!/bin/bash

# 爬虫号码池注册后端启动脚本
echo "========================================"
echo "🚀 启动爬虫号码池注册后端服务"
echo "========================================"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装，请先安装 Python3"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "🔧 创建Python虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "📥 安装依赖..."
pip install -r requirements.txt

# 创建日志目录
mkdir -p logs

# 启动服务
echo "🎯 启动Flask爬虫服务 (端口: 9003)..."
nohup python app.py > logs/crawler.log 2>&1 &
CRAWLER_PID=$!
echo $CRAWLER_PID > crawler.pid

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查服务状态
echo "🔍 检查服务状态..."

if curl -s http://localhost:9003/health > /dev/null; then
    echo "✅ 爬虫服务运行正常 (http://localhost:9003)"
    echo "📊 健康检查: http://localhost:9003/health"
    echo "📚 API文档: http://localhost:9003/"
else
    echo "❌ 爬虫服务启动失败，请检查日志: logs/crawler.log"
    exit 1
fi

echo ""
echo "========================================"
echo "🎉 爬虫号码池注册后端服务启动完成！"
echo "========================================"
echo ""
echo "📋 可用接口:"
echo "  - 健康检查: GET /health"
echo "  - 注册账户: POST /api/register"
echo "  - 登录账户: POST /api/login"
echo "  - 获取数据: POST /api/data"
echo "  - 号码池状态: GET /api/phone-pool"
echo "  - 添加号码: POST /api/phone-pool"
echo "  - 验证码识别: POST /api/captcha"
echo "  - 会话管理: GET /api/sessions"
echo "  - 系统状态: GET /api/status"
echo "  - 系统清理: POST /api/cleanup"
echo ""
echo "📁 日志文件: logs/crawler.log"
echo "🛑 停止服务: ./stop.sh"
echo "" 