-- 清理 dragon_tiger_seats 历史重复数据（一次性执行）
-- 规则：同一 (date, code, direction, seat_name, buy_amount, sell_amount, net_amount)
-- 只保留 id 最小的一条，删除其余重复记录。

START TRANSACTION;

DELETE s1
FROM dragon_tiger_seats s1
INNER JOIN dragon_tiger_seats s2
  ON s1.date = s2.date
  AND s1.code = s2.code
  AND s1.direction = s2.direction
  AND s1.seat_name = s2.seat_name
  AND s1.buy_amount = s2.buy_amount
  AND s1.sell_amount = s2.sell_amount
  AND s1.net_amount = s2.net_amount
  AND s1.id > s2.id;

COMMIT;

-- 可选校验：执行后结果应为空
-- SELECT date, code, direction, seat_name, buy_amount, sell_amount, net_amount, COUNT(*) AS cnt
-- FROM dragon_tiger_seats
-- GROUP BY date, code, direction, seat_name, buy_amount, sell_amount, net_amount
-- HAVING cnt > 1;
