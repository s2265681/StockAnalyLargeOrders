#!/bin/bash

# 🚀 股票分析系统部署脚本
# 支持开发环境(localhost:9001)和生产环境(18.141.179.222:9001)

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的信息
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

# 显示帮助信息
show_help() {
    echo "🚀 股票分析系统部署脚本"
    echo ""
    echo "用法: ./deploy.sh [选项] [环境]"
    echo ""
    echo "环境:"
    echo "  dev     开发环境 (localhost:9001)"
    echo "  prod    生产环境 (18.141.179.222:9001)"
    echo ""
    echo "选项:"
    echo "  -h, --help     显示帮助信息"
    echo "  -c, --clean    清理构建缓存"
    echo "  -i, --install  重新安装依赖"
    echo "  -t, --test     测试API连接"
    echo ""
    echo "示例:"
    echo "  ./deploy.sh dev              # 开发环境部署"
    echo "  ./deploy.sh prod --clean     # 生产环境部署并清理缓存"
    echo "  ./deploy.sh --test           # 测试API连接"
}

# 检查依赖
check_dependencies() {
    print_info "检查系统依赖..."
    
    if ! command -v node &> /dev/null; then
        print_error "Node.js 未安装，请先安装 Node.js"
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        print_error "npm 未安装，请先安装 npm"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 未安装，请先安装 Python3"
        exit 1
    fi
    
    print_success "系统依赖检查通过"
}

# 安装前端依赖
install_frontend_deps() {
    print_info "安装前端依赖..."
    cd frontend
    npm install
    cd ..
    print_success "前端依赖安装完成"
}

# 安装后端依赖
install_backend_deps() {
    print_info "安装后端依赖..."
    cd backend
    
    # 检查虚拟环境
    if [ ! -d "venv" ]; then
        print_info "创建Python虚拟环境..."
        python3 -m venv venv
    fi
    
    # 激活虚拟环境并安装依赖
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
    print_success "后端依赖安装完成"
}

# 清理缓存
clean_cache() {
    print_info "清理构建缓存..."
    
    # 清理前端缓存
    if [ -d "frontend/node_modules" ]; then
        rm -rf frontend/node_modules
    fi
    if [ -d "frontend/build" ]; then
        rm -rf frontend/build
    fi
    
    # 清理后端缓存
    if [ -d "backend/__pycache__" ]; then
        rm -rf backend/__pycache__
    fi
    
    print_success "缓存清理完成"
}

# 测试API连接
test_api_connection() {
    local api_url=$1
    print_info "测试API连接: $api_url"
    
    # 测试健康检查端点
    if curl -s -f "${api_url}/health" > /dev/null 2>&1; then
        print_success "API连接正常"
        return 0
    else
        print_warning "API连接失败，请检查后端服务是否启动"
        return 1
    fi
}

# 启动后端服务
start_backend() {
    local env=$1
    print_info "启动后端服务 ($env环境)..."
    
    cd backend
    source venv/bin/activate
    
    if [ "$env" = "dev" ]; then
        # 开发环境
        export FLASK_ENV=development
        export FLASK_DEBUG=1
        python app.py &
    else
        # 生产环境
        export FLASK_ENV=production
        export FLASK_DEBUG=0
        python app.py &
    fi
    
    BACKEND_PID=$!
    cd ..
    
    # 等待后端启动
    sleep 3
    print_success "后端服务启动完成 (PID: $BACKEND_PID)"
}

# 构建并启动前端
start_frontend() {
    local env=$1
    print_info "构建并启动前端 ($env环境)..."
    
    cd frontend
    
    if [ "$env" = "dev" ]; then
        # 开发环境
        print_info "开发环境模式启动..."
        export REACT_APP_API_BASE_URL=http://localhost:9001
        npm start &
    else
        # 生产环境
        print_info "生产环境构建..."
        export REACT_APP_API_BASE_URL=http://18.141.179.222:9001
        npm run build:prod
        
        print_info "启动生产服务器..."
        npx serve -s build -l 9000 &
    fi
    
    FRONTEND_PID=$!
    cd ..
    
    # 等待前端启动
    sleep 5
    print_success "前端服务启动完成 (PID: $FRONTEND_PID)"
}

# 主部署流程
deploy() {
    local env=$1
    local clean_flag=$2
    local install_flag=$3
    local test_flag=$4
    
    print_info "开始部署股票分析系统 ($env环境)..."
    
    # 检查依赖
    check_dependencies
    
    # 清理缓存
    if [ "$clean_flag" = "true" ]; then
        clean_cache
    fi
    
    # 安装依赖
    if [ "$install_flag" = "true" ] || [ ! -d "frontend/node_modules" ]; then
        install_frontend_deps
        install_backend_deps
    fi
    
    # 启动服务
    start_backend $env
    start_frontend $env
    
    # 测试API连接
    if [ "$test_flag" = "true" ]; then
        sleep 5
        if [ "$env" = "dev" ]; then
            test_api_connection "http://localhost:9001"
        else
            test_api_connection "http://18.141.179.222:9001"
        fi
    fi
    
    # 显示服务信息
    echo ""
    print_success "🎉 部署完成！"
    echo ""
    print_info "服务信息:"
    if [ "$env" = "dev" ]; then
        echo "  📱 前端地址: http://localhost:9000"
        echo "  🔧 后端地址: http://localhost:9001" 
        echo "  🔍 API测试: http://localhost:9001/api/v1/base_info?code=603001"
    else
        echo "  📱 前端地址: http://localhost:9000"
        echo "  🔧 后端地址: http://18.141.179.222:9001"
        echo "  🔍 API测试: http://18.141.179.222:9001/api/v1/base_info?code=603001"
    fi
    echo ""
    print_info "按 Ctrl+C 停止所有服务"
    
    # 等待用户中断
    trap "stop_services" SIGINT
    wait
}

# 停止服务
stop_services() {
    echo ""
    print_info "正在停止服务..."
    
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
        print_success "后端服务已停止"
    fi
    
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
        print_success "前端服务已停止"
    fi
    
    print_success "所有服务已停止"
    exit 0
}

# 解析命令行参数
ENV=""
CLEAN_FLAG=false
INSTALL_FLAG=false
TEST_FLAG=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--clean)
            CLEAN_FLAG=true
            shift
            ;;
        -i|--install)
            INSTALL_FLAG=true
            shift
            ;;
        -t|--test)
            TEST_FLAG=true
            shift
            ;;
        dev|prod)
            ENV=$1
            shift
            ;;
        *)
            print_error "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 如果没有指定环境，默认为开发环境
if [ -z "$ENV" ]; then
    ENV="dev"
    print_warning "未指定环境，默认使用开发环境"
fi

# 验证环境参数
if [ "$ENV" != "dev" ] && [ "$ENV" != "prod" ]; then
    print_error "无效的环境参数: $ENV (只支持 dev 或 prod)"
    exit 1
fi

# 开始部署
deploy $ENV $CLEAN_FLAG $INSTALL_FLAG $TEST_FLAG 