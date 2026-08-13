-- 竞价抢筹高级筛选结果缓存（cron 9:25/9:30 预计算，接口直读）
CREATE TABLE IF NOT EXISTS auction_grab_screen_cache (
  date CHAR(8) NOT NULL COMMENT 'YYYYMMDD',
  period TINYINT NOT NULL COMMENT '0=早盘 1=尾盘',
  items_json MEDIUMTEXT NOT NULL COMMENT '筛选结果 JSON 数组',
  limit_up_by_industry_json TEXT COMMENT '同行业涨停数 JSON',
  item_count INT NOT NULL DEFAULT 0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (date, period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='竞价抢筹高级筛选缓存';
