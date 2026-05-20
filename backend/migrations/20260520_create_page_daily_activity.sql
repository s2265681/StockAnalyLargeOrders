-- 页面日活：同一用户同一天同一页面只记一条
CREATE TABLE IF NOT EXISTS page_daily_activity (
  user_id INT NOT NULL,
  page VARCHAR(50) NOT NULL COMMENT '如 stock-dashboard',
  activity_date DATE NOT NULL,
  first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, page, activity_date),
  INDEX idx_page_date (page, activity_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
