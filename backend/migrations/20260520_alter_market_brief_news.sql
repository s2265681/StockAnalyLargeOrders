-- 幂等：列已存在时跳过（部署脚本会重复执行全部 migration）
SET @col_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'market_brief'
      AND COLUMN_NAME = 'news_json'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE market_brief ADD COLUMN news_json TEXT NULL COMMENT ''多源资讯原始条目 JSON'' AFTER overseas_json',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
