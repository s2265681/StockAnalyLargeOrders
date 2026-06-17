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
  pickMatchedStockBasic,
  resolvePrevClosePrice,
} from './StockChart';
import { isPrevCloseConsistentWithFenshi } from '../utils/l2Analysis';

describe('StockChart helpers', () => {
  test('resolves prev close from base info or stock basic data', () => {
    expect(resolvePrevClosePrice({}, { yesterday_close: 35.98 })).toBe(35.98);
    expect(resolvePrevClosePrice({ prevClosePrice: 38.45, code: '000001' }, { yesterday_close: 35.98, code: '000002' })).toBe(38.45);
    expect(resolvePrevClosePrice({ code: '000001' }, { yesterday_close: 35.98, code: '000002' })).toBeNull();
    expect(resolvePrevClosePrice({ code: '000001' }, { yesterday_close: 35.98, code: '000001' })).toBe(35.98);
  });

  test('ignores realtime header prev close when fenshi is historical series', () => {
    const fenshi = Array(240).fill(11.02);
    expect(isPrevCloseConsistentWithFenshi(12.14, fenshi)).toBe(false);
    expect(resolvePrevClosePrice(
      { prevClosePrice: 11.03, code: '000001' },
      { yesterday_close: 12.14, code: '000001' },
      fenshi,
    )).toBe(11.03);
  });

  test('keeps backend prev close on limit-up day instead of falling back to first fenshi', () => {
    // 涨停板：昨收 6.37，全天最高/收盘 7.01（+10%），首个分时价 6.57。
    // 一致性校验因 >5% 振幅判 false，但绝不能回退到首分时价 6.57，
    // 否则分时图基准错位，涨停被画成 +6.7% 而非 +10%。
    const fenshi = [6.57, 6.62, 5.9, 6.8, 7.01];
    expect(isPrevCloseConsistentWithFenshi(6.37, fenshi)).toBe(false);
    expect(resolvePrevClosePrice(
      { prevClosePrice: 6.37, code: '600578' },
      { yesterday_close: 6.37, code: '600578' },
      fenshi,
    )).toBe(6.37);
  });

  test('prefers header prev close when fenshi prices are stale vs current quote', () => {
    const fenshi = Array(120).fill(39.44);
    expect(resolvePrevClosePrice(
      { prevClosePrice: 39.44, code: '002741' },
      { yesterday_close: 49.39, current_price: 48.17, code: '002741' },
      fenshi,
    )).toBe(49.39);
  });

  test('ignores stale stockBasic limits when code does not match', () => {
    const bounds = getLimitPercentBounds({
      stockBasicData: {
        code: '300001',
        limit_up: 15,
        limit_down: 10,
        yesterday_close: 12,
      },
      baseInfo: {
        code: '000001',
        prevClosePrice: 10,
      },
      fallbackPercents: [-2, 1.5],
    });

    expect(bounds.min).toBeGreaterThanOrEqual(-5);
    expect(bounds.max).toBeLessThanOrEqual(5);
    expect(Math.abs(bounds.max)).toBe(Math.abs(bounds.min));
    expect(pickMatchedStockBasic({ code: '000001' }, { code: '000002' })).toBeNull();
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
