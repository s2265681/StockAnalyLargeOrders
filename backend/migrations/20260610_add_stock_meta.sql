-- 股票基本信息缓存（行业、题材），从涨停池汇总，避免重复查询
CREATE TABLE IF NOT EXISTS stock_meta (
    code VARCHAR(6) PRIMARY KEY,
    name VARCHAR(30) DEFAULT '',
    industry VARCHAR(50) DEFAULT '',
    concepts VARCHAR(200) DEFAULT '',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票行业/题材缓存';
