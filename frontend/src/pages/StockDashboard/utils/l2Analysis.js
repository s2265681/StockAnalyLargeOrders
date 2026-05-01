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
