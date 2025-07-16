# AKShare 分时数据集成总结

## 问题背景

用户反馈分时数据获取再次失败，需要为分时数据获取添加AKShare作为数据源。

## 解决方案

### 1. 新增 AKShare 分时数据获取函数

在 `backend/app.py` 中新增了 `get_akshare_timeshare_data(code)` 函数：

- **数据源**：使用 `ak.stock_zh_a_hist_min_em()` 获取1分钟级分时数据
- **时间范围**：当日 09:30-15:00 交易时间
- **数据转换**：将AKShare数据格式转换为系统标准格式
- **错误处理**：包含详细的错误日志和异常处理

### 2. 优化分时数据获取策略

为所有调用分时数据的地方添加了多层级优先级策略：

1. **第一优先级**：AKShare分时数据（`get_akshare_timeshare_data`）
2. **第二优先级**：东方财富分时数据（`get_eastmoney_timeshare_data`）

### 3. 修改文件列表

#### 主要修改：backend/app.py
- 新增 `get_akshare_timeshare_data()` 函数
- 修改 `get_trading_data()` 函数的分时数据获取逻辑
- 修改大单分析API中的分时数据获取逻辑
- 确保所有分时数据调用都优先使用AKShare

#### 辅助修改：backend/stock_data_manager.py
- 更新import语句，添加AKShare分时数据函数
- 修改大单分析逻辑的分时数据获取策略

## 技术实现细节

### AKShare 分时数据接口特点

```python
# 使用1分钟K线数据作为分时数据
timeshare_df = ak.stock_zh_a_hist_min_em(
    symbol=code, 
    period="1", 
    start_date=start_time, 
    end_date=end_time, 
    adjust=""
)
```

### 数据格式标准化

AKShare返回的数据列名转换：
- `时间` → `time`
- `开盘` → `open`  
- `收盘` → `close`
- `最高` → `high`
- `最低` → `low`
- `成交量` → `volume`
- `成交额` → `amount`

### 容错机制

1. **数据源失败处理**：AKShare失败时自动切换到东方财富
2. **数据验证**：检查返回数据的完整性和有效性
3. **详细日志**：记录每个数据源的尝试结果

## 影响的功能模块

1. **大单统计接口** (`/api/v1/dadantongji`)
2. **交易数据获取** (`get_trading_data`)
3. **股票数据管理器** (`stock_data_manager.py`)

## 预期效果

1. **提高数据可靠性**：AKShare提供更稳定的分时数据源
2. **增强系统鲁棒性**：多重数据源确保服务可用性
3. **改善用户体验**：减少分时数据获取失败的情况

## 测试建议

建议测试以下场景：
1. AKShare分时数据获取成功的情况
2. AKShare失败但东方财富成功的情况
3. 两个数据源都失败的降级处理
4. 不同股票代码的数据获取验证

## 相关技术栈

- **AKShare**：主要财经数据源
- **pandas**：数据处理和转换
- **requests**：HTTP请求处理
- **logging**：错误和状态记录 