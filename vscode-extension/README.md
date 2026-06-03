# AI炒股看盘

在 VS Code 状态栏实时显示股票行情，编码的同时掌握市场动态。集成 AI大单分析系统，一键打开完整的大单分析、涨停梯队、龙虎榜等专业功能。

## 功能

### 状态栏实时行情

- 自动轮询新浪行情接口，默认每 5 秒刷新
- 显示格式：`股票名 价格 ↗+涨跌%` 支持多只同时显示
- 涨停自动标注 `[涨停]`，跌停标注 `[跌停]`
- Hover 显示详细信息：今开、最高、最低、成交量、成交额、**封单量、封单金额**
- Hover 右下角 **查看分时图**：在 Cursor 内置浏览器打开线上分时页（自动带上股票代码）

### 八大操作命令（点击状态栏或 Cmd+Shift+P 搜索「股票看盘」）

| 命令 | 说明 |
|------|------|
| 添加股票 | 输入代码（如 603678）或名称关键字（如 火炬），自动搜索匹配 |
| 查看股票 | 在 VS Code 内打开完整的 AI大单分析系统 |
| 移除股票 | 多选移除，显示当前价格方便确认 |
| 排序股票 | 调整状态栏显示顺序 |
| 清空股票 | 一键清空列表 |
| 价格闹钟 | 价格高于/低于目标时弹出通知 |
| 封单预警 | 涨停封单量高于/低于阈值时提醒 |
| 封单大减 | 涨停封单较上一轮刷新减少达设定比例时自动提醒（默认 30%，可配置） |
| 隐藏/显示状态栏 | 临时隐藏股票行情显示 |

### 集成 AI大单分析系统

点击「查看股票」在 VS Code 内嵌浏览器中打开完整应用，包括：

- 分时图 / K线图
- 大单实时监控
- 涨停梯队分析
- 龙虎榜数据
- AI 诊断报告

## 配置

在 `settings.json` 中搜索「股票看盘」，或参考下表：

| 设置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `stockAnalysis.stocks` | array | `[]` | 股票代码列表，启动时自动加入自选 |
| `stockAnalysis.priceAlarms` | array | `[]` | 价格闹钟，如 `[{"code":"sh600797","price":8.5,"direction":"above"}]` |
| `stockAnalysis.maxDisplayCount` | number | `5` | 状态栏最多显示几只 |
| `stockAnalysis.showMiniName` | boolean | `false` | 状态栏显示简称（前 2 字） |
| `stockAnalysis.stockMiniNames` | object | `{}` | 自定义简称映射 |
| `stockAnalysis.showChangeValue` | boolean | `false` | 状态栏显示涨跌额 |
| `stockAnalysis.autoHideByMarket` | boolean | `false` | 非交易时段隐藏状态栏 |
| `stockAnalysis.showLockCount` | boolean | `false` | 涨停时状态栏显示封单量 |
| `stockAnalysis.enableLockTip` | boolean | `true` | 封单异动通知（阈值 + 大减） |
| `stockAnalysis.enableLargeTip` | boolean | `false` | 成交额异动通知 |
| `stockAnalysis.backendUrl` | string | `https://www.stockai.xin/` | 分时/大单页面地址 |
| `stockAnalysis.refreshInterval` | number | `5000` | 刷新间隔（毫秒） |
| `stockAnalysis.sealDropPercent` | number | `30` | 封单大减百分比阈值 |
| `stockAnalysis.sealDropMinVol` | number | `10000` | 封单大减最低检测手数 |
| `stockAnalysis.largeTipMinAmountWan` | number | `300` | 成交额异动阈值（万元/轮） |

## 快速开始

1. 安装扩展后，点击左下角状态栏的 **AI炒股看盘** 图标
2. 选择「添加股票」，输入股票代码或名称
3. 股票行情会自动出现在状态栏，hover 查看封单详情
4. 选择「查看股票」打开完整分析系统
