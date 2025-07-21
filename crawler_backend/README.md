# 爬虫号码池注册后端

一个基于Flask的爬虫号码池注册系统，支持自动注册、登录和数据获取功能。

## 🎯 功能特性

- **自动注册**: 支持单个和批量账户注册
- **号码池管理**: 智能号码分配和轮换机制
- **验证码识别**: 集成多种OCR引擎自动识别验证码
- **会话管理**: 完整的会话生命周期管理
- **反检测**: 浏览器指纹伪造、代理IP轮换等
- **数据获取**: 自动获取目标网站数据
- **API接口**: 提供完整的RESTful API

## 🏗️ 系统架构

```
crawler_backend/
├── app.py                 # 主应用入口
├── requirements.txt       # 依赖包列表
├── core/                  # 核心模块
│   ├── crawler_manager.py # 爬虫管理器
│   ├── phone_pool.py      # 号码池管理器
│   ├── captcha_solver.py  # 验证码识别器
│   └── session_manager.py # 会话管理器
├── utils/                 # 工具模块
│   ├── config.py          # 配置管理
│   └── database.py        # 数据库管理
├── api/                   # API模块
│   └── routes.py          # 路由定义
├── logs/                  # 日志目录
├── start.sh              # 启动脚本
└── stop.sh               # 停止脚本
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip
- curl (用于健康检查)

### 安装和启动

1. **克隆项目**
```bash
cd crawler_backend
```

2. **给脚本执行权限**
```bash
chmod +x start.sh stop.sh
```

3. **启动服务**
```bash
./start.sh
```

4. **停止服务**
```bash
./stop.sh
```

### 手动启动

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动服务
python app.py
```

## 📋 API接口

### 基础接口

- `GET /health` - 健康检查
- `GET /` - API文档

### 核心功能接口

#### 注册账户
```bash
POST /api/register
Content-Type: application/json

{
  "user_info": {
    "username": "testuser",
    "email": "test@example.com",
    "password": "password123"
  },
  "count": 1
}
```

#### 登录账户
```bash
POST /api/login
Content-Type: application/json

{
  "username": "testuser",
  "password": "password123",
  "session_id": "optional-session-id"
}
```

#### 获取股票数据
```bash
POST /api/data
Content-Type: application/json

{
  "user_info": {
    "session_id": "session-id",
    "token": "user-token",
    "finger_print": "finger-print"
  },
  "stock_code": "000001"
}
```

#### 号码池管理
```bash
# 获取号码池状态
GET /api/phone-pool

# 添加号码到号码池
POST /api/phone-pool
Content-Type: application/json

{
  "phone": "13800138000",
  "source": "manual"
}
```

#### 验证码识别
```bash
POST /api/captcha
Content-Type: application/json

{
  "image_data": "base64-encoded-image",
  "captcha_type": "general"
}
```

#### 会话管理
```bash
# 获取会话列表
GET /api/sessions

# 获取会话信息
GET /api/sessions/{session_id}

# 移除会话
DELETE /api/sessions/{session_id}
```

#### 系统管理
```bash
# 获取系统状态
GET /api/status

# 清理系统
POST /api/cleanup
```

## 🔧 配置说明

### 环境变量

创建 `.env` 文件来配置环境变量：

```env
# 数据库配置
DATABASE_URL=sqlite:///crawler.db
REDIS_URL=redis://localhost:6379/0

# 代理配置
USE_PROXY=false
PROXY_LIST=http://proxy1:8080,http://proxy2:8080

# 日志配置
LOG_LEVEL=INFO
```

### 主要配置项

- `TARGET_SITE`: 目标网站地址
- `REQUEST_TIMEOUT`: 请求超时时间
- `PHONE_POOL_SIZE`: 号码池大小
- `SESSION_TIMEOUT`: 会话超时时间
- `CAPTCHA_TIMEOUT`: 验证码超时时间

## 🛡️ 反检测技术

### 浏览器指纹伪造
- 随机User-Agent
- 模拟真实浏览器行为
- 动态请求头生成

### 验证码处理
- ddddocr自动识别
- tesseract OCR备用
- 人工打码服务集成

### 频率控制
- 随机请求间隔
- 智能频率限制
- 异常检测和处理

### 代理管理
- 代理IP轮换
- 代理质量评估
- 自动故障转移

## 📊 监控和日志

### 日志文件
- `logs/crawler.log` - 主日志文件
- 自动轮转和清理

### 系统状态监控
```bash
# 获取系统状态
curl http://localhost:9003/api/status

# 获取号码池状态
curl http://localhost:9003/api/phone-pool
```

## 🔍 故障排除

### 常见问题

1. **端口被占用**
```bash
lsof -ti:9003 | xargs kill -9
```

2. **依赖安装失败**
```bash
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

3. **验证码识别失败**
- 检查ddddocr安装
- 确认图片格式正确
- 查看日志文件

4. **号码池为空**
```bash
# 手动添加测试号码
curl -X POST http://localhost:9003/api/phone-pool \
  -H "Content-Type: application/json" \
  -d '{"phone": "13800138000", "source": "manual"}'
```

## 📝 开发说明

### 添加新的验证码识别器

1. 在 `core/captcha_solver.py` 中添加新的识别方法
2. 在配置中启用新的识别器
3. 更新错误处理逻辑

### 扩展号码池功能

1. 修改 `core/phone_pool.py` 添加新的号码源
2. 实现号码质量评估
3. 添加号码轮换策略

### 自定义API接口

1. 在 `api/routes.py` 中添加新的路由
2. 实现对应的业务逻辑
3. 添加参数验证和错误处理

## 📄 许可证

本项目仅供学习和研究使用，请遵守相关法律法规和网站使用条款。

## 🤝 贡献

欢迎提交Issue和Pull Request来改进项目。

## 📞 支持

如有问题，请查看日志文件或提交Issue。 