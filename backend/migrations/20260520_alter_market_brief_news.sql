ALTER TABLE market_brief
    ADD COLUMN news_json TEXT NULL COMMENT '多源资讯原始条目 JSON' AFTER overseas_json;
