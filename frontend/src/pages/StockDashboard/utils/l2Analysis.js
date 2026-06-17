export const getFlowTone = (value) => {
  if (value > 0) return 'positive';
  if (value < 0) return 'negative';
  return 'neutral';
};

export const isSameStockCode = (a, b) => {
  if (a == null || b == null) return false;
  return String(a) === String(b);
};

/** 从 stock_info 构建分时 base_info，避免多写入路径字段不一致 */
export const buildTimeshareBaseInfo = (stockInfo, fallbackCode, prevBaseInfo = null) => {
  const next = {
    code: stockInfo?.code ?? fallbackCode,
    prevClosePrice: stockInfo?.yesterday_close ?? stockInfo?.pre_close,
    openPrice: stockInfo?.open,
    highPrice: stockInfo?.high,
    lowPrice: stockInfo?.low,
    limit_up: stockInfo?.limit_up,
    limit_down: stockInfo?.limit_down,
  };
  if (!prevBaseInfo || !isSameStockCode(next.code, prevBaseInfo.code)) {
    return next;
  }
  return {
    ...prevBaseInfo,
    ...next,
    prevClosePrice: next.prevClosePrice ?? prevBaseInfo.prevClosePrice,
    openPrice: next.openPrice ?? prevBaseInfo.openPrice,
    highPrice: next.highPrice ?? prevBaseInfo.highPrice,
    lowPrice: next.lowPrice ?? prevBaseInfo.lowPrice,
    limit_up: next.limit_up ?? prevBaseInfo.limit_up,
    limit_down: next.limit_down ?? prevBaseInfo.limit_down,
  };
};

/** 昨收是否与分时价格序列同量级（防止 header 实时价 + 历史分时错配） */
export const isPrevCloseConsistentWithFenshi = (prevClose, fenshi) => {
  const prev = parseFloat(prevClose);
  if (!Number.isFinite(prev) || prev <= 0) return false;
  const prices = (fenshi || [])
    .map((p) => parseFloat(p))
    .filter((p) => Number.isFinite(p) && p > 0);
  if (!prices.length) return true;
  const last = prices[prices.length - 1];
  const relDiff = Math.abs((last - prev) / prev);
  const absDiff = Math.abs(last - prev);
  return relDiff <= 0.05 || absDiff <= 0.15;
};

/** 分时末价与参考价（通常为 header 现价）偏离过大，视为脏数据 */
export const isTimesharePriceStale = (fenshi, referencePrice, threshold = 0.05) => {
  const prices = (fenshi || [])
    .map((p) => parseFloat(p))
    .filter((p) => Number.isFinite(p) && p > 0);
  if (!prices.length) return false;
  const ref = parseFloat(referencePrice);
  if (!Number.isFinite(ref) || ref <= 0) return false;
  const last = prices[prices.length - 1];
  return Math.abs(last - ref) / ref > threshold;
};

const formatNumber = (value, digits = 2) => Number(value || 0).toFixed(digits);

export const buildAnalysisCards = (analysis = {}) => [
  {
    key: 'orders',
    label: '大单笔数',
    value: String(analysis.total_large_orders || 0),
    suffix: '笔',
    tone: 'neutral',
  },
  {
    key: 'amount',
    label: '大单金额',
    value: formatNumber(analysis.total_amount),
    suffix: '万',
    tone: 'neutral',
  },
  {
    key: 'net',
    label: '净流入',
    value: formatNumber(analysis.net_inflow),
    suffix: '万',
    tone: getFlowTone(analysis.net_inflow || 0),
  },
  {
    key: 'ratio',
    label: '买入占比',
    value: formatNumber(analysis.buy_ratio, 1),
    suffix: '%',
    tone: getFlowTone((analysis.buy_ratio || 0) - 50),
  },
  {
    key: 'score',
    label: '压力强度',
    value: formatNumber(analysis.pressure_score),
    suffix: '%',
    tone: getFlowTone(analysis.pressure_score || 0),
  },
];

export const buildTradingTimeAxis = () => {
  const timePoints = [];

  // 不含集合竞价时段，分时图从连续竞价 09:30 起
  for (let hour = 9; hour <= 11; hour++) {
    const startMinute = hour === 9 ? 30 : 0;
    const endMinute = hour === 11 ? 30 : 59;
    for (let minute = startMinute; minute <= endMinute; minute++) {
      timePoints.push(`${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`);
    }
  }

  for (let hour = 13; hour <= 15; hour++) {
    const endMinute = hour === 15 ? 0 : 59;
    for (let minute = 0; minute <= endMinute; minute++) {
      timePoints.push(`${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`);
    }
  }

  return timePoints;
};

