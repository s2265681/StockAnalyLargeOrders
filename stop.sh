#!/bin/bash

# 股票分析系统停止脚本
echo "========================================"
echo "🛑 停止股票分析系统"
echo "========================================"

# 停止后端服务
if [ -f "backend.pid" ]; then
    BACKEND_PID=$(cat backend.pid)
    echo "🔧 停止后端服务 (PID: $BACKEND_PID)..."
    
    if kill -0 $BACKEND_PID 2>/dev/null; then
        kill $BACKEND_PID
        echo "✅ 后端服务已停止"
    else
        echo "⚠️  后端进程不存在或已停止"
    fi
    
    rm -f backend.pid
else
    echo "⚠️  未找到后端进程ID文件"
fi

# 停止前端服务
if [ -f "frontend.pid" ]; then
    FRONTEND_PID=$(cat frontend.pid)
    echo "🌐 停止前端服务 (PID: $FRONTEND_PID)..."
    
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID
        echo "✅ 前端服务已停止"
    else
        echo "⚠️  前端进程不存在或已停止"
    fi
    
    rm -f frontend.pid
else
    echo "⚠️  未找到前端进程ID文件"
fi

# 强制停止相关进程
echo "🔍 检查并清理残留进程..."

# 查找并停止可能的残留进程
BACKEND_PROCESSES=$(ps aux | grep "python.*app.py" | grep -v grep | awk '{print $2}')
if [ ! -z "$BACKEND_PROCESSES" ]; then
    echo "🧹 清理后端残留进程: $BACKEND_PROCESSES"
    echo $BACKEND_PROCESSES | xargs kill 2>/dev/null
fi

FRONTEND_PROCESSES=$(ps aux | grep "node.*react-scripts" | grep -v grep | awk '{print $2}')
if [ ! -z "$FRONTEND_PROCESSES" ]; then
    echo "🧹 清理前端残留进程: $FRONTEND_PROCESSES"
    echo $FRONTEND_PROCESSES | xargs kill 2>/dev/null
fi

# 清理端口占用
echo "🚪 检查端口占用..."

# 检查9001端口
PORT_9001=$(lsof -ti:9001 2>/dev/null)
if [ ! -z "$PORT_9001" ]; then
    echo "🔓 释放端口9001 (PID: $PORT_9001)"
    kill $PORT_9001 2>/dev/null
fi

# 检查9000端口
PORT_9000=$(lsof -ti:9000 2>/dev/null)
if [ ! -z "$PORT_9000" ]; then
    echo "🔓 释放端口9000 (PID: $PORT_9000)"
    kill $PORT_9000 2>/dev/null
fi

# 等待进程完全停止
sleep 2

# 验证服务已停止
echo "✅ 验证服务状态..."

if curl -s --connect-timeout 2 http://localhost:9001/health > /dev/null 2>&1; then
    echo "⚠️  后端服务仍在运行"
else
    echo "✅ 后端服务已完全停止"
fi

if curl -s --connect-timeout 2 http://localhost:9000 > /dev/null 2>&1; then
    echo "⚠️  前端服务仍在运行"
else
    echo "✅ 前端服务已完全停止"
fi

echo ""
echo "========================================"
echo "✅ 股票分析系统已停止"
echo ""
echo "📝 日志文件保留:"
echo "   - 后端日志: backend.log"
echo "   - 前端日志: frontend.log"
echo ""
echo "🚀 重新启动: ./start.sh"
echo "========================================" 