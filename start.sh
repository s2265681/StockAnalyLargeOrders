#!/bin/bash

# 股票分析系统启动脚本
echo "========================================"
echo "🚀 启动股票分析系统"
echo "========================================"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装，请先安装 Python3"
    exit 1
fi

# 检查Node.js环境
if ! command -v node &> /dev/null; then
    echo "❌ Node.js 未安装，请先安装 Node.js"
    exit 1
fi

# 检查pnpm
if ! command -v pnpm &> /dev/null; then
    echo "❌ pnpm 未安装，请先安装 pnpm: npm install -g pnpm"
    exit 1
fi

# 启动后端服务
echo "📦 启动后端服务..."
cd backend

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "🔧 创建Python虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "📥 安装后端依赖..."
pip install -r requirements.txt

# 启动后端服务
echo "🎯 启动Flask后端服务 (端口: 9001)..."
nohup python app.py > ../backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > ../backend.pid

cd ..

# 启动前端服务
echo "🎨 启动前端服务..."
cd frontend

# 安装依赖
echo "📥 安装前端依赖..."
pnpm install

# 启动前端服务
echo "🌐 启动React前端服务 (端口: 9000)..."
nohup pnpm start > ../frontend.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > ../frontend.pid

cd ..

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查服务状态
echo "🔍 检查服务状态..."

# 检查后端
if curl -s http://localhost:9001/health > /dev/null; then
    echo "✅ 后端服务运行正常 (http://localhost:9001)"
else
    echo "❌ 后端服务启动失败，请检查日志: backend.log"
fi

# 检查前端
if curl -s http://localhost:9000 > /dev/null; then
    echo "✅ 前端服务运行正常 (http://localhost:9000)"
else
    echo "⚠️  前端服务可能还在启动中，请稍等片刻"
fi

echo ""
echo "========================================"
echo "🎉 股票分析系统启动完成！"
echo ""
echo "📊 前端地址: http://localhost:9000"
echo "🔧 后端地址: http://localhost:9001"
echo "📄 健康检查: http://localhost:9001/health"
echo ""
echo "📝 日志文件:"
echo "   - 后端日志: backend.log"
echo "   - 前端日志: frontend.log"
echo ""
echo "🛑 停止服务: ./stop.sh"
echo "========================================"

# 显示进程信息
echo "📋 服务进程信息:"
echo "   - 后端PID: $BACKEND_PID"
echo "   - 前端PID: $FRONTEND_PID"
echo ""

# 提示用户
echo "💡 提示:"
echo "   - 首次启动可能需要几分钟来安装依赖"
echo "   - 如遇到问题，请检查对应的日志文件"
echo "   - 默认显示平安银行(000001)数据"
echo ""
echo "🔥 系统功能:"
echo "   - 实时股价显示与分时图"
echo "   - 大单资金流向分析"
echo "   - 数据多源验证"
echo "   - 专业股票指标展示" 