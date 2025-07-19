#!/bin/bash

# 🚀 服务器部署脚本
# 用于在服务器上正确部署股票分析系统

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 检查系统依赖
check_dependencies() {
    print_info "检查系统依赖..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 未安装"
        exit 1
    fi
    
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3 未安装"
        exit 1
    fi
    
    if ! command -v pm2 &> /dev/null; then
        print_warning "PM2 未安装，正在安装..."
        npm install -g pm2
    fi
    
    print_success "系统依赖检查通过"
}

# 设置后端环境
setup_backend() {
    print_info "设置后端环境..."
    
    cd backend
    
    # 删除旧的虚拟环境
    if [ -d "venv" ]; then
        print_info "删除旧的虚拟环境..."
        rm -rf venv
    fi
    
    # 创建新的虚拟环境
    print_info "创建Python虚拟环境..."
    python3 -m venv venv
    
    # 激活虚拟环境并安装依赖
    print_info "安装Python依赖..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # 验证安装
    print_info "验证Flask安装..."
    python -c "import flask; print(f'Flask版本: {flask.__version__}')"
    
    cd ..
    print_success "后端环境设置完成"
}

# 创建日志目录
create_log_dirs() {
    print_info "创建日志目录..."
    mkdir -p logs
    print_success "日志目录创建完成"
}

# 启动 PM2 服务
start_pm2() {
    print_info "启动PM2服务..."
    
    # 停止现有服务
    pm2 stop StockAnalysisLargeOrders 2>/dev/null || true
    pm2 delete StockAnalysisLargeOrders 2>/dev/null || true
    
    # 启动新服务
    pm2 start ecosystem.config.js
    
    # 保存PM2配置
    pm2 save
    
    # 设置开机自启
    pm2 startup
    
    print_success "PM2服务启动完成"
}

# 检查服务状态
check_service() {
    print_info "检查服务状态..."
    
    sleep 5
    
    if pm2 list | grep -q "StockAnalysisLargeOrders.*online"; then
        print_success "服务运行正常"
        
        # 测试API
        if curl -s http://localhost:9001/health > /dev/null 2>&1; then
            print_success "API健康检查通过"
        else
            print_warning "API健康检查失败，请查看日志"
        fi
    else
        print_error "服务启动失败"
        pm2 logs StockAnalysisLargeOrders --lines 20
        exit 1
    fi
}

# 主函数
main() {
    print_info "开始服务器部署..."
    
    check_dependencies
    setup_backend
    create_log_dirs
    start_pm2
    check_service
    
    print_success "🎉 服务器部署完成！"
    echo ""
    print_info "服务信息:"
    echo "  🔧 后端地址: http://localhost:9001"
    echo "  📄 健康检查: http://localhost:9001/health"
    echo "  📝 日志查看: pm2 logs StockAnalysisLargeOrders"
    echo "  🛑 停止服务: pm2 stop StockAnalysisLargeOrders"
    echo "  🔄 重启服务: pm2 restart StockAnalysisLargeOrders"
}

# 执行主函数
main "$@" 