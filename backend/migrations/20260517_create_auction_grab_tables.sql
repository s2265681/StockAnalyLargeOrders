-- 竞价抢筹日快照（早盘/尾盘），供接口缓存与历史回测

CREATE TABLE IF NOT EXISTS auction_grab_stocks (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL COMMENT '交易日期 YYYYMMDD',
  period TINYINT NOT NULL DEFAULT 0 COMMENT '0=早盘竞价 1=尾盘抢筹',
  code VARCHAR(6) NOT NULL COMMENT '股票代码',
  name VARCHAR(30) DEFAULT '' COMMENT '股票名称',
  open_amount DECIMAL(16,2) DEFAULT 0 COMMENT '开盘金额(万元)',
  grab_change_pct DECIMAL(10,4) DEFAULT 0 COMMENT '竞价涨幅%',
  grab_turnover DECIMAL(16,2) DEFAULT 0 COMMENT '抢筹成交额(万元)',
  grab_order_amount DECIMAL(16,2) DEFAULT 0 COMMENT '抢筹委托金额(万元)',
  close_change_pct DECIMAL(10,4) NULL COMMENT '当日收盘涨幅%',
  next_day_change_pct DECIMAL(10,4) NULL COMMENT '次日涨幅%',
  source_time VARCHAR(32) DEFAULT '' COMMENT '数据源时间字段',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_period_code (date, period, code),
  INDEX idx_date_period (date, period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='竞价抢筹日快照';