export const alignTimeshareToTradingAxis = (timeshare = []) => {
  const axis = buildTradingTimeAxis();
  const byTime = new Map(timeshare.map(item => [item.time, item]));

  const resolvePointPrice = (item) => {
    if (!item) return null;
    const price = item.price ?? item.avg_price;
    const value = parseFloat(price);
    return Number.isFinite(value) ? value : null;
  };

  return {
    axis,
    fenshi: axis.map((time) => resolvePointPrice(byTime.get(time))),
    volume: axis.map(time => byTime.get(time)?.volume ?? 0),
  };
};

/** 同花顺 time 可能是 "0930" 或 "09:30"，统一为交易轴格式 */
export const normalizeFlowTimeKey = (time) => {
  const text = String(time || '').trim();
  if (!text) return '';
  if (text.includes(':')) return text;
  if (text.length === 4) return `${text.slice(0, 2)}:${text.slice(2)}`;
  return text;
};

/** 把 money_flow 各序列按分钟对齐到 buildTradingTimeAxis() */
export const alignMoneyFlowToTradingAxis = (moneyFlow) => {
  if (!moneyFlow) return null;

  const axis = buildTradingTimeAxis();
  const sourceTimes = moneyFlow.time || [];
  const indexByTime = new Map();
  sourceTimes.forEach((rawTime, index) => {
    indexByTime.set(normalizeFlowTimeKey(rawTime), index);
  });

  const alignSeries = (series = []) => axis.map((time) => {
    const index = indexByTime.get(time);
    if (index === undefined || index >= series.length) return null;
    const value = series[index];
    return value == null || value === '' ? null : value;
  });

  return {
    ...moneyFlow,
    time: axis,
    chaoda: alignSeries(moneyFlow.chaoda),
    sanhu: alignSeries(moneyFlow.sanhu),
    dadan: alignSeries(moneyFlow.dadan),
    zhongdan: alignSeries(moneyFlow.zhongdan),
    chaoda_delta: alignSeries(moneyFlow.chaoda_delta),
    sanhu_delta: alignSeries(moneyFlow.sanhu_delta),
  };
};

/**
 * 资金博弈线 Y 值：分钟净额为 0（同花顺无更新）时沿用上一有效点，避免午后拐头。
 */
export const buildFlowLineSeriesData = ({
  axis,
  fenshi,
  scores = [],
  minuteDeltas = [],
  yMid,
  yRange,
  maxAbsFlow,
  holdEpsilon = 0.5,
}) => {
  const points = [];
  let lastY = null;

  for (let i = 0; i < axis.length; i++) {
    const timePoint = axis[i];
    if (!timePoint || fenshi[i] == null || fenshi[i] === '') {
      points.push([timePoint || '', null]);
      continue;
    }

    const delta = parseFloat(minuteDeltas[i]);
    const hasMinuteUpdate = Number.isFinite(delta) && Math.abs(delta) >= holdEpsilon;
    const raw = parseFloat(scores[i]);

    if (!hasMinuteUpdate && lastY != null) {
      points.push([timePoint, lastY]);
      continue;
    }

    const safeRaw = Number.isFinite(raw) ? raw : 0;
    const y = yMid + (safeRaw / maxAbsFlow) * yRange;
    lastY = y;
    points.push([timePoint, y]);
  }

  return points;
};

const sumOrderAmount = (orders, type) => orders
  .filter(order => order.type === type)
  .reduce((sum, order) => sum + Number(order.amount || 0), 0);

/** 按主动/被动分别统计大单金额 */
const sumOrderByActivity = (orders, type) => {
  const matched = orders.filter(order => order.type === type);
  const active = matched.filter(o => (o.direction || '').startsWith('主'));
  const passive = matched.filter(o => (o.direction || '').startsWith('被'));
  // 没有 direction 字段的订单（兼容旧数据）归入 unknown
  const unknown = matched.filter(o => !o.direction || (!(o.direction).startsWith('主') && !(o.direction).startsWith('被')));
  return {
    active: active.reduce((s, o) => s + Number(o.amount || 0), 0),
    passive: passive.reduce((s, o) => s + Number(o.amount || 0), 0),
    unknown: unknown.reduce((s, o) => s + Number(o.amount || 0), 0),
    total: matched.reduce((s, o) => s + Number(o.amount || 0), 0),
  };
};

