-- 板块抢筹日快照：板块列表 + 板块内个股

CREATE TABLE IF NOT EXISTS sector_grab_sectors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL COMMENT '交易日期 YYYYMMDD',
  gn_code VARCHAR(16) NOT NULL COMMENT '板块代码',
  name VARCHAR(64) DEFAULT '' COMMENT '板块名称',
  strength INT DEFAULT 0 COMMENT '强度',
  strength_change INT DEFAULT 0 COMMENT '强度变化',
  change_pct DECIMAL(10,4) DEFAULT 0 COMMENT '涨幅%',
  limit_up_count INT DEFAULT 0 COMMENT '涨停家数',
  is_hot TINYINT DEFAULT 0 COMMENT '是否热门',
  sort_order INT DEFAULT 0 COMMENT '排序',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_gn (date, gn_code),
  INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块抢筹-板块日快照';

CREATE TABLE IF NOT EXISTS sector_grab_stocks (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL COMMENT '交易日期 YYYYMMDD',
  gn_code VARCHAR(16) NOT NULL COMMENT '板块代码',
  code VARCHAR(6) NOT NULL COMMENT '股票代码',
  name VARCHAR(30) DEFAULT '' COMMENT '股票名称',
  change_pct DECIMAL(10,4) DEFAULT 0 COMMENT '涨幅%',
  turnover_pct DECIMAL(10,4) DEFAULT 0 COMMENT '换手率%',
  speed DECIMAL(16,2) DEFAULT 0 COMMENT '涨速/主力净流入',
  leader_rank VARCHAR(16) DEFAULT '' COMMENT '领涨 龙一/龙二',
  main_force VARCHAR(32) DEFAULT '' COMMENT '主力类型',
  board_label VARCHAR(32) DEFAULT '' COMMENT '连板标签',
  sectors VARCHAR(256) DEFAULT '' COMMENT '所属板块',
  popularity INT DEFAULT 0 COMMENT '人气排名',
  price DECIMAL(12,4) DEFAULT 0 COMMENT '价格',
  score DECIMAL(10,2) DEFAULT 0 COMMENT '评分',
  raw_json JSON NULL COMMENT '原始字段',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_gn_code (date, gn_code, code),
  INDEX idx_date_gn (date, gn_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块抢筹-个股日快照';
