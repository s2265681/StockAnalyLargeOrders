import {
  alignTimeshareToTradingAxis,
  buildAnalysisCards,
  buildHandicapLanguage,
  buildTimeshareBaseInfo,
  getFlowTone,
  isPrevCloseConsistentWithFenshi,
  isSameStockCode,
} from './l2Analysis';

describe('l2Analysis helpers', () => {
  test('builds display cards from backend large-order analysis', () => {
    const cards = buildAnalysisCards({
      total_large_orders: 12,
      total_amount: 1888.5,
      net_inflow: -320.25,
      buy_ratio: 41.2,
      pressure_score: -16.96,
    });

    expect(cards).toEqual([
      { key: 'orders', label: '大单笔数', value: '12', suffix: '笔', tone: 'neutral' },
      { key: 'amount', label: '大单金额', value: '1888.50', suffix: '万', tone: 'neutral' },
      { key: 'net', label: '净流入', value: '-320.25', suffix: '万', tone: 'negative' },
      { key: 'ratio', label: '买入占比', value: '41.2', suffix: '%', tone: 'negative' },
      { key: 'score', label: '压力强度', value: '-16.96', suffix: '%', tone: 'negative' },
    ]);
  });

  test('classifies flow tone around zero', () => {
    expect(getFlowTone(1)).toBe('positive');
    expect(getFlowTone(-1)).toBe('negative');
    expect(getFlowTone(0)).toBe('neutral');
  });

  test('compares stock codes as strings', () => {
    expect(isSameStockCode('000001', '000001')).toBe(true);
    expect(isSameStockCode(1, '000001')).toBe(false);
    expect(isSameStockCode('000001', '000002')).toBe(false);
    expect(isSameStockCode(null, '000001')).toBe(false);
  });

  test('detects prev close mismatch against fenshi prices', () => {
    expect(isPrevCloseConsistentWithFenshi(11.03, [11.02, 11.01, 10.99])).toBe(true);
    expect(isPrevCloseConsistentWithFenshi(12.14, [11.02, 11.01, 10.99])).toBe(false);
  });

  test('builds timeshare base_info from stock_info', () => {
    expect(buildTimeshareBaseInfo({
      code: '600519',
      yesterday_close: 1680,
      pre_close: 1670,
      open: 1690,
      high: 1700,
      low: 1675,
      limit_up: 1848,
      limit_down: 1512,
    }, '600519')).toEqual({
      code: '600519',
      prevClosePrice: 1680,
      openPrice: 1690,
      highPrice: 1700,
      lowPrice: 1675,
      limit_up: 1848,
      limit_down: 1512,
    });
  });

  test('aligns historical timeshare by real minute instead of array index', () => {
    const aligned = alignTimeshareToTradingAxis([
      { time: '09:31', price: 11.56, volume: 100 },
      { time: '09:32', price: 11.58, volume: 200 },
    ]);

    expect(aligned.axis[0]).toBe('09:30');
    expect(aligned.fenshi[0]).toBeNull();
    expect(aligned.fenshi[1]).toBe(11.56);
    expect(aligned.volume[1]).toBe(100);
  });

  test('falls back to avg_price when price field is missing', () => {
    const aligned = alignTimeshareToTradingAxis([
      { time: '09:31', avg_price: 12.15, volume: 100 },
    ]);

    expect(aligned.fenshi[1]).toBe(12.15);
  });

  test('returns waiting state before timeshare data is loaded', () => {
    const signal = buildHandicapLanguage({
      timeshareData: null,
      largeOrdersData: null,
    });

    expect(signal.primaryLabel).toBe('等待数据');
    expect(signal.tone).toBe('neutral');
  });

  test('detects pressure when sell orders dominate below open price', () => {
    const signal = buildHandicapLanguage({
      timeshareData: {
        fenshi: [10, 9.95, 9.9, 9.86],
        base_info: { prevClosePrice: 10, openPrice: 10 },
      },
      largeOrdersData: {
        largeOrders: [
          { type: 'sell', amount: 2_000_000 },
          { type: 'sell', amount: 1_200_000 },
          { type: 'buy', amount: 500_000 },
        ],
      },
    });

    expect(signal.primaryLabel).toBe('压单明显');
    expect(signal.tone).toBe('negative');
    expect(signal.advice).toContain('等重新站回均线');
  });

  test('detects support when buy orders dominate above average line', () => {
    const signal = buildHandicapLanguage({
      timeshareData: {
        fenshi: [10, 10.05, 10.08, 10.1],
        base_info: { prevClosePrice: 10, openPrice: 10 },
      },
      largeOrdersData: {
        largeOrders: [
          { type: 'buy', amount: 2_000_000 },
          { type: 'buy', amount: 1_500_000 },
          { type: 'sell', amount: 500_000 },
        ],
      },
    });

    expect(signal.primaryLabel).toBe('均线上承接');
    expect(signal.tone).toBe('positive');
    expect(signal.advice).toContain('回踩均线');
  });

  test('uses five-level order book to identify upper pressure', () => {
    const signal = buildHandicapLanguage({
      timeshareData: {
        fenshi: [10, 10.02, 10.01],
        base_info: { prevClosePrice: 10, openPrice: 10 },
        order_book: {
          bid_amount: 1_000_000,
          ask_amount: 3_500_000,
          spread: 0.03,
          bids: [{ level: 1, price: 10.0, amount: 400_000 }],
          asks: [{ level: 1, price: 10.03, amount: 1_800_000 }],
        },
      },
      largeOrdersData: { largeOrders: [] },
    });

    expect(signal.tags).toContain('五档压单');
    expect(signal.reasons.join('')).toContain('五档卖盘');
  });

  test('detects limit-down crash even when buy orders dominate', () => {
    // 模拟002210场景：跌停但大单买入远多于卖出（被动成交）
    const prices = [];
    const startPrice = 3.36;
    const endPrice = 2.98; // ~-11% 跌停
    for (let i = 0; i < 30; i++) {
      prices.push(startPrice - (startPrice - endPrice) * (i / 29));
    }
    const signal = buildHandicapLanguage({
      timeshareData: {
        fenshi: prices,
        base_info: { prevClosePrice: 3.31, openPrice: 3.36 },
      },
      largeOrdersData: {
        largeOrders: [
          { type: 'buy', direction: '被买', amount: 270508_0000 },
          { type: 'buy', direction: '主买', amount: 5000_0000 },
          { type: 'sell', direction: '主卖', amount: 33005_0000 },
        ],
      },
    });

    expect(signal.tone).toBe('negative');
    expect(signal.score).toBeLessThan(25);
  });

  test('detects strong drop with passive buy orders as weak', () => {
    const prices = [10, 9.8, 9.6, 9.5, 9.4, 9.3, 9.2, 9.15, 9.1, 9.05];
    const signal = buildHandicapLanguage({
      timeshareData: {
        fenshi: prices,
        base_info: { prevClosePrice: 10, openPrice: 10 },
      },
      largeOrdersData: {
        largeOrders: [
          { type: 'buy', direction: '被买', amount: 5_000_000 },
          { type: 'sell', direction: '主卖', amount: 1_000_000 },
        ],
      },
    });

    expect(signal.tone).toBe('negative');
    expect(signal.score).toBeLessThan(30);
  });

  test('uses five-level order book to identify lower support', () => {
    const signal = buildHandicapLanguage({
      timeshareData: {
        fenshi: [10, 10.02, 10.04],
        base_info: { prevClosePrice: 10, openPrice: 10 },
        order_book: {
          bid_amount: 4_000_000,
          ask_amount: 1_000_000,
          spread: 0.01,
          bids: [{ level: 1, price: 10.03, amount: 2_000_000 }],
          asks: [{ level: 1, price: 10.04, amount: 500_000 }],
        },
      },
      largeOrdersData: { largeOrders: [] },
    });

    expect(signal.tags).toContain('五档托单');
    expect(signal.reasons.join('')).toContain('五档买盘');
  });
});
