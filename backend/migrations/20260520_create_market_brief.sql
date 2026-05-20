CREATE TABLE IF NOT EXISTS market_brief (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    brief_date   DATE     NOT NULL,
    overseas_json TEXT    NOT NULL,
    ai_summary   TEXT     NOT NULL,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_date (brief_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
