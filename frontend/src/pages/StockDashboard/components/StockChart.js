import React, { useMemo, useRef } from 'react';
import { Spin } from 'antd';
import { useAtom } from 'jotai';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { PieChart, LineChart, BarChart } from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  AxisPointerComponent,
  MarkPointComponent,
  MarkLineComponent,
  ToolboxComponent,
  GraphicComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import {
  stockCodeAtom,
  stockBasicDataAtom,
  largeOrdersDataAtom,
  timeshareDataAtom,
  filterAmountAtom,
  timeshareLoadingAtom,
  errorAtom,
} from '../../../store/atoms';
import {
  alignMoneyFlowToTradingAxis,
  buildFlowLineSeriesData,
  isPrevCloseConsistentWithFenshi,
} from '../utils/l2Analysis';

// 注册ECharts组件
echarts.use([
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  AxisPointerComponent,
  MarkPointComponent,
  MarkLineComponent,
  ToolboxComponent,
  GraphicComponent,
  PieChart,
  LineChart,
  BarChart,
  CanvasRenderer
]);

export const formatPercentLabel = (value) => {
  const roundedValue = Math.round(Number(value || 0) * 100) / 100;
  if (Object.is(roundedValue, -0) || Math.abs(roundedValue) < 0.005) {
    return '0%';
  }

  const absText = Math.abs(roundedValue).toFixed(2).replace(/\.?0+$/, '');
  return `${roundedValue > 0 ? '+' : '-'}${absText}%`;
};

export const resolvePrevClosePrice = (baseInfo, stockBasicData, fenshi) => {
  const parsePrice = (raw) => {
    const value = parseFloat(raw);
    return Number.isFinite(value) && value > 0 ? value : null;
  };

  const baseCode = baseInfo?.code;
  const basicMatches = baseCode && stockBasicData?.code
    ? String(stockBasicData.code) === String(baseCode)
    : false;

  const fromTimeshare = parsePrice(baseInfo?.prevClosePrice) ?? parsePrice(baseInfo?.prev_close);
  const fromBasic = (!baseCode || basicMatches)
    ? (parsePrice(stockBasicData?.yesterday_close)
      ?? parsePrice(stockBasicData?.pre_close)
      ?? parsePrice(stockBasicData?.preClose))
    : null;

  const hasFenshi = (fenshi || []).some((p) => p != null && p !== '');

  // 有分时序列时，昨收必须与价格同量级，禁止用 header 实时昨收去算历史分时
  if (hasFenshi) {
    if (fromTimeshare && isPrevCloseConsistentWithFenshi(fromTimeshare, fenshi)) {
      return fromTimeshare;
    }
    if (fromBasic && isPrevCloseConsistentWithFenshi(fromBasic, fenshi)) {
      return fromBasic;
    }
    // 一致性校验对涨跌停（振幅>5%）必然判 false，此时仍应优先用后端同源昨收，
    // 首个分时价只是当日首分钟成交价，绝不能当昨收（否则涨停被画成 0% 基准错位）。
    const prices = (fenshi || [])
      .map((p) => parseFloat(p))
      .filter((p) => Number.isFinite(p) && p > 0);
    return fromTimeshare ?? fromBasic ?? (prices.length ? prices[0] : null);
  }

  if (fromTimeshare) {
    return fromTimeshare;
  }

  if (!baseCode || basicMatches) {
    return fromBasic;
  }

  return null;
};

export const pickMatchedStockBasic = (baseInfo, stockBasicData) => {
  if (!stockBasicData) {
    return null;
  }
  const baseCode = baseInfo?.code;
  if (!baseCode || !stockBasicData.code) {
    return stockBasicData;
  }
  return String(stockBasicData.code) === String(baseCode) ? stockBasicData : null;
};

export const formatTradingTimeLabel = (value) => {
  if (!value || typeof value !== 'string') {
    return '';
  }

  if (value === '11:30') {
    return '11:30/13:00';
  }
  if (value === '13:00') {
    return '';
  }

  const targetTimes = ['09:30', '10:30', '11:30', '14:00', '15:00'];
  return targetTimes.includes(value) ? value : '';
};

export const getLimitPercentBounds = ({ stockBasicData, baseInfo, fallbackPercents = [] }) => {
  const matchedBasic = pickMatchedStockBasic(baseInfo, stockBasicData);
  const prevClosePrice = resolvePrevClosePrice(baseInfo, stockBasicData);
  const limitUpPrice = parseFloat(matchedBasic?.limit_up ?? baseInfo?.limit_up);
  const limitDownPrice = parseFloat(matchedBasic?.limit_down ?? baseInfo?.limit_down);
  const validPercents = fallbackPercents
    .map(Number)
    .filter(Number.isFinite);
  const maxAbsFallback = validPercents.reduce((max, value) => Math.max(max, Math.abs(value)), 0);

  const getAdaptiveBounds = (maxLimit = 30) => {
    const paddedMax = maxAbsFallback >= 5
      ? maxAbsFallback
      : Math.max(maxAbsFallback * 1.2, 0.2);
    const niceBounds = [0.5, 1, 1.5, 2, 3, 5, 7.5, 10, 20, 30];
    const bound = niceBounds.find((candidate) => paddedMax <= candidate + 0.2) || Math.min(maxLimit, 30);
    const clampedBound = Math.min(bound, maxLimit);
    return { min: -clampedBound, max: clampedBound };
  };

  if (Number.isFinite(prevClosePrice) && prevClosePrice > 0) {
    const upper = Number.isFinite(limitUpPrice)
      ? ((limitUpPrice - prevClosePrice) / prevClosePrice) * 100
      : null;
    const lower = Number.isFinite(limitDownPrice)
      ? ((limitDownPrice - prevClosePrice) / prevClosePrice) * 100
      : null;

    if (Number.isFinite(upper) && Number.isFinite(lower) && upper > lower) {
      const maxLimit = Math.max(Math.abs(upper), Math.abs(lower));
      const nearLimit = validPercents.some((value) => value >= upper - 0.35 || value <= lower + 0.35);
      if (!nearLimit && maxAbsFallback > 0 && maxAbsFallback < maxLimit * 0.55) {
        return getAdaptiveBounds(maxLimit);
      }
      return { min: lower, max: upper };
    }

    const oneSidedLimit = Math.max(Math.abs(upper || 0), Math.abs(lower || 0));
    if (oneSidedLimit > 0) {
      if (maxAbsFallback > 0 && maxAbsFallback < oneSidedLimit * 0.55) {
        return getAdaptiveBounds(oneSidedLimit);
      }
      return { min: -oneSidedLimit, max: oneSidedLimit };
    }
  }

  return getAdaptiveBounds();
};

