-- 竞价抢筹评分字段：拆分接口后后台异步写入
ALTER TABLE auction_grab_stocks
  ADD COLUMN IF NOT EXISTS recommend_stars TINYINT NULL COMMENT '推荐星级 0-3',
  ADD COLUMN IF NOT EXISTS recommend_reason VARCHAR(100) NULL COMMENT '推荐理由',
  ADD COLUMN IF NOT EXISTS recommend_score DECIMAL(10,2) NULL COMMENT '推荐综合评分';

-- 每日情绪阶段+提示（全局，非逐股）
CREATE TABLE IF NOT EXISTS auction_grab_score_meta (
  id INT AUTO_INCREMENT PRIMARY KEY,
  date VARCHAR(8) NOT NULL COMMENT '交易日期 YYYYMMDD',
  period TINYINT NOT NULL DEFAULT 0 COMMENT '0=早盘 1=尾盘',
  emotion_stage VARCHAR(20) DEFAULT '' COMMENT '情绪阶段',
  recommend_hint VARCHAR(200) DEFAULT '' COMMENT '推荐提示语',
  score_ready TINYINT DEFAULT 0 COMMENT '1=评分已就绪',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_date_period (date, period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='竞价抢筹评分元数据';
