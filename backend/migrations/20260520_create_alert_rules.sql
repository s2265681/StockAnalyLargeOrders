CREATE TABLE IF NOT EXISTS alert_rules (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT          NOT NULL,
    code          VARCHAR(10)  NOT NULL,
    stock_name    VARCHAR(20)  NOT NULL DEFAULT '',
    alert_type    VARCHAR(20)  NOT NULL COMMENT 'change_pct / limit_up / limit_down / seal_order',
    threshold     FLOAT        DEFAULT NULL,
    direction     VARCHAR(5)   DEFAULT NULL COMMENT 'above / below，仅 change_pct 使用',
    email         VARCHAR(100) NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active / triggered / disabled',
    triggered_at  DATETIME     DEFAULT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_status (user_id, status),
    INDEX idx_code_status (code, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