export const getPercentAxisInterval = ({ min, max, sections = 4 }) => {
  const span = Number(max) - Number(min);
  if (!Number.isFinite(span) || span <= 0 || sections <= 0) {
    return undefined;
  }
  return span / sections;
};

export const getZeroLineLabel = () => ({ show: false });

const isBigMapBuyOrder = (item) => {
  const rawType = item.type ?? item.t ?? item.direction;
  const type = Number.isNaN(parseInt(rawType, 10)) ? rawType : parseInt(rawType, 10);
  return type === 1 || type === 2 || type === '主买' || type === '被买';
};

const isBigMapSellOrder = (item) => {
  const rawType = item.type ?? item.t ?? item.direction;
  const type = Number.isNaN(parseInt(rawType, 10)) ? rawType : parseInt(rawType, 10);
  return type === 3 || type === 4 || type === '主卖' || type === '被卖';
};

const StockChart = () => {
  const [stockCode] = useAtom(stockCodeAtom);
  const [stockBasicData] = useAtom(stockBasicDataAtom);
  const [largeOrdersData] = useAtom(largeOrdersDataAtom);
  const [timeshareData] = useAtom(timeshareDataAtom);
  const [filterAmount] = useAtom(filterAmountAtom);
  const [error] = useAtom(errorAtom);
  const [timeshareLoading] = useAtom(timeshareLoadingAtom);
  const chartRef = useRef(null);

  // 添加筛选阈值状态，默认300
  const [filterThreshold] = React.useState(300);

  // 获取当前主题的CSS变量颜色（ECharts canvas不支持var()）
  const getThemeColor = (varName, fallback) => {
    return getComputedStyle(document.documentElement).getPropertyValue(varName).trim() || fallback;
  };
  const textColor = getThemeColor('--text-primary', '#fff');
  const textMuted = getThemeColor('--text-muted', '#999');
  const borderColor = getThemeColor('--border-primary', '#333');
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';

  const hasTimesharePoints = useMemo(() => (
    (timeshareData?.fenshi || []).some((price) => price != null && price !== '')
  ), [timeshareData]);

  // 生成筛选金额标注点（使用百分比坐标）
  const generateFilteredAmountMarkers = (fenshiData, largeOrders, filterAmount, yesterdayClose) => {
    if (!fenshiData || !largeOrders || largeOrders.length === 0 || !filterAmount) {
      return { institutionalMarkers: [], retailMarkers: [] };
    }

    const institutionalMarkers = [];
    const retailMarkers = [];
    
    const filteredOrders = largeOrders.filter(order => order.amount >= filterAmount);
    
    filteredOrders.forEach(order => {
      // 找到对应时间点的价格数据
      const timeIndex = parseInt(order.time.split(' ')[1]?.substring(0, 5).replace(':', '')) || 0;
      const priceIndex = Math.floor(timeIndex / 100) * 60 + (timeIndex % 100);
      
      if (fenshiData[priceIndex]) {
        const price = parseFloat(fenshiData[priceIndex]);
        const percentChange = ((price - yesterdayClose) / yesterdayClose) * 100;
        
        const markerData = {
          name: `${order.type === 'buy' ? '买入' : '卖出'}${(order.amount / 10000).toFixed(1)}万`,
          coord: [order.time, percentChange],
          value: `${(order.amount / 10000).toFixed(1)}万`,
          symbol: 'circle',
          symbolSize: Math.min(Math.max((order.amount / filterAmount) * 6, 6), 20),
          itemStyle: {
            color: order.type === 'buy' ? '#ff4d4f' : '#52c41a',
            borderColor: isDark ? '#fff' : '#1a1a1a',
            borderWidth: 2
          },
          label: {
            show: true,
            position: order.type === 'buy' ? 'top' : 'bottom',
            color: order.type === 'buy' ? '#ff4d4f' : '#52c41a',
            fontSize: 9,
            fontWeight: 'bold'
          }
        };

        if (order.amount >= 1000000) {
          institutionalMarkers.push(markerData);
        } else {
          retailMarkers.push(markerData);
        }
      }
    });

    return { institutionalMarkers, retailMarkers };
  };

  // 分时图配置
  const getTimeshareChartOption = () => {
    if (!timeshareData) {
      return {};
    }
    
    const { base_info, fenshi, sanhu, volume, zhuli, timeAxis } = timeshareData;
    const prevClosePrice = resolvePrevClosePrice(base_info, stockBasicData, fenshi);
    if (!prevClosePrice) {
      return {};
    }

    const lastFenshiIndex = (fenshi || []).reduce(
      (lastIndex, price, index) => (price != null && price !== '' ? index : lastIndex),
      -1
    );
    
    // 根据数据长度生成时间轴
    const dataLength = Math.max(
      fenshi?.length || 0,
      sanhu?.length || 0,
      volume?.length || 0,
      zhuli?.length || 0
    );
    
    // 生成对应长度的时间轴
    const generateTimeAxisByLength = (length) => {
      const timePoints = [];
      let currentHour = 9;
      let currentMinute = 30;
      
      for (let i = 0; i < length; i++) {
        const timeStr = `${currentHour.toString().padStart(2, '0')}:${currentMinute.toString().padStart(2, '0')}`;
        timePoints.push(timeStr);
        
        currentMinute++;
        if (currentMinute >= 60) {
          currentMinute = 0;
          currentHour++;
        }
        
        // 跳过午休时间 11:30-13:00
        if (currentHour === 11 && currentMinute === 31) {
          currentHour = 13;
          currentMinute = 0;
        }
        
        // 结束时间 15:00
        if (currentHour === 15 && currentMinute === 1) {
          break;
        }
      }
      
      // 确保包含15:00
      if (!timePoints.includes('15:00')) {
        timePoints.push('15:00');
      }
      
      return timePoints;
    };
    
    const fullTimeAxis = timeAxis?.length ? timeAxis : generateTimeAxisByLength(dataLength);
    
    // 生成big_map数据标注点
    const generateBigMapMarkers = (bigMapData, institutionalData, retailData, fullTimeAxis, filterThreshold = 300, yAxisMin = -10, yAxisMax = 10) => {
      if (!bigMapData) {
        return { institutionalMarkers: [], retailMarkers: [] };
      }

      const institutionalMarkers = [];
      const isBuyOrder = isBigMapBuyOrder;
      const isSellOrder = isBigMapSellOrder;
      const buildMarker = (timeStr, item, stackIndex, side) => {
        const value = parseFloat(item.amount ?? item.v);
        const isBuy = side === 'buy';
        const color = isBuy ? '#ff4d4f' : '#52c41a';
        const timeIndex = fullTimeAxis.indexOf(timeStr);
        if (timeIndex === -1) return null;

        const basePrice = item.price || fenshi[timeIndex];
        if (!basePrice || !prevClosePrice) return null;

        const baseY = ((parseFloat(basePrice) - prevClosePrice) / prevClosePrice) * 100;
        const stackStep = Math.max((yAxisMax - yAxisMin) * 0.045, 0.28);
        const maxRowsPerColumn = 6;
        const rowIndex = stackIndex % maxRowsPerColumn;
        const columnIndex = Math.floor(stackIndex / maxRowsPerColumn);
        const horizontalOffset = (isBuy ? -12 : 12) + (isBuy ? -1 : 1) * columnIndex * 18;
        const neededSpace = (rowIndex + 1) * stackStep + 0.3;
        const spaceAbove = yAxisMax - baseY;
        const spaceBelow = baseY - yAxisMin;
        const direction = isBuy
          ? (spaceAbove >= neededSpace ? 1 : -1)
          : (spaceBelow >= neededSpace ? -1 : 1);
        const stackedY = Math.max(
          yAxisMin + 0.15,
          Math.min(yAxisMax - 0.15, baseY + direction * (rowIndex + 1) * stackStep)
        );

        return {
          name: Math.round(value).toString(),
          coord: [timeStr, stackedY],
          symbol: 'circle',
          symbolSize: 1,
          symbolOffset: [horizontalOffset, 0],
          itemStyle: {
            color: 'transparent',
            borderColor: 'transparent',
            borderWidth: 0
          },
          label: {
            show: true,
            position: 'inside',
            offset: [horizontalOffset, 0],
            color,
            fontSize: 9,
            fontWeight: 'bold',
            lineHeight: 10,
            backgroundColor: 'transparent',
            padding: 0,
            borderRadius: 2
          }
        };
      };

      // 遍历big_map中的每个时间点。同一分钟按买/卖拆成两列，分别上下堆叠。
      Object.keys(bigMapData).forEach(timeStr => {
        const timeData = bigMapData[timeStr];
        if (!Array.isArray(timeData)) return;
        
        // 兼容后端新格式 {type, amount} 和旧格式 {t, v}，金额单位均为万元
        const filteredData = timeData
          .filter(item => parseFloat(item.amount ?? item.v) >= filterThreshold)
          .sort((a, b) => parseFloat(b.amount ?? b.v) - parseFloat(a.amount ?? a.v));

        filteredData.filter(isBuyOrder).forEach((item, stackIndex) => {
          const marker = buildMarker(timeStr, item, stackIndex, 'buy');
          if (marker) institutionalMarkers.push(marker);
        });

        filteredData.filter(isSellOrder).forEach((item, stackIndex) => {
          const marker = buildMarker(timeStr, item, stackIndex, 'sell');
          if (marker) institutionalMarkers.push(marker);
        });
      });

      return { institutionalMarkers, retailMarkers: [] };
    };
    
    // 价格数据（转换为百分比坐标）。缺分钟点时沿用最近有效价格，但不向未到的交易时段延伸。
    let lastPricePct = null;
    const priceData = fenshi.map((price, index) => {
      const timePoint = fullTimeAxis[index];
      if (index > lastFenshiIndex) {
        return [timePoint, null];
      }
      if (timePoint && price) {
        const percentChange = ((parseFloat(price) - prevClosePrice) / prevClosePrice) * 100;
        lastPricePct = percentChange;
        return [timePoint, percentChange];
      }
      return [timePoint, lastPricePct];
    });
    
    // 成交量数据
    const volumeData = volume.map((vol, index) => {
      const timePoint = fullTimeAxis[index];
      if (timePoint && vol) {
        let color = '#808080';
        if (index > 0 && fenshi[index] && fenshi[index - 1]) {
          const currentPrice = parseFloat(fenshi[index]);
          const previousPrice = parseFloat(fenshi[index - 1]);
          color = currentPrice >= previousPrice ? '#ff4d4f' : '#52c41a';
        } else if (fenshi[index]) {
          const currentPrice = parseFloat(fenshi[index]);
          color = currentPrice >= prevClosePrice ? '#ff4d4f' : '#52c41a';
        }
        
        return {
          value: [timePoint, vol],
          itemStyle: { color }
        };
      }
      return {
        value: [timePoint, 0],
        itemStyle: { color: 'transparent' }
      };
    });
    
    // 计算均价线
    const avgPriceData = [];
    let totalAmount = 0;
    let totalVolume = 0;
    
    fenshi.forEach((price, index) => {
      const timePoint = fullTimeAxis[index];
      if (index > lastFenshiIndex) {
        avgPriceData.push([timePoint, null]);
        return;
      }
      if (timePoint && price && volume[index]) {
        const currentPrice = parseFloat(price);
        const currentVolume = volume[index];
        totalAmount += currentPrice * currentVolume;
        totalVolume += currentVolume;
        const avgPrice = totalVolume > 0 ? totalAmount / totalVolume : prevClosePrice;
        const percentChange = ((avgPrice - prevClosePrice) / prevClosePrice) * 100;
        avgPriceData.push([timePoint, percentChange]);
      } else {
        const lastAvgPoint = avgPriceData[avgPriceData.length - 1];
        avgPriceData.push([timePoint, Array.isArray(lastAvgPoint) ? lastAvgPoint[1] : null]);
      }
    });
    
    // Y 轴使用个股真实涨跌停百分比，避免封板走势显示成 +12%/-9.99% 这类伪边界。
    const pricePercents = (fenshi || [])
      .map((p) => (p != null && prevClosePrice
        ? ((parseFloat(p) - prevClosePrice) / prevClosePrice) * 100
        : null))
      .filter((v) => v != null && !Number.isNaN(v));
    const avgPercents = avgPriceData
      .map((pt) => (Array.isArray(pt) ? pt[1] : null))
      .filter((v) => v != null && !Number.isNaN(Number(v)))
      .map(Number);
    const allPct = [...pricePercents, ...avgPercents];
    let { min: yAxisMin, max: yAxisMax } = getLimitPercentBounds({
      stockBasicData,
      baseInfo: base_info,
      fallbackPercents: allPct,
    });
    if (!Number.isFinite(yAxisMax) || !Number.isFinite(yAxisMin) || yAxisMax <= yAxisMin) {
      yAxisMax = 10;
      yAxisMin = -10;
    }
    const yAxisInterval = getPercentAxisInterval({ min: yAxisMin, max: yAxisMax });
    
    // 主力线和散户线 - 基于 big_map 计算累计 VWAP（加权平均成本）
    // 竞品原理：主力线 = 大单（>=阈值）的累计VWAP，散户线 = 小单（<阈值）的累计VWAP
    // 放大偏离：以市场均价为基准，放大主力/散户成本与均价的差异，使趋势更明显
    let largeCumAmount = 0;
    let largeCumValue = 0;
    let smallCumAmount = 0;
    let smallCumValue = 0;
    const deviationAmplify = 3; // 偏离放大倍数

    const institutionalData = [];
    const retailData = [];

    fullTimeAxis.forEach((timePoint, index) => {
      // 只在有分时数据的时间点画线，超出当前时间不填充
      if (!fenshi[index] || fenshi[index] == null) {
        institutionalData.push([timePoint, null]);
        retailData.push([timePoint, null]);
        return;
      }

      const currentPrice = parseFloat(fenshi[index]);
      const orders = timeshareData.big_map?.[timePoint] || [];

      orders.forEach(item => {
        const amount = parseFloat(item.amount ?? item.v);
        const price = parseFloat(item.price) || currentPrice;
        if (!price || !amount || Number.isNaN(amount) || Number.isNaN(price)) return;

        if (amount >= filterThreshold) {
          largeCumAmount += amount;
          largeCumValue += amount * price;
        } else {
          smallCumAmount += amount;
          smallCumValue += amount * price;
        }
      });

      // 当前分钟的市场均价（来自均价线）
      const marketAvgPct = avgPriceData[index] && Array.isArray(avgPriceData[index])
        ? avgPriceData[index][1] : null;

      // 主力线：大单VWAP，放大与均价的偏离
      if (largeCumAmount > 0 && marketAvgPct != null) {
        const vwap = largeCumValue / largeCumAmount;
        const vwapPct = ((vwap - prevClosePrice) / prevClosePrice) * 100;
        const amplified = marketAvgPct + (vwapPct - marketAvgPct) * deviationAmplify;
        institutionalData.push([timePoint, amplified]);
      } else {
        institutionalData.push([timePoint, null]);
      }

      // 散户线：小单VWAP，放大与均价的偏离
      if (smallCumAmount > 0 && marketAvgPct != null) {
        const vwap = smallCumValue / smallCumAmount;
        const vwapPct = ((vwap - prevClosePrice) / prevClosePrice) * 100;
        const amplified = marketAvgPct + (vwapPct - marketAvgPct) * deviationAmplify;
        retailData.push([timePoint, amplified]);
      } else {
        retailData.push([timePoint, null]);
      }
    });

    // 资金博弈线：主力=超大单博弈得分，散户=小单博弈得分；标注用分钟净流入
    const formatFlowAmount = (val) => {
      const amount = Number(val);
      if (Number.isNaN(amount)) return '--';
      const absVal = Math.abs(amount);
      return absVal >= 10000
        ? `${(amount / 10000).toFixed(2)}亿`
        : `${Math.round(amount)}万`;
    };

    let bigFlowData = [];
    let smallFlowData = [];
    let bigFlowMarkers = [];
    const alignedMoneyFlow = alignMoneyFlowToTradingAxis(timeshareData.money_flow);
    let chaodaDeltaArr = [];
    let sanhuDeltaArr = [];
    if (alignedMoneyFlow?.chaoda?.length > 0) {
      const chaodaArr = alignedMoneyFlow.chaoda;
      const xiaoArr = alignedMoneyFlow.sanhu || [];
      chaodaDeltaArr = alignedMoneyFlow.chaoda_delta || [];
      sanhuDeltaArr = alignedMoneyFlow.sanhu_delta || [];

      const bigRaw = chaodaArr.map((value) => parseFloat(value) || 0);
      const smallRaw = xiaoArr.map((value) => parseFloat(value) || 0);
      const maxAbsFlow = Math.max(
        ...bigRaw.map(Math.abs),
        ...smallRaw.map(Math.abs),
        0.01
      );
      const yRange = (yAxisMax - yAxisMin) * 0.3;
      const yMid = (yAxisMax + yAxisMin) / 2;
      const flowLineParams = {
        axis: fullTimeAxis,
        fenshi,
        yMid,
        yRange,
        maxAbsFlow,
      };

      bigFlowData = buildFlowLineSeriesData({
        ...flowLineParams,
        scores: chaodaArr,
        minuteDeltas: chaodaDeltaArr,
      });
      smallFlowData = buildFlowLineSeriesData({
        ...flowLineParams,
        scores: xiaoArr,
        minuteDeltas: sanhuDeltaArr,
      });

      const markerTimes = ['09:30', '10:00', '10:30', '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00'];
      const timeToIndex = {};
      fullTimeAxis.forEach((time, index) => {
        if (time) timeToIndex[time] = index;
      });
      for (const t of markerTimes) {
        const idx = timeToIndex[t];
        if (idx !== undefined && bigFlowData[idx] && bigFlowData[idx][1] !== null) {
          const minuteNet = parseFloat(chaodaDeltaArr[idx]) || 0;
          if (Math.abs(minuteNet) < 1) continue;
          bigFlowMarkers.push({
            coord: bigFlowData[idx],
            name: formatFlowAmount(minuteNet),
            value: formatFlowAmount(minuteNet),
          });
        }
      }
      for (let i = fullTimeAxis.length - 1; i >= 0; i--) {
        if (bigFlowData[i] && bigFlowData[i][1] !== null) {
          const t = fullTimeAxis[i];
          if (!markerTimes.includes(t)) {
            const minuteNet = parseFloat(chaodaDeltaArr[i]) || 0;
            if (Math.abs(minuteNet) >= 1) {
              bigFlowMarkers.push({
                coord: bigFlowData[i],
                name: formatFlowAmount(minuteNet),
                value: formatFlowAmount(minuteNet),
              });
            }
          }
          break;
        }
      }
    }

    // 生成筛选金额标注
    const { institutionalMarkers, retailMarkers } = generateFilteredAmountMarkers(
      fenshi, 
      largeOrdersData?.largeOrders, 
      filterAmount,
      prevClosePrice
    );
    
    // 生成big_map数据标注
    const { institutionalMarkers: bigMapInstitutionalMarkers, retailMarkers: bigMapRetailMarkers } = generateBigMapMarkers(
      timeshareData.big_map,
      institutionalData,
      retailData,
      fullTimeAxis,
      filterThreshold, // 传递筛选阈值
      yAxisMin,
      yAxisMax
    );

    // 大单净量：每分钟大单(买-卖)净额（万元），来自 big_map
    const netFlowData = fullTimeAxis.map((timePoint, index) => {
      if (!fenshi[index] || fenshi[index] == null || index > lastFenshiIndex) {
        return { value: [timePoint, null], itemStyle: { color: 'transparent' } };
      }
      const orders = timeshareData.big_map?.[timePoint] || [];
      let buyAmt = 0;
      let sellAmt = 0;
      orders.forEach(item => {
        const amount = parseFloat(item.amount ?? item.v);
        if (!amount || Number.isNaN(amount)) return;
        if (isBigMapBuyOrder(item)) buyAmt += amount;
        else if (isBigMapSellOrder(item)) sellAmt += amount;
      });
      const net = buyAmt - sellAmt;
      return {
        value: [timePoint, net === 0 && buyAmt === 0 ? null : net],
        itemStyle: { color: net >= 0 ? '#ff4d4f' : '#52c41a' }
      };
    });

    const chartOption = {
      backgroundColor: 'transparent',
      tooltip: {
        show: true,
        trigger: 'axis',
        confine: true,
        axisPointer: {
          type: 'line',
          snap: true,
          lineStyle: {
            color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.35)',
            width: 1,
            type: 'dashed'
          }
        },
        backgroundColor: isDark ? 'rgba(18, 24, 38, 0.94)' : 'rgba(255, 255, 255, 0.96)',
        borderColor: borderColor,
        textStyle: {
          color: textColor,
          fontSize: 12
        },
        extraCssText: 'box-shadow: 0 8px 24px rgba(0,0,0,0.18); border-radius: 8px;',
        formatter: function(params) {
          const list = Array.isArray(params) ? params : [params];
          const firstValue = list[0]?.value;
          const time = Array.isArray(firstValue) ? firstValue[0] : list[0]?.axisValue || '';
          const rows = list
            .filter((item) => item?.value != null)
            .map((item) => {
              const rawValue = Array.isArray(item.value) ? item.value[1] : item.value;
              if (rawValue == null || Number.isNaN(Number(rawValue))) {
                return '';
              }

              const marker = item.marker || '';
              if (item.seriesName === '成交量') {
                return `<div>${marker}${item.seriesName}: ${Number(rawValue).toLocaleString()}</div>`;
              }

              if (item.seriesName === '大单净量') {
                const net = Number(rawValue);
                const formatted = Math.abs(net) >= 10000
                  ? `${(net / 10000).toFixed(2)}亿`
                  : `${net >= 0 ? '+' : ''}${Math.round(net)}万`;
                return `<div>${marker}大单净量: ${formatted}</div>`;
              }

              if (item.seriesName === '主力' || item.seriesName === '散户') {
                const flowIndex = fullTimeAxis.indexOf(time);
                if (flowIndex < 0) return '';
                const deltaArr = item.seriesName === '主力' ? chaodaDeltaArr : sanhuDeltaArr;
                const minuteNet = parseFloat(deltaArr[flowIndex]);
                if (Number.isNaN(minuteNet)) return '';
                return `<div>${marker}${item.seriesName}: ${formatFlowAmount(minuteNet)}</div>`;
              }

              const percentText = formatPercentLabel(rawValue);
              const priceText = item.seriesName === '价格' && prevClosePrice
                ? ` (${(prevClosePrice * (1 + Number(rawValue) / 100)).toFixed(2)})`
                : '';
              return `<div>${marker}${item.seriesName}: ${percentText}${priceText}</div>`;
            })
            .filter(Boolean);

          return [`<div style="font-weight:600;margin-bottom:4px;">${time}</div>`, ...rows].join('');
        }
      },
      grid: [
        {
          left: '4%',
          right: '10%',
          top: '5%',
          height: '56%',
        },
        {
          left: '4%',
          right: '10%',
          top: '65%',
          height: '10%',
        },
        {
          left: '4%',
          right: '10%',
          top: '79%',
          height: '17%',
        },
      ],
      xAxis: [
        {
          type: 'category',
          data: fullTimeAxis,
          scale: true,
          boundaryGap: false,
          axisLine: { 
            onZero: false,
            lineStyle: { color: borderColor }
          },
          axisTick: {
            show: false
          },
          splitLine: { 
            show: false
          },
          axisLabel: {
            color: textColor,
            formatter: formatTradingTimeLabel,
            show: true,
            interval: 0
          },
          silent: false
        },
        {
          type: 'category',
          gridIndex: 1,
          data: fullTimeAxis,
          scale: true,
          boundaryGap: false,
          axisLine: {
            onZero: false,
            lineStyle: { color: borderColor }
          },
          axisTick: {
            show: false
          },
          splitLine: {
            show: false
          },
          axisLabel: {
            show: false
          },
          silent: false
        },
        {
          type: 'category',
          gridIndex: 2,
          data: fullTimeAxis,
          scale: true,
          boundaryGap: false,
          axisLine: {
            onZero: false,
            lineStyle: { color: borderColor }
          },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          silent: false
        }
      ],
      yAxis: [
        {
          scale: false,
          min: yAxisMin,
          max: yAxisMax,
          interval: yAxisInterval,
          splitNumber: 4,
          position: 'right',
          splitArea: {
            show: false
          },
          axisLine: {
            show: false
          },
          axisTick: {
            show: false
          },
          splitLine: {
            show: false
          },
          axisLabel: {
            color: textColor,
            formatter: formatPercentLabel,
            show: true,
            inside: false,
            margin: 12,
            align: 'center',
            verticalAlign: 'middle'
          },
          silent: false
        },
        {
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          axisLabel: {
            show: false
          },
          axisLine: {
            show: false
          },
          axisTick: {
            show: false
          },
          splitLine: {
            show: false
          },
          silent: false
        },
        {
          scale: true,
          gridIndex: 2,
          splitNumber: 2,
          position: 'right',
          axisLabel: {
            show: true,
            color: textMuted,
            fontSize: 9,
            formatter: (val) => {
              const v = Math.abs(val);
              if (v >= 10000) return `${(val / 10000).toFixed(0)}亿`;
              if (v >= 1000) return `${(val / 1000).toFixed(0)}k`;
              return `${Math.round(val)}`;
            },
            margin: 4,
          },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { show: false },
          silent: false
        }
      ],
      animation: false,
      toolbox: {
        show: false
      },
      dataZoom: [],
      graphic: [],
      silent: false,
      series: [
        // 主力线、散户线暂时隐藏（数据不准，代码保留）
        // {
        //   name: '主力线', type: 'line', data: institutionalData, ...
        // },
        // {
        //   name: '散户线', type: 'line', data: retailData, ...
        // },
        ...(bigFlowData.length > 0 ? [{
          name: '主力',
          type: 'line',
          data: bigFlowData,
          smooth: false,
          connectNulls: false,
          lineStyle: {
            width: 2,
            color: '#ff4500',
            type: 'dashed'
          },
          itemStyle: {
            color: '#ff4500'
          },
          symbol: 'none',
          markPoint: {
            symbol: 'circle',
            symbolSize: 0,
            label: {
              show: true,
              position: 'top',
              color: '#ff4500',
              fontSize: 11,
              fontWeight: 'bold',
              formatter: function(params) {
                return params.name || '';
              }
            },
            data: bigFlowMarkers,
          },
          silent: false
        }] : []),
        ...(smallFlowData.length > 0 ? [{
          name: '散户',
          type: 'line',
          data: smallFlowData,
          smooth: false,
          connectNulls: false,
          lineStyle: {
            width: 1.5,
            color: '#22c55e',
            type: 'dashed'
          },
          itemStyle: {
            color: '#22c55e'
          },
          symbol: 'none',
          silent: false
        }] : []),
        {
          name: '均价',
          type: 'line',
          data: avgPriceData,
          smooth: true,
          connectNulls: true,
          lineStyle: {
            width: 1,
            color: '#ffd700'
          },
          itemStyle: {
            color: '#ffd700'
          },
          symbol: 'none',
          silent: false
        },
        {
          name: '价格',
          type: 'line',
          data: priceData,
          smooth: true,
          symbol: 'none',
          connectNulls: true,
          lineStyle: {
            width: 2,
            color: isDark ? '#ffffff' : '#1a1a1a'
          },
          itemStyle: {
            color: isDark ? '#ffffff' : '#1a1a1a'
          },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [
              {
                yAxis: 0,
                symbol: 'none',
                lineStyle: {
                  color: '#666',
                  width: 1,
                  type: 'dashed'
                },
                label: {
                  ...getZeroLineLabel()
                }
              }
            ]
          },
          silent: false
        },
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumeData,
          barWidth: '60%',
          silent: false
        },
        {
          name: '大单净量',
          type: 'bar',
          xAxisIndex: 2,
          yAxisIndex: 2,
          data: netFlowData,
          barWidth: '60%',
          silent: false,
          markLine: {
            silent: true,
            symbol: 'none',
            data: [{
              yAxis: 0,
              lineStyle: { color: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)', width: 1, type: 'dashed' },
              label: { show: false }
            }]
          }
        }
      ]
    };
    
    return chartOption;
  };

  // 获取大单汇总数据
  const getLargeOrderSummaryData = () => {
    if (largeOrdersData?.levelStats) {
      const levels = [
        { key: 'D300', label: '大于300万' },
        { key: 'D100', label: '大于100万' },
        { key: 'D50', label: '大于50万' },
        { key: 'D30', label: '大于30万' },
        { key: 'under_D30', label: '小于30万' }
      ];

      return levels.map(level => {
        const stats = largeOrdersData.levelStats[level.key] || {};
        return {
          level: level.label,
          buyCount: stats.buy_count || 0,
          sellCount: (stats.sell_count || 0) + (stats.neutral_count || 0),
          buyAmount: Number(stats.buy_amount || 0).toFixed(2),
          sellAmount: (Number(stats.sell_amount || 0) + Number(stats.neutral_amount || 0)).toFixed(2)
        };
      });
    }

    if (!timeshareData?.big_map) return [];
    
    // 从big_map数据中统计不同金额级别的数据
    const levelStats = {
      D300: { buy_count: 0, sell_count: 0, buy_amount: 0, sell_amount: 0 },
      D100: { buy_count: 0, sell_count: 0, buy_amount: 0, sell_amount: 0 },
      D50: { buy_count: 0, sell_count: 0, buy_amount: 0, sell_amount: 0 },
      D30: { buy_count: 0, sell_count: 0, buy_amount: 0, sell_amount: 0 },
      under_D30: { buy_count: 0, sell_count: 0, buy_amount: 0, sell_amount: 0 }
    };
    
    // 遍历big_map数据
    Object.keys(timeshareData.big_map).forEach(timeStr => {
      const timeData = timeshareData.big_map[timeStr];
      if (!Array.isArray(timeData)) return;
      
      timeData.forEach(item => {
        const value = parseFloat(item.amount ?? item.v);
        const rawType = item.type ?? item.t;
        const type = Number.isNaN(parseInt(rawType, 10)) ? rawType : parseInt(rawType, 10);
        
        // 判断买入还是卖出
        const isBuy = type === 1 || type === 2 || type === '主买' || type === '被买';
        const isSell = type === 3 || type === 4 || type === '主卖' || type === '被卖';
        const isNeutral = type === 4 || type === '中性';
        
        if (isBuy || isSell || isNeutral) {
          // 根据金额分类
          let level;
          if (value >= 300) {
            level = 'D300';
          } else if (value >= 100) {
            level = 'D100';
          } else if (value >= 50) {
            level = 'D50';
          } else if (value >= 30) {
            level = 'D30';
          } else {
            level = 'under_D30';
          }
          
          // 统计数据
          if (isBuy) {
            levelStats[level].buy_count++;
            levelStats[level].buy_amount += value;
          } else if (isSell) {
            levelStats[level].sell_count++;
            levelStats[level].sell_amount += value;
          } else {
            levelStats[level].neutral_count = (levelStats[level].neutral_count || 0) + 1;
            levelStats[level].neutral_amount = (levelStats[level].neutral_amount || 0) + value;
          }
        }
      });
    });
    
    // console.log('📊 big_map数据统计结果:', levelStats);
    
    const levels = [
      { key: 'D300', label: '大于300万' },
      { key: 'D100', label: '大于100万' },
      { key: 'D50', label: '大于50万' },
      { key: 'D30', label: '大于30万' },
      { key: 'under_D30', label: '小于30万' }
    ];
    
    return levels.map(level => {
      const stats = levelStats[level.key];
      return {
        level: level.label,
        buyCount: stats.buy_count || 0,
        sellCount: (stats.sell_count || 0) + (stats.neutral_count || 0),
        buyAmount: (stats.buy_amount || 0).toFixed(2),
        sellAmount: ((stats.sell_amount || 0) + (stats.neutral_amount || 0)).toFixed(2)
      };
    });
  };

  // 获取D300成本信息
  const getD300Cost = () => {
    if (timeshareData?.base_info?.d300ave_percent) {
      return timeshareData.base_info.d300ave_percent;
    }
    return '0.00%';
  };

  // 验证数据完整性
  const validateData = () => {
    if (!timeshareData) {
      return { valid: false, message: '数据未加载' };
    }
    
    const { fenshi, sanhu, volume, zhuli, base_info } = timeshareData;
    
    if (!fenshi || fenshi.length === 0) {
      return { valid: false, message: '分时数据为空' };
    }
    
    if (!sanhu || sanhu.length === 0) {
      return { valid: false, message: '散户数据为空' };
    }
    
    if (!zhuli || zhuli.length === 0) {
      return { valid: false, message: '主力数据为空' };
    }
    
    if (!volume || volume.length === 0) {
      return { valid: false, message: '成交量数据为空' };
    }
    
    if (!base_info?.prevClosePrice) {
      return { valid: false, message: '基础信息不完整' };
    }
    
    return { valid: true, message: '数据验证通过' };
  };

  const dataValidation = validateData();
  const chartOption = useMemo(
    () => getTimeshareChartOption(),
    [timeshareData, stockBasicData, largeOrdersData, filterAmount, filterThreshold, isDark, textColor, textMuted, borderColor]
  );

  return (
    <div>
      {/* 调试信息 */}
      {/* <div style={{ 
        backgroundColor: '#1f1f1f', 
        color: '#fff', 
        padding: '10px', 
        marginBottom: '10px', 
        fontSize: '12px',
        borderRadius: '4px'
      }}>
        <div style={{ fontWeight: 'bold', marginBottom: '5px' }}>分时图数据状态:</div>
        <div style={{ color: dataValidation.valid ? '#52c41a' : '#ff4d4f' }}>
          验证结果: {dataValidation.message}
        </div>
        {timeshareData && (
          <>
            <div>分时数据: {timeshareData.fenshi?.length || 0} 条</div>
            <div>主力数据: {timeshareData.zhuli?.length || 0} 条</div>
            <div>散户数据: {timeshareData.sanhu?.length || 0} 条</div>
            <div>成交量数据: {timeshareData.volume?.length || 0} 条</div>
            <div>昨收价: {timeshareData.base_info?.prevClosePrice || 'N/A'}</div>
            <div>D300成本: {getD300Cost()}</div>
          </>
        )}
        <div style={{ marginTop: '10px' }}>
          <Button 
            type="primary" 
            size="small" 
            onClick={handleLoadData}
            style={{ marginRight: '10px' }}
          >
            手动加载数据
          </Button>
          <Button 
            size="small" 
            onClick={() => {}}
          >
            查看数据
          </Button>
        </div>
      </div>
       */}
      {/* 分时图 */}
      <div className="stock-card chart-container" style={{ position: 'relative' }}>
        {/* 加载指示器 */}
        {(timeshareLoading || !timeshareData) && (
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--bg-card)',
            zIndex: 10,
            borderRadius: 'inherit',
          }}>
            <Spin size="large" tip="分时数据加载中..." />
          </div>
        )}
        {/* 图例和导航区域 */}
        <div className="chart-legend-nav">
          {/* D300/D100/D50/D30 筛选按钮暂时隐藏 */}
          <div className="period-buttons">
          </div>

          {/* 图例 */}
          <div className="chart-legend">
            <div className="legend-item">
              <span className="legend-line" style={{ borderTop: '2px dashed #ff4500', width: 20, display: 'inline-block', verticalAlign: 'middle', marginRight: 4 }}></span>
              <span className="legend-text" style={{ color: '#ff4500' }}>主力</span>
            </div>
            <div className="legend-item">
              <span className="legend-line" style={{ borderTop: '2px dashed #22c55e', width: 20, display: 'inline-block', verticalAlign: 'middle', marginRight: 4 }}></span>
              <span className="legend-text" style={{ color: '#22c55e' }}>散户</span>
            </div>
            <div className="legend-item">
              <span style={{ display: 'inline-block', width: 10, height: 10, background: '#ff4d4f', marginRight: 4, verticalAlign: 'middle' }}></span>
              <span className="legend-text" style={{ color: 'var(--text-muted)', fontSize: 11 }}>大单净量</span>
            </div>
          </div>
        </div>
        
        {/* {error && (
            <Alert
              message="错误"
              description={error}
              type="error"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )} */}
          {/* <div style={{ border: '1px solid #333', padding: '10px', marginBottom: '10px' }}>
            <div style={{ color: '#fff', fontSize: '12px', marginBottom: '5px' }}>
              图表渲染状态: {timeshareData ? '数据已加载' : '数据未加载'}
            </div>
            <div style={{ color: '#fff', fontSize: '12px', marginBottom: '5px' }}>
              图表配置: {Object.keys(getTimeshareChartOption()).length > 0 ? '已生成' : '未生成'}
            </div>
          </div> */}
        {!timeshareLoading && timeshareData && !hasTimesharePoints && (
          <div
            className="chart-empty-hint"
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-muted)',
              fontSize: 14,
              zIndex: 5,
            }}
          >
            暂无分时数据
          </div>
        )}
        <ReactEChartsCore
          key={stockCode || 'stock-chart'}
          ref={chartRef}
          echarts={echarts}
          option={chartOption}
          style={{ width: '100%', height: 480, minHeight: 420 }}
          opts={{ 
            renderer: 'canvas',
            devicePixelRatio: window.devicePixelRatio || 1
          }}
          notMerge={true}
          lazyUpdate={false}
          onChartReady={() => {
            const chart = chartRef.current?.getEchartsInstance?.();
            if (chart && chartOption?.series?.length) {
              chart.setOption(chartOption, { notMerge: true, lazyUpdate: false });
            }
          }}
          onEvents={{
            click: () => {},
          }}
        />
      </div>

      {/* 大单数据分析 - 暂时隐藏 */}
    </div>
  );
};

export default StockChart; 