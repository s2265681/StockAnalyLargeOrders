# 微信支付商户平台配置指南（可先完成，不等网站应用审核）

> 商户号：**1748571098**  
> 商户简称：stockai-助手  
> 主体：杭州临安重阳微噪电子商务商行（个体工商户）  
> 回调域名：`www.stockai.xin`

---

## 一、商户平台「开发配置」（你截图里的页面）

路径：**产品中心 → 开发配置 → 支付配置**

### 1. Native 支付回调链接（必配）

点击 **修改**，填写：

```
https://www.stockai.xin/api/payments/wechat/notify
```

说明：
- 必须 **HTTPS**
- 路径与后端代码一致（`backend/routes/orders.py`）
- 与 `backend/.env` 里的 `WECHAT_NOTIFY_URL` **保持一致**

### 2. JSAPI 支付授权目录（建议先配，以后微信内打开可用）

点击 **添加**，填写：

```
https://www.stockai.xin/
```

注意：
- 必须以 `/` 结尾
- 最多 5 个目录
- PC 纯扫码不强制，但已开通 JSAPI，建议配上

---

## 二、账户中心 → API 安全（密钥与证书）

路径：**账户中心 → API 安全**

按顺序完成：

### 步骤 1：设置 APIv3 密钥

1. 点击 **设置 APIv3 密钥**
2. 自行生成 **32 位** 字符串（大小写字母+数字）
3. **务必保存**，只显示一次

示例生成（本地终端）：

```bash
openssl rand -hex 16
```

记下结果，填入 `WECHAT_API_V3_KEY`。

### 步骤 2：申请 API 证书

1. 点击 **申请 API 证书**
2. 下载 **证书工具** 或使用微信提供的工具生成
3. 得到文件（解压后）：
   - `apiclient_key.pem` ← **商户私钥**（重要，勿泄露）
   - `apiclient_cert.pem`
4. 在页面查看 **证书序列号** → 填入 `WECHAT_CERT_SERIAL_NO`

### 步骤 3：下载微信支付公钥（你当前是公钥模式）

1. 在 **API 安全 → 微信支付公钥** 点击 **重新下载**
2. 保存 PEM 文件为 `backend/certs/pub_key.pem`
3. 复制 **公钥 ID**（形如 `PUB_KEY_ID_...`）→ `WECHAT_PAY_PUBLIC_KEY_ID`

> 你的公钥 ID：`PUB_KEY_ID_0117485710982026072300181620002803`  
> 公钥模式**不需要**再下载平台证书。

### 步骤 4：放置证书文件

将文件放到服务器（或本地）：

```
backend/certs/
├── apiclient_key.pem          # 商户 API 私钥
└── pub_key.pem                # 微信支付公钥（公钥模式）
```

`certs/` 目录已在 `.gitignore` 中，**不要提交到 Git**。

---

## 三、配置 `backend/.env`

在服务器 `backend/.env` 增加（或修改）：

```bash
# ========== 微信支付 ==========
WECHAT_PAY_ENABLED=1
WECHAT_MCH_ID=1748571098
WECHAT_API_V3_KEY=你的32位APIv3密钥
WECHAT_CERT_SERIAL_NO=你的证书序列号
WECHAT_NOTIFY_URL=https://www.stockai.xin/api/payments/wechat/notify
WECHAT_PRIVATE_KEY_PATH=certs/apiclient_key.pem
WECHAT_PAY_PUBLIC_KEY_PATH=certs/pub_key.pem
WECHAT_PAY_PUBLIC_KEY_ID=PUB_KEY_ID_0117485710982026072300181620002803

# 网站应用审核通过后再填 AppID
WECHAT_APP_ID=wx待填写的网站应用AppID
```

**说明：**
- `WECHAT_APP_ID` 需等开放平台网站应用审核通过后才能填
- 在 AppID 关联完成前，可先 `WECHAT_PAY_ENABLED=0`，或保持 `1` 但支付会因缺 AppID 无法下单

---

## 四、数据库迁移（服务器执行一次）

```bash
mysql -u root -p stock < backend/migrations/20260723_wechat_pay_orders.sql
```

新增字段：`payment_channel`、`transaction_id`、`paid_at`

---

## 五、安装依赖并重启后端

```bash
cd backend
pip install -r requirements.txt   # 含 cryptography
# 重启 PM2 / 你的部署方式
pm2 restart StockAnalysisLargeOrders
```

---

## 六、验证配置是否齐全

在 `backend` 目录执行：

```bash
python3 scripts/check_wechat_pay_config.py
```

会列出已配置项和仍缺失项（不会打印密钥内容）。

---

## 七、网站应用审核通过后再做

1. 复制开放平台网站应用 **AppID**
2. 商户平台 → **产品中心 → AppID 账号管理** → 新增授权
3. 开放平台 → 网站应用 → **微信支付** → 确认关联
4. 把 AppID 写入 `WECHAT_APP_ID`
5. 重启后端
6. 用 **日度 VIP ¥0.01** 测试一笔真实支付

---

## 配置对照表

| 配置项 | 在哪里获取 | .env 变量 |
|--------|-----------|-----------|
| 商户号 | 商户平台首页 | `WECHAT_MCH_ID` |
| APIv3 密钥 | 账户中心 → API 安全 | `WECHAT_API_V3_KEY` |
| 证书序列号 | 账户中心 → API 安全 | `WECHAT_CERT_SERIAL_NO` |
| 商户私钥 | 申请证书后下载 | `WECHAT_PRIVATE_KEY_PATH` |
| 微信支付公钥 | API 安全 → 微信支付公钥 | `WECHAT_PAY_PUBLIC_KEY_PATH` |
| 公钥 ID | 同页面复制 | `WECHAT_PAY_PUBLIC_KEY_ID` |
| 回调地址 | 自行填写 | `WECHAT_NOTIFY_URL` |
| AppID | 开放平台网站应用 | `WECHAT_APP_ID` |
