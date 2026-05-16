import React, { useEffect } from 'react';
import { Button, Spin } from 'antd';
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
  stockBasicDataAtom,
  largeOrdersDataAtom,
  timeshareDataAtom,
  filterAmountAtom,
  loadingAtom,
  errorAtom,
  fetchTimeshareDataAtom
} from '../../../store/atoms';

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

const StockChart = () => {
  const [stockBasicData] = useAtom(stockBasicDataAtom);
  const [largeOrdersData] = useAtom(largeOrdersDataAtom);
  const [timeshareData] = useAtom(timeshareDataAtom);
  const [filterAmount] = useAtom(filterAmountAtom);
  const [error] = useAtom(errorAtom);
  const [loading] = useAtom(loadingAtom);
  const [, fetchTimeshareData] = useAtom(fetchTimeshareDataAtom);

  // 添加筛选阈值状态，默认300
  const [filterThreshold, setFilterThreshold] = React.useState(300);

  // 数据验证
  if (timeshareData) {
    // 数据验证逻辑保留，但去掉console.log
  } else {
    // timeshareData 为空或格式不正确
  }

  // 测试数据加载
  useEffect(() => {
    if (timeshareData) {
      // 分时图数据加载成功
    } else {
      // 分时图数据未加载
    }
  }, [timeshareData]);

  // 手动触发数据加载
  const handleLoadData = () => {
    fetchTimeshareData('603001');
  };

  // 处理筛选阈值切换
  const handleFilterChange = (threshold) => {
    setFilterThreshold(threshold);
  };

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
            borderColor: '#fff',
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
    const prevClosePrice = parseFloat(base_info?.prevClosePrice || 12.59);
    
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
      const isBuyOrder = (item) => {
        const rawType = item.type ?? item.t ?? item.direction;
        const type = Number.isNaN(parseInt(rawType, 10)) ? rawType : parseInt(rawType, 10);
        return type === 1 || type === 2 || type === '主买' || type === '被买';
      };
      const isSellOrder = (item) => {
        const rawType = item.type ?? item.t ?? item.direction;
        const type = Number.isNaN(parseInt(rawType, 10)) ? rawType : parseInt(rawType, 10);
        return type === 3 || type === 4 || type === '主卖' || type === '被卖';
      };
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
    
    // 价格数据（转换为百分比坐标）
    const priceData = fenshi.map((price, index) => {
      const timePoint = fullTimeAxis[index];
      if (timePoint && price) {
        const percentChange = ((parseFloat(price) - prevClosePrice) / prevClosePrice) * 100;
        return [timePoint, percentChange];
      }
      return [fullTimeAxis[index], null];
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
      if (timePoint && price && volume[index]) {
        const currentPrice = parseFloat(price);
        const currentVolume = volume[index];
        totalAmount += currentPrice * currentVolume;
        totalVolume += currentVolume;
        const avgPrice = totalVolume > 0 ? totalAmount / totalVolume : prevClosePrice;
        const percentChange = ((avgPrice - prevClosePrice) / prevClosePrice) * 100;
        avgPriceData.push([timePoint, percentChange]);
      } else {
        avgPriceData.push([timePoint, null]);
      }
    });
    
    // Y 轴：按分时实际涨跌幅区间收紧，避免 ±1% 把曲线压扁
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
    let lo = allPct.length ? Math.min(...allPct, 0) : -0.15;
    let hi = allPct.length ? Math.max(...allPct, 0) : 0.15;
    const span = Math.max(hi - lo, 0.08);
    const pad = Math.max(span * 0.15, 0.03);
    let yAxisMax = hi + pad;
    let yAxisMin = lo - pad;
    if (!Number.isFinite(yAxisMax) || !Number.isFinite(yAxisMin) || yAxisMax <= yAxisMin) {
      yAxisMax = 0.2;
      yAxisMin = -0.2;
    }
    
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

    // 资金博弈线：红线 = (超大单+大单)/2，绿线 = (小单+中单)/2
    const bigFlowData = [];
    const smallFlowData = [];
    let bigFlowMarkers = [];
    const moneyFlow = timeshareData.money_flow;
    if (moneyFlow && moneyFlow.chaoda && moneyFlow.chaoda.length > 0) {
      const chaodaArr = moneyFlow.chaoda;
      const dadanArr = moneyFlow.dadan || [];
      const xiaoArr = moneyFlow.sanhu || [];
      const zhongArr = moneyFlow.zhongdan || [];
      const len = chaodaArr.length;

      // 计算合并后的原始值
      const bigRaw = [];   // (超大单+大单)/2
      const smallRaw = []; // (小单+中单)/2
      for (let i = 0; i < len; i++) {
        bigRaw.push(((parseFloat(chaodaArr[i]) || 0) + (parseFloat(dadanArr[i]) || 0)) / 2);
        smallRaw.push(((parseFloat(xiaoArr[i]) || 0) + (parseFloat(zhongArr[i]) || 0)) / 2);
      }

      // 共用归一化基准
      const maxAbsFlow = Math.max(
        ...bigRaw.map(Math.abs),
        ...smallRaw.map(Math.abs),
        0.01
      );
      const yRange = (yAxisMax - yAxisMin) * 0.3;
      const yMid = (yAxisMax + yAxisMin) / 2;

      for (let i = 0; i < len; i++) {
        const timePoint = fullTimeAxis[i];
        if (!timePoint || !fenshi[i]) {
          bigFlowData.push([fullTimeAxis[i] || '', null]);
          smallFlowData.push([fullTimeAxis[i] || '', null]);
          continue;
        }
        bigFlowData.push([timePoint, yMid + (bigRaw[i] / maxAbsFlow) * yRange]);
        smallFlowData.push([timePoint, yMid + (smallRaw[i] / maxAbsFlow) * yRange]);
      }

      // 在关键时间点标注金额（整点/半点 + 最后一个有效点）
      const markerTimes = ['09:30', '10:00', '10:30', '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00'];
      const timeToIndex = {};
      for (let i = 0; i < len; i++) {
        if (fullTimeAxis[i]) timeToIndex[fullTimeAxis[i]] = i;
      }
      const formatFlowLabel = (val) => {
        const absVal = Math.abs(val);
        return absVal >= 10000
          ? `${(val / 10000).toFixed(2)}亿`
          : `${Math.round(val)}万`;
      };
      for (const t of markerTimes) {
        const idx = timeToIndex[t];
        if (idx !== undefined && bigFlowData[idx] && bigFlowData[idx][1] !== null) {
          const totalVal = bigRaw[idx] * 2;
          bigFlowMarkers.push({
            coord: bigFlowData[idx],
            name: formatFlowLabel(totalVal),
            value: formatFlowLabel(totalVal),
          });
        }
      }
      // 确保最后一个有效点一定标注
      for (let i = len - 1; i >= 0; i--) {
        if (bigFlowData[i] && bigFlowData[i][1] !== null) {
          const t = fullTimeAxis[i];
          if (!markerTimes.includes(t)) {
            const totalVal = bigRaw[i] * 2;
            bigFlowMarkers.push({
              coord: bigFlowData[i],
              name: formatFlowLabel(totalVal),
              value: formatFlowLabel(totalVal),
            });
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

    const chartOption = {
      backgroundColor: 'transparent',
      tooltip: {
        show: false
      },
      grid: [
        {
          left: '4%',
          right: '10%',
          top: '8%',
          height: '72%',
        },
        {
          left: '4%',
          right: '10%',
          top: '84%',
          height: '12%',
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
            lineStyle: { color: '#444' }
          },
          axisTick: {
            show: false
          },
          splitLine: { 
            show: false
          },
          axisLabel: {
            color: '#fff',
            formatter: function(value, index) {
              if (!value || typeof value !== 'string') {
                return '';
              }
              
              const targetTimes = ['09:30', '10:30', '11:30', '13:00', '14:00', '15:00'];
              
              if (targetTimes.includes(value)) {
                return value;
              }
              
              return '';
            },
            show: true,
            interval: 0
          },
          silent: true
        },
        {
          type: 'category',
          gridIndex: 1,
          data: fullTimeAxis,
          scale: true,
          boundaryGap: false,
          axisLine: { 
            onZero: false,
            lineStyle: { color: '#444' }
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
          silent: true
        }
      ],
      yAxis: [
        {
          scale: false,
          min: yAxisMin,
          max: yAxisMax,
          splitNumber: 6,
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
            color: '#fff',
            formatter: function(value) {
              // 取整到小数点后2位
              const roundedValue = Math.round(value * 100) / 100;
              if (roundedValue === 0) {
                return '0%';
              } else if (roundedValue > 0) {
                return `+${roundedValue}%`;
              } else {
                return `${roundedValue}%`;
              }
            },
            show: true,
            inside: false,
            margin: 12,
            align: 'center',
            verticalAlign: 'middle'
          },
          silent: true
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
          silent: true
        }
      ],
      animation: false,
      brush: {
        show: false
      },
      toolbox: {
        show: false
      },
      dataZoom: [],
      graphic: [],
      silent: true,
      series: [
        // 主力线、散户线暂时隐藏（数据不准，代码保留）
        // {
        //   name: '主力线', type: 'line', data: institutionalData, ...
        // },
        // {
        //   name: '散户线', type: 'line', data: retailData, ...
        // },
        ...(bigFlowData.length > 0 ? [{
          name: '大资金',
          type: 'line',
          data: bigFlowData,
          smooth: true,
          connectNulls: true,
          lineStyle: {
            width: 2,
            color: '#ff4500'
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
          silent: true
        }] : []),
        ...(smallFlowData.length > 0 ? [{
          name: '小资金',
          type: 'line',
          data: smallFlowData,
          smooth: true,
          connectNulls: true,
          lineStyle: {
            width: 1.5,
            color: '#22c55e'
          },
          itemStyle: {
            color: '#22c55e'
          },
          symbol: 'none',
          silent: true
        }] : []),
        {
          name: '均价',
          type: 'line',
          data: avgPriceData,
          smooth: true,
          connectNulls: false,
          lineStyle: {
            width: 1,
            color: '#ffd700'
          },
          itemStyle: {
            color: '#ffd700'
          },
          symbol: 'none',
          silent: true
        },
        {
          name: '价格',
          type: 'line',
          data: priceData,
          smooth: true,
          symbol: 'none',
          connectNulls: false,
          lineStyle: {
            width: 2,
            color: '#ffffff'
          },
          itemStyle: {
            color: '#ffffff'
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
                  show: true,
                  position: 'end',
                  color: '#666',
                  fontSize: 10,
                  formatter: '0%'
                }
              }
            ]
          },
          silent: true
        },
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumeData,
          barWidth: '60%',
          silent: true
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
        {(loading || !timeshareData) && (
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
              <span className="legend-line" style={{ borderTop: '2px solid #ff4500', width: 20, display: 'inline-block', verticalAlign: 'middle', marginRight: 4 }}></span>
              <span className="legend-text" style={{ color: '#ff4500' }}>大资金</span>
            </div>
            <div className="legend-item">
              <span className="legend-line" style={{ borderTop: '2px solid #22c55e', width: 20, display: 'inline-block', verticalAlign: 'middle', marginRight: 4 }}></span>
              <span className="legend-text" style={{ color: '#22c55e' }}>小资金</span>
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
        <ReactEChartsCore
          echarts={echarts}
          option={getTimeshareChartOption()}
          style={{ width: '100%', height: 480, minHeight: 420 }}
          opts={{ 
            renderer: 'canvas',
            devicePixelRatio: window.devicePixelRatio || 1
          }}
          notMerge={true}
          lazyUpdate={false}
          onChartReady={(chart) => {
            // console.log('✅ ECharts 图表已准备就绪:', chart);
          }}
          onEvents={{
            click: (params) => {
              // console.log('图表点击事件:', params);
            }
          }}
        />
      </div>

      {/* 大单数据分析 - 暂时隐藏 */}
    </div>
  );
};

export default StockChart; 