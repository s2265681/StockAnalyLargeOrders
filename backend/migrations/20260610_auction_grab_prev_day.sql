-- 竞价抢筹：补充昨日涨幅持久化字段
ALTER TABLE auction_grab_stocks
  ADD COLUMN IF NOT EXISTS prev_day_change_pct DECIMAL(10,4) NULL COMMENT '昨日（上一交易日）涨幅%';
