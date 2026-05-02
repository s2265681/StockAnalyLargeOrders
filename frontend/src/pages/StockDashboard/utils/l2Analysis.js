export const getFlowTone = (value) => {
  if (value > 0) return 'positive';
  if (value < 0) return 'negative';
  return 'neutral';
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

  return {
    axis,
    fenshi: axis.map(time => byTime.get(time)?.price ?? null),
    volume: axis.map(time => byTime.get(time)?.volume ?? 0),
  };
};

const sumOrderAmount = (orders, type) => orders
  .filter(order => order.type === type)
  .reduce((sum, order) => sum + Number(order.amount || 0), 0);

const getValidPrices = (timeshareData = {}) => ((timeshareData || {}).fenshi || [])
  .filter(price => price !== null && price !== undefined && !Number.isNaN(Number(price)))
  .map(Number);

export const buildHandicapLanguage = ({ timeshareData = {}, largeOrdersData = {} } = {}) => {
  const prices = getValidPrices(timeshareData);
  const orders = (largeOrdersData || {}).largeOrders || [];
  const orderBook = (timeshareData || {}).order_book || {};

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
  const buyAmount = sumOrderAmount(orders, 'buy');
  const sellAmount = sumOrderAmount(orders, 'sell');
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
  const tags = [];
  const reasons = [];

  let primaryLabel = '夹单震荡';
  let tone = 'neutral';
  let score = 50;
  let advice = '买卖力量接近，先观察是否放量突破均线或跌破开盘价。';

  if (bookAvailable && askAmount > bidAmount * 1.8) {
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
  } else if (sellAmount > buyAmount * 1.3 && (!aboveOpen || !aboveAvg)) {
    primaryLabel = '压单明显';
    tone = 'negative';
    score = 35;
    tags.push('压单', '转弱');
    reasons.push('卖出大单金额明显高于买入大单');
    reasons.push(currentPrice < openPrice ? '价格运行在开盘价下方' : '价格未能稳定站上均线');
    advice = '先谨慎，等重新站回均线或开盘价后再看承接，跌破开盘价且卖单放大时避免追高。';
  } else if (buyAmount > sellAmount * 1.3 && aboveAvg) {
    primaryLabel = aboveOpen ? '均线上承接' : '托单修复';
    tone = 'positive';
    score = 68;
    tags.push('堆单', '承接');
    reasons.push('买入大单金额明显高于卖出大单');
    reasons.push(aboveOpen ? '价格保持在开盘价上方' : '价格回到均线附近并有承接');
    advice = '偏强观察，可等回踩均线或开盘价不破时看承接，放量上穿前高再确认主动性。';
  } else if (buyRatio > 0.58 && rising) {
    primaryLabel = '扫单进攻';
    tone = 'positive';
    score = 74;
    tags.push('扫单', '主动买');
    reasons.push('买方大单占优，最近价格重心抬升');
    advice = '进攻信号较强，避免急追，优先等回踩均线不破或突破后缩量回踩确认。';
  } else if (Math.abs(buyRatio - 0.5) < 0.12 && rangePercent < 1.2 && orders.length >= 6) {
    primaryLabel = '夹单震荡';
    tone = 'neutral';
    score = 52;
    tags.push('夹单', '等方向');
    reasons.push('买卖大单接近，价格波动区间收窄');
    advice = '方向未选出，等放量突破区间上沿或跌破开盘价后再判断。';
  } else if (!aboveOpen && sellAmount >= buyAmount) {
    primaryLabel = '跌破开盘价';
    tone = 'negative';
    score = 40;
    tags.push('开盘价失守', '谨慎');
    reasons.push('价格低于开盘价，卖方力量不弱');
    advice = '等跌破开盘价后的承接是否出现，重新站回均线前以观察为主。';
  } else {
    tags.push('观察');
    reasons.push('当前买卖力量没有形成明显单边盘口语言');
  }

  if (totalAmount > 0) {
    reasons.push(`买卖大单占比约 ${Math.round(buyRatio * 100)}% / ${Math.round((1 - buyRatio) * 100)}%`);
  }

  if (!bookAvailable) {
    reasons.push('五档盘口暂不可用，当前按分时位置和大单方向降级判断');
  }

  return {
    primaryLabel,
    tone,
    score,
    tags,
    reasons: reasons.slice(0, 3),
    advice,
    metrics: {
      currentPrice,
      changePercent,
      openPrice,
      avgPrice: Number(avgPrice.toFixed(2)),
      buyAmount,
      sellAmount,
      buyRatio,
      bookAvailable,
      bidAmount,
      askAmount,
      bookBidRatio,
      spread: Number(orderBook.spread || 0),
    },
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

  return {
    ...fullData,
    data: {
      ...d,
      timeshare,
      large_orders,
      big_map,
      statistics,
      // 模拟回放：用截止时刻的最后一条分时价格更新股票基础信息
      stock_info: (() => {
        const lastTs = timeshare[timeshare.length - 1];
        const currentPrice = lastTs?.price ?? d.stock_info?.price;
        const prevClose = d.stock_info?.yesterday_close;
        const changePct = (prevClose && currentPrice)
          ? parseFloat(((currentPrice - prevClose) / prevClose * 100).toFixed(2))
          : d.stock_info?.change_percent;
        return {
          ...(d.stock_info || {}),
          price: currentPrice,
          change_percent: changePct,
        };
      })(),
    },
  };
};