/** 计算加权大单金额：主动权重1.0，被动权重0.3，无分类信息默认权重1.0 */
const weightedAmount = (detail) => detail.active + detail.passive * 0.3 + (detail.unknown || 0);

const getValidPrices = (timeshareData = {}) => ((timeshareData || {}).fenshi || [])
  .filter(price => price !== null && price !== undefined && !Number.isNaN(Number(price)))
  .map(Number);

/** 检测价格趋势强度：返回 -1~1，负值=持续下跌，正值=持续上涨 */
const calcTrendStrength = (prices) => {
  if (prices.length < 3) return 0;
  const sample = prices.length > 20 ? prices.slice(-20) : prices;
  let drops = 0;
  let rises = 0;
  for (let i = 1; i < sample.length; i++) {
    if (sample[i] < sample[i - 1]) drops++;
    else if (sample[i] > sample[i - 1]) rises++;
  }
  const total = sample.length - 1;
  return (rises - drops) / total; // -1 = 全部下跌, +1 = 全部上涨
};

export const buildHandicapLanguage = ({ timeshareData = {}, largeOrdersData = {}, moneyflowData = null } = {}) => {
  const prices = getValidPrices(timeshareData);
  const orders = (largeOrdersData || {}).largeOrders || [];
  const orderBook = (timeshareData || {}).order_book || {};

  // 同花顺资金流汇总
  const mfSummary = (moneyflowData && moneyflowData.success) ? moneyflowData.summary || {} : {};
  const mfAvailable = Object.keys(mfSummary).length > 0;
  const mainNetWan = mfSummary.main_net_wan || 0;         // 主力净额（万）
  const superBigNetWan = mfSummary.super_big_net_wan || 0; // 超大单净额（万）

  if (prices.length === 0) {
    return {
      primaryLabel: '等待数据',
      tone: 'neutral',
      score: 50,
      tags: ['观察'],
      reasons: ['分时数据不足，暂不判断盘口语言'],
      advice: '先等待分时和大单数据更新，再观察开盘价、均线和大单方向。',
    };
  }

  const currentPrice = prices[prices.length - 1];
  const openPrice = Number(timeshareData.base_info?.openPrice || prices[0]);
  const prevClosePrice = Number(timeshareData.base_info?.prevClosePrice || openPrice);
  const changePercent = prevClosePrice
    ? parseFloat(((currentPrice - prevClosePrice) / prevClosePrice * 100).toFixed(2))
    : null;
  const avgPrice = prices.reduce((sum, price) => sum + price, 0) / prices.length;
  const highPrice = Math.max(...prices);
  const lowPrice = Math.min(...prices);
  const rangePercent = openPrice ? ((highPrice - lowPrice) / openPrice) * 100 : 0;

  // --- 大单：按主动/被动分别统计 ---
  const buyDetail = sumOrderByActivity(orders, 'buy');
  const sellDetail = sumOrderByActivity(orders, 'sell');
  const buyAmount = buyDetail.total;
  const sellAmount = sellDetail.total;
  // 加权金额：主动成交权重高，被动成交权重低
  const wBuy = weightedAmount(buyDetail);
  const wSell = weightedAmount(sellDetail);
  const wTotal = wBuy + wSell;
  const wBuyRatio = wTotal ? wBuy / wTotal : 0.5;
  const totalAmount = buyAmount + sellAmount;
  const buyRatio = totalAmount ? buyAmount / totalAmount : 0.5;

  const bidAmount = Number(orderBook.bid_amount || 0);
  const askAmount = Number(orderBook.ask_amount || 0);
  const bookTotalAmount = bidAmount + askAmount;
  const bookAvailable = bookTotalAmount > 0;
  const bookBidRatio = bookTotalAmount ? bidAmount / bookTotalAmount : 0.5;
  const bid1Amount = Number(orderBook.bids?.[0]?.amount || 0);
  const ask1Amount = Number(orderBook.asks?.[0]?.amount || 0);
  const aboveOpen = currentPrice >= openPrice;
  const aboveAvg = currentPrice >= avgPrice;
  const recent = prices.slice(-5);
  const rising = recent.length >= 2 && recent[recent.length - 1] >= recent[0];

  // --- 价格趋势 ---
  const trendStrength = calcTrendStrength(prices);
  const absChange = Math.abs(changePercent || 0);
  const isLimitDown = changePercent !== null && changePercent <= -9.5;
  const isNearLimitDown = changePercent !== null && changePercent <= -7;
  const isLimitUp = changePercent !== null && changePercent >= 9.5;
  const isNearLimitUp = changePercent !== null && changePercent >= 7;
  const isStrongDrop = changePercent !== null && changePercent <= -4 && trendStrength < -0.4;
  const isStrongRise = changePercent !== null && changePercent >= 4 && trendStrength > 0.4;

  const tags = [];
  const reasons = [];

  let primaryLabel = '夹单震荡';
  let tone = 'neutral';
  let score = 50;
  let advice = '买卖力量接近，先观察是否放量突破均线或跌破开盘价。';

  // === 最高优先级：极端行情（跌停/涨停区域），价格走势直接定性 ===
  if (isLimitDown) {
    primaryLabel = '跌停崩溃';
    tone = 'negative';
    score = 8;
    tags.push('跌停', '极弱');
    reasons.push('股价已至跌停板，卖方完全主导');
    if (buyAmount > sellAmount) {
      reasons.push('大单显示买多卖少，但多为被动成交或跌停挂单承接，非主动买入');
    }
    advice = '跌停板不可操作，切勿抄底。等开板后观察成交量和资金流向再判断。';
  } else if (isLimitUp) {
    primaryLabel = '涨停封板';
    tone = 'positive';
    score = 92;
    tags.push('涨停', '极强');
    reasons.push('股价已至涨停板，买方完全主导');
    advice = '涨停封板中，关注封单量是否稳固，注意尾盘炸板风险。';
  } else if (isNearLimitDown) {
    primaryLabel = '急速杀跌';
    tone = 'negative';
    score = 15;
    tags.push('暴跌', '风险');
    reasons.push(`跌幅${changePercent}%，接近跌停板`);
    if (trendStrength < -0.5) reasons.push('价格持续单边下行，无有效反弹');
    if (buyAmount > sellAmount) reasons.push('大单买入多为被动承接，未能阻止下跌');
    advice = '极弱走势，避免抄底。等跌势企稳、出现放量反弹信号后再观察。';
  } else if (isNearLimitUp) {
    primaryLabel = '强势冲板';
    tone = 'positive';
    score = 85;
    tags.push('冲板', '强势');
    reasons.push(`涨幅${changePercent}%，接近涨停板`);
    if (trendStrength > 0.5) reasons.push('价格持续上攻，多方强势');
    advice = '高位强势，注意追高风险，关注是否能封涨停。';
  // === 次优先级：强趋势行情，价格走势权重高于大单 ===
  } else if (isStrongDrop) {
    primaryLabel = '单边下杀';
    tone = 'negative';
    score = 22;
    tags.push('杀跌', '趋势空');
    reasons.push(`跌幅${changePercent}%，价格持续走低`);
    if (wBuyRatio > 0.6) {
      reasons.push('大单买入占比高但多为被动成交，主动卖压主导实际走势');
    } else {
      reasons.push('大单卖出力量明显');
    }
    advice = '下跌趋势明确，不宜抄底。等止跌企稳并出现主动买入放量信号后再观察。';
  } else if (isStrongRise) {
    primaryLabel = '单边拉升';
    tone = 'positive';
    score = 78;
    tags.push('拉升', '趋势多');
    reasons.push(`涨幅${changePercent}%，价格持续走高`);
    if (wBuyRatio > 0.6) reasons.push('主动买入大单力量强劲');
    advice = '上涨趋势明确，但注意追高风险，可等回踩均线不破后介入。';
  // === 常规判断（使用加权买卖比 wBuyRatio 代替原始 buyRatio）===
  } else if (bookAvailable && askAmount > bidAmount * 1.8) {
    primaryLabel = '上方压单';
    tone = 'negative';
    score = 38;
    tags.push('五档压单', '抛压');
    reasons.push('五档卖盘金额明显大于买盘，短线上方抛压偏重');
    if (ask1Amount > bid1Amount * 1.5) {
      reasons.push('卖一挂单明显厚于买一，靠近盘口有压制');
    }
    advice = '先等压单被主动买单消化，或价格放量站上卖一附近后再看强度；未突破前避免追高。';
  } else if (bookAvailable && bidAmount > askAmount * 1.8) {
    primaryLabel = '下方托单';
    tone = 'positive';
    score = 66;
    tags.push('五档托单', '承接');
    reasons.push('五档买盘金额明显大于卖盘，下方承接偏厚');
    if (bid1Amount > ask1Amount * 1.5) {
      reasons.push('买一挂单明显厚于卖一，盘口短线有托举');
    }
    advice = '偏强观察，可等回踩买盘密集区不破；若托单撤掉且跌破均线，需要降低预期。';
  } else if (wSell > wBuy * 1.3 && (!aboveOpen || !aboveAvg)) {
    primaryLabel = '压单明显';
    tone = 'negative';
    score = 35;
    tags.push('压单', '转弱');
    reasons.push('主动卖出大单金额明显高于主动买入');
    reasons.push(currentPrice < openPrice ? '价格运行在开盘价下方' : '价格未能稳定站上均线');
    advice = '先谨慎，等重新站回均线或开盘价后再看承接，跌破开盘价且卖单放大时避免追高。';
  } else if (wBuy > wSell * 1.3 && aboveAvg) {
    primaryLabel = aboveOpen ? '均线上承接' : '托单修复';
    tone = 'positive';
    score = 68;
    tags.push('堆单', '承接');
    reasons.push('主动买入大单金额明显高于主动卖出');
    reasons.push(aboveOpen ? '价格保持在开盘价上方' : '价格回到均线附近并有承接');
    advice = '偏强观察，可等回踩均线或开盘价不破时看承接，放量上穿前高再确认主动性。';
  } else if (wBuyRatio > 0.58 && rising) {
    primaryLabel = '扫单进攻';
    tone = 'positive';
    score = 74;
    tags.push('扫单', '主动买');
    reasons.push('主动买方大单占优，最近价格重心抬升');
    advice = '进攻信号较强，避免急追，优先等回踩均线不破或突破后缩量回踩确认。';
  } else if (Math.abs(wBuyRatio - 0.5) < 0.12 && rangePercent < 1.2 && orders.length >= 6) {
    primaryLabel = '夹单震荡';
    tone = 'neutral';
    score = 52;
    tags.push('夹单', '等方向');
    reasons.push('买卖大单接近，价格波动区间收窄');
    advice = '方向未选出，等放量突破区间上沿或跌破开盘价后再判断。';
  } else if (!aboveOpen && wSell >= wBuy) {
    primaryLabel = '跌破开盘价';
    tone = 'negative';
    score = 40;
    tags.push('开盘价失守', '谨慎');
    reasons.push('价格低于开盘价，卖方力量不弱');
    advice = '等跌破开盘价后的承接是否出现，重新站回均线前以观察为主。';
  } else if (!aboveOpen && changePercent !== null && changePercent < -2 && trendStrength < -0.3) {
    // 大单显示买多但价格持续下跌 — 被动买入为主，实际偏弱
    primaryLabel = '承接乏力';
    tone = 'negative';
    score = 35;
    tags.push('虚买', '偏弱');
    reasons.push('价格持续下行，大单买入多为被动承接，未能扭转跌势');
    advice = '大单买入未能止跌，说明卖压较重，避免抄底，等止跌信号。';
  } else {
    tags.push('观察');
    reasons.push('当前买卖力量没有形成明显单边盘口语言');
  }

  // 补充大单信息（使用加权比例展示）
  if (totalAmount > 0) {
    const activeBuyPct = Math.round(wBuyRatio * 100);
    reasons.push(`加权买卖大单占比约 ${activeBuyPct}% / ${100 - activeBuyPct}%（主动成交权重高）`);
  }

  if (!bookAvailable) {
    reasons.push('五档盘口暂不可用，当前按分时位置和大单方向降级判断');
  }

  // --- 同花顺资金流信号：交叉验证 + score 微调 ---
  if (mfAvailable) {
    const mainFlowDir = mainNetWan > 0 ? 'in' : mainNetWan < 0 ? 'out' : 'flat';
    const tickDir = wBuyRatio > 0.55 ? 'buy' : wBuyRatio < 0.45 ? 'sell' : 'flat';

    // 资金流与逐笔方向矛盾时：降低 score 可信度
    if (tickDir === 'buy' && mainFlowDir === 'out' && Math.abs(mainNetWan) > 100) {
      score = Math.max(score - 8, 15);
      reasons.push(`主力资金净流出${Math.abs(mainNetWan).toFixed(0)}万，与逐笔买入信号矛盾`);
      if (!tags.includes('虚买')) tags.push('资金背离');
    } else if (tickDir === 'sell' && mainFlowDir === 'in' && Math.abs(mainNetWan) > 100) {
      score = Math.min(score + 8, 85);
      reasons.push(`主力资金净流入${mainNetWan.toFixed(0)}万，卖压可能为洗盘`);
      if (!tags.includes('洗盘')) tags.push('资金托底');
    } else if (mainFlowDir === 'in' && mainNetWan > 500) {
      // 大额主力净流入：增强多方信号
      score = Math.min(score + 5, 85);
      reasons.push(`主力资金大幅净流入${mainNetWan.toFixed(0)}万`);
    } else if (mainFlowDir === 'out' && mainNetWan < -500) {
      // 大额主力净流出：增强空方信号
      score = Math.max(score - 5, 15);
      reasons.push(`主力资金大幅净流出${Math.abs(mainNetWan).toFixed(0)}万`);
    }

    // 超大单独立信号
    if (Math.abs(superBigNetWan) > 200) {
      const sbDir = superBigNetWan > 0 ? '流入' : '流出';
      reasons.push(`超大单净${sbDir}${Math.abs(superBigNetWan).toFixed(0)}万`);
    }
  }

  return {
    primaryLabel,
    tone,
    score,
    tags,
    reasons: reasons.slice(0, 5),
    advice,
    metrics: {
      currentPrice,
      changePercent,
      openPrice,
      avgPrice: Number(avgPrice.toFixed(2)),
      buyAmount,
      sellAmount,
      buyRatio,
      wBuyRatio,
      bookAvailable,
      bidAmount,
      askAmount,
      bookBidRatio,
      spread: Number(orderBook.spread || 0),
      mainNetWan: mfAvailable ? mainNetWan : null,
      superBigNetWan: mfAvailable ? superBigNetWan : null,
    },
  };
};

