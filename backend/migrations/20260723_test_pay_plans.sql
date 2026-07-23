-- 测试套餐 plan_type 扩展
ALTER TABLE orders
  MODIFY plan_type ENUM('daily','test2','monthly','quarterly','semi','annual') NOT NULL;

ALTER TABLE user_subscriptions
  MODIFY plan_type ENUM('daily','test2','monthly','quarterly','semi','annual') NOT NULL;
