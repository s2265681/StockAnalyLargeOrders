# 定时任务说明（本地 / 服务器）

> **生产环境请在阿里云服务器跑**（`install_server_crontab.sh`），本机仅调试或临时使用。  
> 本地与服务器**不要同时**启用同一套 cron。

---

## 一、任务总览

| 类别 | 脚本 | 触发时间（工作日 cron） | 行为 |
|------|------|-------------------------|------|
| 盘中刷新 | `run_intraday.sh` | **9:45 / 10:30 / 11:30 / 14:00 / 14:45**（5 次） | 强制覆盖当日：梯队 + 情绪周期 + 买卖指导 |
| 龙虎榜 AI | `run_dragon_tiger.sh` | 15:30 / 16:30 / 17:30 / 18:30 | 补全 AI；**已齐全则跳过** |
| 竞价抢筹 | `run_auction_grab.sh` | **9:25、9:30** 早盘；15:20、15:40 尾盘 | 写入 `auction_grab_stocks` |

### 通用机制

- **休市日跳过**：`job_guard.py` 调东方财富校验，节假日/周末直接 exit 0。
- **任务锁**：`logs/.{name}.lock`，上一轮未结束则跳过，避免 AI 重叠。
- **邮件提醒**：成功/失败均发信至 `JOB_ALERT_EMAIL`。正文两行：首行含状态/耗时/任务/时间，次行将核心结果提炼合并（如 `梯队✓；情绪✓；AI共8只/新2/跳5/败1`）。设 `JOB_NOTIFY_ON_SUCCESS=0` 可只保留失败告警。
- **日志轮转**：服务器安装 `deploy/logrotate-niuniuniu.conf`（保留 14 天）。

---

## 二、服务器安装（推荐）

```bash
ssh your-server
cd /www/StockAnalyLargeOrders
git pull   # 或通过 GitHub Actions 部署

# 在 backend/.env 配置 SMTP（见下文）
bash backend/jobs/install_server_crontab.sh
```

GitHub Actions `deploy.yml` 在每次部署成功后会**自动执行** `install_server_crontab.sh`。

### SMTP 配置（`backend/.env`）

```env
JOB_ALERT_EMAIL=s2265681@163.com
SMTP_HOST=smtp.qq.com          # 或企业邮箱 SMTP
SMTP_PORT=465
SMTP_SSL=1
SMTP_USER=你的发信邮箱
SMTP_PASS=授权码
SMTP_FROM=你的发信邮箱
```

未配置 SMTP 时任务仍正常运行，仅无法发邮件。

---

## 三、本地安装（可选）

```bash
bash backend/jobs/install_local_crontab.sh
crontab -l | grep -A15 "NiuNIuNiu local jobs"
```

模板：`backend/jobs/crontab.local.txt`  
**合盖休眠会漏跑**，生产请用服务器。

---

## 四、日志

| 文件 | 内容 |
|------|------|
| `logs/intraday_job.log` | 盘中三合一 |
| `logs/dragon_tiger_job.log` | 龙虎榜 |
| `logs/auction_grab_job.log` | 竞价 |

手动执行：

```bash
backend/jobs/run_intraday.sh
backend/jobs/run_dragon_tiger.sh
backend/jobs/run_auction_grab.sh morning
```

---

## 五、文件结构

```
backend/jobs/
├── job_lib.sh              # 休市检查、锁、失败告警
├── job_guard.py
├── job_notify_failure.py
├── intraday_refresh.py
├── auction_grab_sync.py
├── crontab.server.txt
├── crontab.local.txt
├── install_server_crontab.sh
└── install_local_crontab.sh
backend/utils/
├── job_notify.py
└── date_utils.py           # is_trading_day()
deploy/logrotate-niuniuniu.conf
```

---

## 六、故障排查

| 现象 | 处理 |
|------|------|
| 未收到失败邮件 | 检查 `.env` SMTP；看日志 `未配置 SMTP` |
| 休市仍跑 | 查 `job_guard` 日志；东财接口失败时仅排除周末 |
| 竞价表不存在 | 执行 `migrations/20260517_create_auction_grab_tables.sql` |
| 锁未释放 | `rmdir logs/.intraday.lock`（异常退出时） |

---

*更新：2026-05-17 — 降频 5 次/日、竞价 9:25/9:30、休市跳过、邮件告警、服务器 cron*