/** 根据分时列表重算集合竞价与量比（模拟切片用） */
export const recomputeSessionSnapshot = (
  timeshare,
  stockInfo,
  prevSnap = {},
  orderBook = null,
  limitUpData = null,
) => {
  const tk = (t) => String(t?.time || '').slice(0, 5);
  const auction = (timeshare || []).filter((t) => tk(t) && tk(t) < '09:30');
  const sortedA = [...auction].sort((a, b) => tk(a).localeCompare(tk(b)));
  let auctionVol = 0;
  let auctionAmt = 0;
  if (sortedA.length >= 1) {
    const fv = Number(sortedA[0].volume) || 0;
    const lv = Number(sortedA[sortedA.length - 1].volume) || 0;
    const fa = Number(sortedA[0].amount) || 0;
    const la = Number(sortedA[sortedA.length - 1].amount) || 0;
    auctionVol = lv >= fv ? lv - fv : sortedA.reduce((s, t) => s + (Number(t.volume) || 0), 0);
    auctionAmt = la >= fa ? la - fa : sortedA.reduce((s, t) => s + (Number(t.amount) || 0), 0);
  }
  let auctionLast = null;
  sortedA.forEach((t) => {
    if (t.price != null && !Number.isNaN(Number(t.price))) auctionLast = Number(t.price);
  });
  let auctionFromOpenFallback = false;
  const openPx = Number(stockInfo?.open);
  if (auctionLast == null && openPx > 0) {
    auctionLast = openPx;
    auctionFromOpenFallback = true;
  }
  const prevClose = Number(stockInfo?.yesterday_close || 0);
  let auctionChg = null;
  if (auctionLast && prevClose > 0) {
    auctionChg = parseFloat(((auctionLast - prevClose) / prevClose * 100).toFixed(2));
  }
  const dayVol = (timeshare || []).reduce((s, t) => s + (Number(t.volume) || 0), 0);
  const yvol = prevSnap?.yesterday_volume_hands;
  let ratio = null;
  if (yvol && yvol > 0) ratio = Math.round((dayVol / yvol) * 1000) / 10;

  let totalAskVolumeHands = prevSnap?.total_ask_volume_hands ?? null;
  const asks = orderBook?.asks || [];
  if (asks.length) {
    const shareSum = asks.reduce((s, a) => s + (Number(a.volume) || 0), 0);
    if (shareSum > 0) totalAskVolumeHands = Math.round((shareSum / 100) * 100) / 100;
  }

  const sealWan = Number(limitUpData?.seal_amount || 0);
  const turnover = Number(stockInfo?.turnover || 0);
  let sealToTurnoverPercent = prevSnap?.seal_to_turnover_percent ?? null;
  if (sealWan > 0 && turnover > 0) {
    sealToTurnoverPercent = Math.round((sealWan * 10000 / turnover) * 10000) / 100;
  }

  return {
    ...prevSnap,
    auction_last_price: auctionLast,
    auction_change_percent: auctionChg,
    auction_volume_hands: auctionVol,
    auction_amount: Math.round(auctionAmt * 100) / 100, // 元
    auction_from_open_fallback: auctionFromOpenFallback,
    today_volume_hands: dayVol,
    volume_vs_yesterday_percent: ratio,
    total_ask_volume_hands: totalAskVolumeHands ?? prevSnap?.total_ask_volume_hands,
    seal_to_turnover_percent: sealToTurnoverPercent,
  };
};

