-- 龙虎榜席位关键词映射表
-- 用于将营业部名称映射为游资人物/派系标签

CREATE TABLE IF NOT EXISTS dragon_tiger_seat_aliases (
  id INT AUTO_INCREMENT PRIMARY KEY,
  keyword VARCHAR(120) NOT NULL COMMENT '营业部名称关键词（用于包含匹配）',
  trader_tag VARCHAR(60) NOT NULL COMMENT '展示标签，如成都系/炒股养家',
  priority INT NOT NULL DEFAULT 100 COMMENT '同长度关键词冲突时优先级，越大越优先',
  source VARCHAR(30) NOT NULL DEFAULT 'manual' COMMENT '来源：manual/ths/import',
  is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_keyword (keyword),
  INDEX idx_active_priority (is_active, priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='龙虎榜席位关键词映射';

-- 初始常用映射（可持续补充）
INSERT INTO dragon_tiger_seat_aliases (keyword, trader_tag, priority, source, is_active) VALUES
('国泰海通证券股份有限公司成都北一环路证券营业部', '成都系', 200, 'manual', 1),
('成都北一环路', '成都系', 180, 'manual', 1),
('华鑫证券有限责任公司上海茅台路证券营业部', '炒股养家', 200, 'manual', 1),
('上海茅台路', '炒股养家', 180, 'manual', 1),
('中国银河证券股份有限公司绍兴证券营业部', '赵老哥', 190, 'manual', 1),
('绍兴证券营业部', '赵老哥', 150, 'manual', 1),
('中信证券股份有限公司浙江分公司', '章盟主', 160, 'manual', 1),
('华鑫证券有限责任公司上海分公司', '方新侠', 160, 'manual', 1),
('华泰证券股份有限公司天津东丽开发区二纬路证券营业部', '欢乐海岸', 200, 'manual', 1),
('国盛证券宁波桑田路证券营业部', '桑田路', 190, 'manual', 1),
('中信证券股份有限公司西安朱雀大街证券营业部', '西安朱雀', 170, 'manual', 1),
('东方财富证券股份有限公司拉萨金融城南环路证券营业部', '拉萨天团', 180, 'manual', 1),
('东方财富证券股份有限公司拉萨团结路第一证券营业部', '拉萨天团', 180, 'manual', 1),
('东方财富证券股份有限公司拉萨东环路第二证券营业部', '拉萨天团', 180, 'manual', 1),
('深股通专用', '北向资金', 220, 'manual', 1),
('沪股通专用', '北向资金', 220, 'manual', 1),

-- 以下为图片提取的常用席位映射
('光大证券深圳金田路', '金田路', 180, 'manual', 1),
('平安证券福州长乐北路', '温州帮', 170, 'manual', 1),
('高盛(中国)上海浦东新区世纪大道', '量化基金', 180, 'manual', 1),
('华鑫证券上海宛平南路', '炒股养家', 210, 'manual', 1),
('平安证券浙江分公司', '温州帮', 160, 'manual', 1),
('华泰证券江阴福泰路', '温州帮', 160, 'manual', 1),
('开源证券西安太华路', '量化打板', 165, 'manual', 1),
('华鑫证券上海陆家嘴', '量化打板', 165, 'manual', 1),
('东方证券上海松江区沪亭北路', '温州帮', 170, 'manual', 1),
('长江证券深圳福华路', '温州帮', 165, 'manual', 1),
('东方证券上海浦东新区源深路', '徐晓峰', 175, 'manual', 1),
('国泰海通证券上海松江区中山东路', '中山东路', 185, 'manual', 1),
('中金公司上海分公司', '量化基金', 175, 'manual', 1),
('长江证券惠州金山湖', '佛山系', 175, 'manual', 1),
('东亚前海证券上海分公司', '思明南路', 180, 'manual', 1),
('国盛证券宁波桑田路', '宁波团团', 190, 'manual', 1),
('国信证券宁波桑田路', '宁波团团', 185, 'manual', 1),
('国泰海通证券三亚迎宾路', '佛山系', 175, 'manual', 1),
('中信证券深圳分公司', '欢乐海岸', 170, 'manual', 1)
ON DUPLICATE KEY UPDATE
  trader_tag = VALUES(trader_tag),
  priority = VALUES(priority),
  source = VALUES(source),
  is_active = VALUES(is_active),
  updated_at = CURRENT_TIMESTAMP;
