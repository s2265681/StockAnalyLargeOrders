/** A 股交易时段（本地时间，周一至周五） */
export function isAShareMarketOpen(now = new Date()): boolean {
  const day = now.getDay();
  if (day === 0 || day === 6) return false;

  const minutes = now.getHours() * 60 + now.getMinutes();
  const morning = minutes >= 9 * 60 + 15 && minutes <= 11 * 60 + 30;
  const afternoon = minutes >= 13 * 60 && minutes <= 15 * 60;
  return morning || afternoon;
}
