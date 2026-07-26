-- 微信网页扫码登录：为 users 表增加微信身份字段
-- 创建时间: 2026-07-26
-- 说明：微信登录用户无密码，password_hash 需可空；openid/unionid 作为身份唯一标识

ALTER TABLE users
  MODIFY COLUMN password_hash VARCHAR(255) NULL;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS wechat_openid VARCHAR(64) DEFAULT NULL AFTER default_email,
  ADD COLUMN IF NOT EXISTS wechat_unionid VARCHAR(64) DEFAULT NULL AFTER wechat_openid,
  ADD COLUMN IF NOT EXISTS nickname VARCHAR(64) DEFAULT NULL AFTER wechat_unionid,
  ADD COLUMN IF NOT EXISTS avatar VARCHAR(512) DEFAULT NULL AFTER nickname;

-- unionid 优先作为跨应用唯一身份；openid 为网站应用内唯一
ALTER TABLE users
  ADD UNIQUE INDEX IF NOT EXISTS uniq_wechat_unionid (wechat_unionid),
  ADD UNIQUE INDEX IF NOT EXISTS uniq_wechat_openid (wechat_openid);
