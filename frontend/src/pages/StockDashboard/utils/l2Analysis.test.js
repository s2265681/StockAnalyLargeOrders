import {
  alignTimeshareToTradingAxis,
  buildAnalysisCards,
  buildHandicapLanguage,
  getFlowTone,
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
