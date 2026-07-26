-- 微信支付订单字段扩展
-- 执行时间: 2026-07-23

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS payment_channel VARCHAR(20) DEFAULT NULL COMMENT 'wechat | mock' AFTER status,
  ADD COLUMN IF NOT EXISTS transaction_id VARCHAR(64) DEFAULT NULL COMMENT '微信支付订单号' AFTER payment_channel,
  ADD COLUMN IF NOT EXISTS paid_at DATETIME DEFAULT NULL COMMENT '支付完成时间' AFTER transaction_id;

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_transaction_id ON orders (transaction_id);
