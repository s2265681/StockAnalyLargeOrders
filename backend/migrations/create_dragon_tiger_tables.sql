-- backend/migrations/create_dragon_tiger_tables.sql

CREATE TABLE IF NOT EXISTS dragon_tiger_daily (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL COMMENT '格式YYYYMMDD',
  code VARCHAR(6) NOT NULL,
  name VARCHAR(20) NOT NULL,
  change_pct DECIMAL(8,4) DEFAULT 0 COMMENT '涨跌幅',
  close_price DECIMAL(10,2) DEFAULT 0,
  net_buy DECIMAL(20,2) DEFAULT 0 COMMENT '龙虎榜净买额(元)',
  buy_amount DECIMAL(20,2) DEFAULT 0 COMMENT '龙虎榜买入额',
  sell_amount DECIMAL(20,2) DEFAULT 0 COMMENT '龙虎榜卖出额',
  lhb_amount DECIMAL(20,2) DEFAULT 0 COMMENT '龙虎榜成交额',
  total_amount DECIMAL(20,2) DEFAULT 0 COMMENT '市场总成交额',
  reason VARCHAR(300) DEFAULT '' COMMENT '上榜原因',
  interpret VARCHAR(200) DEFAULT '' COMMENT '解读',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_code (date, code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='龙虎榜每日股票列表';

CREATE TABLE IF NOT EXISTS dragon_tiger_seats (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL,
  code VARCHAR(6) NOT NULL,
  direction ENUM('buy','sell') NOT NULL COMMENT '买入/卖出席位',
  rank_no INT NOT NULL COMMENT '席位排名1-5',
  seat_name VARCHAR(150) DEFAULT '' COMMENT '营业部名称',
  buy_amount DECIMAL(20,2) DEFAULT 0 COMMENT '买入金额',
  sell_amount DECIMAL(20,2) DEFAULT 0 COMMENT '卖出金额',
  net_amount DECIMAL(20,2) DEFAULT 0 COMMENT '净额',
  is_hot_money TINYINT(1) DEFAULT 0 COMMENT '是否游资席位',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_date_code (date, code),
  INDEX idx_date_code_dir (date, code, direction)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='龙虎榜席位明细';

CREATE TABLE IF NOT EXISTS dragon_tiger_ai (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL,
  code VARCHAR(6) NOT NULL,
  analysis TEXT COMMENT 'AI分析内容',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_code (date, code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='龙虎榜AI分析结果';
