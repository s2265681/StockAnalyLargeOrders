# 自动注册脚本

针对 WordPress + xh_social 插件搭建的网站，使用 Python 模拟浏览器完成自动化注册流程。仅供学习研究使用。

## 项目结构

```
crawler_backend/
├── dapaodan_register.py        # 主脚本 — 注册流程入口
├── core/
│   ├── ema_service.py          # e码平台 API 封装（取号、取码、释放）
│   └── phone_detection_service.py  # 手机号质量检测
├── utils/
│   └── config.py               # 配置管理（环境变量、UA池、代理）
├── .env                        # 环境变量（e码账密等，不提交到 git）
├── requirements.txt            # Python 依赖
└── e码API.md                   # e码平台 API 参考文档
```

## 环境准备

### 1. 安装依赖

```bash
cd crawler_backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

在 `.env` 文件中填写 e码平台的账号密码：

```env
EMA_USERNAME=你的e码用户名
EMA_PASSWORD=你的e码密码
```

可选配置（代理 IP）：

```env
USE_PROXY=true
PROXY_LIST=http://ip1:port,http://ip2:port
```

### 3. e码平台准备

首次使用或长时间未使用 API 时，需要先通过 e码 APP 或网页版（eomsg.com）登录一次账号，之后 2 小时内 API 可正常调用。

## 使用方法

```bash
source venv/bin/activate
python dapaodan_register.py
```

运行后会自动完成注册，最终输出账号信息：

```
用户名: yanglin
邮箱:   yanglin@sina.com
密码:   Wei1991b
手机号: 15332607221
```

## 注意事项

- 运行前确保 e码平台有余额，每次取号约 ¥0.28
- 如果提示 e码登录失败，先去 APP 或网页版登录一次
- 脚本会自动释放手机号，不会浪费号码资源
- 仅供学习研究，请遵守相关法律法规
