-- 用户常用邮箱（条件预警等通知默认收件地址）
ALTER TABLE users
  ADD COLUMN default_email VARCHAR(128) DEFAULT NULL AFTER phone;
