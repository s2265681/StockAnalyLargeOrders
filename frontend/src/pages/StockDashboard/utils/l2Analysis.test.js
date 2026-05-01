import { alignTimeshareToTradingAxis, buildAnalysisCards, getFlowTone } from './l2Analysis';

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
});
