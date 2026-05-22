-- 为 alert_rules 增加冷却时间支持
ALTER TABLE alert_rules
  ADD COLUMN IF NOT EXISTS last_notified_at DATETIME DEFAULT NULL COMMENT '最近一次通知时间，用于冷却判断',
  ADD COLUMN IF NOT EXISTS repeat_minutes   INT      NOT NULL DEFAULT 0 COMMENT '重复提醒间隔分钟，0=一次性';

-- seal_order 类型的规则默认每5分钟重复提醒
UPDATE alert_rules SET repeat_minutes = 5 WHERE alert_type = 'seal_order';

-- 微信通知队列
CREATE TABLE IF NOT EXISTS wechat_notification_queue (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    rule_id    INT          NOT NULL,
    message    TEXT         NOT NULL,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent       TINYINT      NOT NULL DEFAULT 0,
    INDEX idx_unsent (sent, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