/**
 * 模拟回放时按时间截断 L2 看板数据（纯前端，不发额外请求）
 *
 * @param {object} fullData  完整的 /api/v1/l2_dashboard 响应
 * @param {string} cutoffTime  截止时间 'HH:MM'，只保留 <= 该时间的数据
 * @returns {object|null}  与 fullData 格式相同的切片数据，失败返回 null
 */
export const sliceL2DataByTime = (fullData, cutoffTime) => {
  if (!fullData?.success || !fullData?.data) return null;
  const d = fullData.data;
  const cutoff = String(cutoffTime || '').slice(0, 5);
  const timeKey = (t) => String(t || '').slice(0, 5);

  // 分时截断
  const timeshare = (d.timeshare || []).filter(t => timeKey(t.time) <= cutoff);

  // 大单截断
  const large_orders = (d.large_orders || []).filter(o => timeKey(o.time) <= cutoff);

  // 重建 big_map（与后端 _build_big_map 格式保持一致：direction → type）
  const big_map = {};
  large_orders.forEach(order => {
    const k = timeKey(order.time);
    if (!big_map[k]) big_map[k] = [];
    big_map[k].push({
      type: order.direction,      // StockChart isBuyOrder 检查 item.type
      time: order.time,
      price: order.price,
      volume: order.volume_lots,
      amount: order.amount,       // 万元
    });
  });

  // 重建 statistics（amount 单位：万元）
  const calcLevel = (orders, minWan, maxWan = null) => {
    const f = orders.filter(o => {
      const a = o.amount || 0;
      return a >= minWan && (maxWan === null || a < maxWan);
    });
    const buy = f.filter(o => ['被买', '主买'].includes(o.direction));
    const sell = f.filter(o => ['被卖', '主卖'].includes(o.direction));
    return {
      buy_count: buy.length,
      sell_count: sell.length,
      neutral_count: f.length - buy.length - sell.length,
      buy_amount: buy.reduce((s, o) => s + (o.amount || 0), 0),
      sell_amount: sell.reduce((s, o) => s + (o.amount || 0), 0),
      neutral_amount: 0,
    };
  };

  const statistics = {
    above_300: calcLevel(large_orders, 300),
    above_100: calcLevel(large_orders, 100),
    above_50:  calcLevel(large_orders, 50),
    above_30:  calcLevel(large_orders, 30),
    below_30:  calcLevel(large_orders, 0, 30),
  };

  const lastTs = timeshare[timeshare.length - 1];
  const currentPrice = lastTs?.price ?? d.stock_info?.price;
  const prevClose = d.stock_info?.yesterday_close;
  const changePct = (prevClose && currentPrice)
    ? parseFloat(((currentPrice - prevClose) / prevClose * 100).toFixed(2))
    : d.stock_info?.change_percent;
  const stock_info = {
    ...(d.stock_info || {}),
    price: currentPrice,
    change_percent: changePct,
  };

  const session_snapshot = recomputeSessionSnapshot(
    timeshare,
    stock_info,
    d.session_snapshot || {},
    d.order_book || null,
    d.limit_up_monitor || null,
  );

  return {
    ...fullData,
    data: {
      ...d,
      timeshare,
      large_orders,
      big_map,
      statistics,
      stock_info,
      session_snapshot,
    },
  };
};
