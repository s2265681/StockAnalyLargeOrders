#!/bin/bash

# 爬虫号码池注册后端停止脚本
echo "========================================"
echo "🛑 停止爬虫号码池注册后端服务"
echo "========================================"

# 检查PID文件
if [ -f "crawler.pid" ]; then
    CRAWLER_PID=$(cat crawler.pid)
    
    if ps -p $CRAWLER_PID > /dev/null; then
        echo "🔄 正在停止爬虫服务 (PID: $CRAWLER_PID)..."
        kill $CRAWLER_PID
        
        # 等待进程结束
        sleep 3
        
        if ps -p $CRAWLER_PID > /dev/null; then
            echo "⚠️  进程仍在运行，强制终止..."
            kill -9 $CRAWLER_PID
        fi
        
        echo "✅ 爬虫服务已停止"
    else
        echo "⚠️  进程不存在 (PID: $CRAWLER_PID)"
    fi
    
    # 删除PID文件
    rm -f crawler.pid
else
    echo "⚠️  未找到PID文件"
fi

# 检查端口占用
if lsof -ti:9003 > /dev/null 2>&1; then
    echo "🔄 清理端口9003占用..."
    lsof -ti:9003 | xargs kill -9
    echo "✅ 端口9003已清理"
fi

echo ""
echo "========================================"
echo "🎉 爬虫号码池注册后端服务已停止！"
echo "========================================" 