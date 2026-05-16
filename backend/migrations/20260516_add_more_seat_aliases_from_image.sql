-- 根据新增图片补充的席位映射（仅加入可明确识别的标签）

INSERT INTO dragon_tiger_seat_aliases (keyword, trader_tag, priority, source, is_active) VALUES
('华泰证券北京月坛南街', '独股一剑', 180, 'manual', 1),
('平安证券宁波海晏北路', '席文斌', 175, 'manual', 1),
('东方证券厦门仙岳路', '山东帮', 170, 'manual', 1),
('华泰证券总部', '量化基金', 165, 'manual', 1),
('上海证券苏州人民路', '涅槃重升', 175, 'manual', 1)
ON DUPLICATE KEY UPDATE
  trader_tag = VALUES(trader_tag),
  priority = VALUES(priority),
  source = VALUES(source),
  is_active = VALUES(is_active),
  updated_at = CURRENT_TIMESTAMP;
