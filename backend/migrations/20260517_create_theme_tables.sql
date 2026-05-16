-- 题材标签与涨停池缓存表
-- 支撑 /api/v1/limit_up_themes、涨停梯队历史、题材人工维护等接口。

CREATE TABLE IF NOT EXISTS theme_tags (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL COMMENT '交易日期，格式YYYYMMDD',
  tag_name VARCHAR(80) NOT NULL COMMENT '题材标签名称',
  reason TEXT COMMENT '题材归纳原因',
  source VARCHAR(30) NOT NULL DEFAULT 'ai' COMMENT '来源：ai/manual/import',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_tag (date, tag_name),
  INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='涨停题材标签';

CREATE TABLE IF NOT EXISTS limit_up_stocks (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL COMMENT '交易日期，格式YYYYMMDD',
  code VARCHAR(6) NOT NULL COMMENT '股票代码',
  name VARCHAR(30) DEFAULT '' COMMENT '股票名称',
  boards INT DEFAULT 1 COMMENT '连板数',
  tag_name VARCHAR(80) DEFAULT '' COMMENT '所属题材标签',
  price DECIMAL(10,2) DEFAULT 0 COMMENT '最新价/收盘价',
  change_pct DECIMAL(8,4) DEFAULT 0 COMMENT '涨跌幅',
  seal_amount DECIMAL(20,2) DEFAULT 0 COMMENT '封单金额',
  turnover DECIMAL(20,2) DEFAULT 0 COMMENT '成交额',
  seal_ratio DECIMAL(10,4) DEFAULT 0 COMMENT '封成比',
  turnover_rate DECIMAL(10,4) DEFAULT 0 COMMENT '换手率',
  float_mv DECIMAL(20,2) DEFAULT 0 COMMENT '流通市值',
  first_time VARCHAR(20) DEFAULT '' COMMENT '首次封板时间',
  last_time VARCHAR(20) DEFAULT '' COMMENT '最后封板时间',
  break_count INT DEFAULT 0 COMMENT '炸板次数',
  industry VARCHAR(80) DEFAULT '' COMMENT '行业',
  zt_stat VARCHAR(50) DEFAULT '' COMMENT '涨停统计描述',
  ths_rank INT DEFAULT 0 COMMENT '同花顺热度/排序',
  ths_analyse TEXT COMMENT '同花顺分析',
  ths_analyse_title VARCHAR(255) DEFAULT '' COMMENT '同花顺分析标题',
  is_leader TINYINT(1) DEFAULT 0 COMMENT '是否题材龙头',
  leader_role VARCHAR(50) DEFAULT '' COMMENT '龙头定位',
  leader_reason VARCHAR(255) DEFAULT '' COMMENT '龙头理由',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_code (date, code),
  INDEX idx_date (date),
  INDEX idx_date_tag (date, tag_name),
  INDEX idx_date_boards (date, boards)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='涨停股票缓存';
