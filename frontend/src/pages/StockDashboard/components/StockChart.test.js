jest.mock('echarts-for-react/lib/core', () => () => null);
jest.mock('echarts/core', () => ({ use: jest.fn() }));
jest.mock('echarts/charts', () => ({
  PieChart: {},
  LineChart: {},
  BarChart: {},
}));
jest.mock('echarts/components', () => ({
  TitleComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  GridComponent: {},
  DataZoomComponent: {},
  AxisPointerComponent: {},
  MarkPointComponent: {},
  MarkLineComponent: {},
  ToolboxComponent: {},
  GraphicComponent: {},
}));
jest.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

import {
  formatPercentLabel,
  formatTradingTimeLabel,
  getPercentAxisInterval,
  getZeroLineLabel,
  getLimitPercentBounds,
  resolvePrevClosePrice,
} from './StockChart';

describe('StockChart helpers', () => {
  test('resolves prev close from base info or stock basic data', () => {
    expect(resolvePrevClosePrice({}, { yesterday_close: 35.98 })).toBe(35.98);
    expect(resolvePrevClosePrice({ prevClosePrice: 38.45 }, { yesterday_close: 35.98 })).toBe(38.45);
    expect(resolvePrevClosePrice({}, {})).toBeNull();
  });

  test('uses stock limit prices as y-axis percent bounds', () => {
    const bounds = getLimitPercentBounds({
      stockBasicData: {
        limit_up: 7.01,
        limit_down: 5.73,
      },
      baseInfo: {
        prevClosePrice: 6.37,
      },
      fallbackPercents: [-3.2, 10.05],
    });

    expect(bounds.min).toBeCloseTo(-10.05, 2);
    expect(bounds.max).toBeCloseTo(10.05, 2);
  });

  test('zooms in small fluctuations instead of forcing full limit bounds', () => {
    const bounds = getLimitPercentBounds({
      stockBasicData: {
        limit_up: 12.16,
        limit_down: 9.95,
      },
      baseInfo: {
        prevClosePrice: 11.05,
      },
      fallbackPercents: [-0.82, 0.48],
    });

    expect(bounds.min).toBe(-1);
    expect(bounds.max).toBe(1);
  });

  test('falls back to the nearest common limit when limit prices are unavailable', () => {
    const bounds = getLimitPercentBounds({
      stockBasicData: {},
      baseInfo: {
        prevClosePrice: 10,
      },
      fallbackPercents: [-1.2, 19.9],
    });

    expect(bounds.min).toBe(-20);
    expect(bounds.max).toBe(20);
  });

  test('keeps ordinary 10 percent limit-up stocks at ten percent when price rounds slightly above', () => {
    const bounds = getLimitPercentBounds({
      stockBasicData: {},
      baseInfo: {
        prevClosePrice: 38.45,
      },
      fallbackPercents: [10.013003901170353, 6.87, -0.4],
    });

    expect(bounds.min).toBe(-10);
    expect(bounds.max).toBe(10);
  });

  test('merges the lunch break labels to avoid overlap', () => {
    expect(formatTradingTimeLabel('11:30')).toBe('11:30/13:00');
    expect(formatTradingTimeLabel('13:00')).toBe('');
  });

  test('formats percentage labels without redundant decimals', () => {
    expect(formatPercentLabel(10)).toBe('+10%');
    expect(formatPercentLabel(10.047095761381477)).toBe('+10.05%');
    expect(formatPercentLabel(-9.999999)).toBe('-10%');
  });

  test('uses equal percent intervals between limit bounds', () => {
    expect(getPercentAxisInterval({ min: -10, max: 10 })).toBe(5);
    expect(getPercentAxisInterval({ min: -20, max: 20 })).toBe(10);
  });

  test('hides the zero mark line label because the y-axis already labels zero', () => {
    expect(getZeroLineLabel()).toEqual({ show: false });
  });
});
