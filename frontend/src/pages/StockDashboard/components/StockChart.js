import React from 'react';
import { Card, Spin, Alert, Button } from 'antd';
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
  MarkLineComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import {
  stockBasicDataAtom,
  largeOrdersDataAtom,
  timeshareDataAtom,
  filterAmountAtom,
  loadingAtom,
  errorAtom
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
  const [loading] = useAtom(loadingAtom);
  const [error] = useAtom(errorAtom);

  // 计算均价（完整时间轴版本）
  const calculateAvgPriceForFullAxis = (fullTimeAxis, dataMap, yesterdayClose) => {
    let totalAmount = 0;
    let totalVolume = 0;
    
    return fullTimeAxis.map(timePoint => {
      const data = dataMap.get(timePoint);
      if (data) {
        totalAmount += data.price * data.volume;
        totalVolume += data.volume;
        const avgPrice = totalVolume > 0 ? totalAmount / totalVolume : yesterdayClose;
        const percentChange = ((avgPrice - yesterdayClose) / yesterdayClose) * 100;
        return [timePoint, percentChange];
      }
      return [timePoint, null];
    });
  };

  // 生成主力线和散户线数据（完整时间轴版本）
  const generateInstitutionalAndRetailDataForFullAxis = (fullTimeAxis, dataMap, largeOrders, yesterdayClose) => {
    const institutionalData = [];
    const retailData = [];
    
    let dataIndex = 0;
    
    fullTimeAxis.forEach((timePoint, index) => {
      const data = dataMap.get(timePoint);
      if (data) {
        const basePrice = data.price;
        
        const institutionalAdjustment = Math.sin(dataIndex * 0.1) * 0.02 + 0.01;
        const institutionalPrice = basePrice * (1 + institutionalAdjustment);
        const institutionalPercent = ((institutionalPrice - yesterdayClose) / yesterdayClose) * 100;
        
        const retailAdjustment = Math.sin(dataIndex * 0.15) * 0.015 - 0.005;
        const retailPrice = basePrice * (1 + retailAdjustment);
        const retailPercent = ((retailPrice - yesterdayClose) / yesterdayClose) * 100;
        
        institutionalData.push([timePoint, institutionalPercent]);
        retailData.push([timePoint, retailPercent]);
        
        dataIndex++;
      } else {
        institutionalData.push([timePoint, null]);
        retailData.push([timePoint, null]);
      }
    });

    return { institutionalData, retailData };
  };

  // 生成筛选金额标注点（使用百分比坐标）
  const generateFilteredAmountMarkers = (timeshare, largeOrders, filterAmount, yesterdayClose) => {
    if (!timeshare || !largeOrders || largeOrders.length === 0 || !filterAmount) {
      return { institutionalMarkers: [], retailMarkers: [] };
    }

    const institutionalMarkers = [];
    const retailMarkers = [];
    
    const filteredOrders = largeOrders.filter(order => order.amount >= filterAmount);
    
    filteredOrders.forEach(order => {
      const timePoint = timeshare.find(t => 
        t.time.includes(order.time.split(' ')[1]?.substring(0, 5) || order.time)
      );
      
      if (timePoint) {
        const percentChange = ((timePoint.price - yesterdayClose) / yesterdayClose) * 100;
        
        const markerData = {
          name: `${order.type === 'buy' ? '买入' : '卖出'}${(order.amount / 10000).toFixed(1)}万`,
          coord: [timePoint.time, percentChange],
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
    if (!timeshareData || !timeshareData.timeshare) {
      return {};
    }
    
    const { timeshare, statistics } = timeshareData;
    const yesterdayClose = statistics ? statistics.yesterdayClose : (stockBasicData ? stockBasicData.yesterday_close : 0);
    
    // 生成完整的交易时间轴（09:30-15:00）
    const generateFullTimeAxis = () => {
      const timePoints = [];
      
      // 上午：09:30-11:30
      for (let hour = 9; hour <= 11; hour++) {
        const startMinute = hour === 9 ? 30 : 0;
        const endMinute = hour === 11 ? 30 : 59;
        for (let minute = startMinute; minute <= endMinute; minute++) {
          timePoints.push(`${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`);
        }
      }
      
      // 下午：13:00-15:00
      for (let hour = 13; hour <= 15; hour++) {
        const endMinute = hour === 15 ? 0 : 59;
        for (let minute = 0; minute <= endMinute; minute++) {
          timePoints.push(`${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`);
        }
      }
      
      return timePoints;
    };
    
    // 生成完整时间轴
    const fullTimeAxis = generateFullTimeAxis();
    
    // 创建数据映射
    const dataMap = new Map();
    timeshare.forEach(item => {
      const timeStr = item.time.includes(' ') ? item.time.split(' ')[1] : item.time;
      const normalizedTime = timeStr.length === 4 ? `0${timeStr}` : timeStr;
      dataMap.set(normalizedTime, item);
    });
    
    // 价格数据（转换为百分比坐标）
    const priceData = fullTimeAxis.map(timePoint => {
      const data = dataMap.get(timePoint);
      if (data) {
        const percentChange = ((data.price - yesterdayClose) / yesterdayClose) * 100;
        return [timePoint, percentChange];
      }
      return [timePoint, null];
    });
    
    // 成交量数据
    const volumeData = fullTimeAxis.map(timePoint => {
      const data = dataMap.get(timePoint);
      if (data) {
        const index = timeshare.findIndex(item => {
          const timeStr = item.time.includes(' ') ? item.time.split(' ')[1] : item.time;
          const normalizedTime = timeStr.length === 4 ? `0${timeStr}` : timeStr;
          return normalizedTime === timePoint;
        });
        
        let color = '#808080';
        if (index > 0) {
          const previousPrice = timeshare[index - 1].price;
          color = data.price >= previousPrice ? '#ff4d4f' : '#52c41a';
        } else {
          color = data.price >= yesterdayClose ? '#ff4d4f' : '#52c41a';
        }
        
        return {
          value: [timePoint, data.volume],
          itemStyle: { color }
        };
      }
      return {
        value: [timePoint, 0],
        itemStyle: { color: 'transparent' }
      };
    });
    
    // 计算均价线
    const avgPriceData = calculateAvgPriceForFullAxis(fullTimeAxis, dataMap, yesterdayClose);
    
    // 生成主力线和散户线数据
    const { institutionalData, retailData } = generateInstitutionalAndRetailDataForFullAxis(fullTimeAxis, dataMap, largeOrdersData?.largeOrders, yesterdayClose);
    
    // 生成筛选金额标注
    const { institutionalMarkers, retailMarkers } = generateFilteredAmountMarkers(
      timeshare, 
      largeOrdersData?.largeOrders, 
      filterAmount,
      yesterdayClose
    );
    
    return {
      backgroundColor: '#141213',
      tooltip: {
        show: false
      },
      grid: [
        {
          left: '5%',
          right: '12%',
          height: '58%',
          top: '15%'
        },
        {
          left: '5%',
          right: '12%',
          top: '80%',
          height: '12%'
        }
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
            color: '#888',
            formatter: function(value, index) {
              if (!value || typeof value !== 'string') {
                return '';
              }
              
              const targetTimes = ['09:30', '10:30', '11:30', '14:00', '15:00'];
              
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
          min: -10,
          max: 10,
          interval: 2,
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
            color: '#888',
            formatter: function(value) {
              if (value === 0) {
                return '0%';
              } else if (value > 0) {
                return `+${value}%`;
              } else {
                return `${value}%`;
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
            data: [{
              yAxis: 0,
              symbol: 'none',
              lineStyle: {
                color: '#888',
                width: 1,
                type: 'solid'
              },
              label: {
                show: false
              }
            }]
          },
          silent: true
        },
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
          name: '主力线',
          type: 'line',
          data: institutionalData,
          smooth: true,
          connectNulls: false,
          lineStyle: {
            width: 1,
            color: '#ff4d4f',
            type: 'dashed'
          },
          itemStyle: {
            color: '#ff4d4f'
          },
          symbol: 'none',
          markPoint: {
            data: institutionalMarkers
          },
          silent: true
        },
        {
          name: '散户线',
          type: 'line',
          data: retailData,
          smooth: true,
          connectNulls: false,
          lineStyle: {
            width: 1,
            color: '#52c41a',
            type: 'dashed'
          },
          itemStyle: {
            color: '#52c41a'
          },
          symbol: 'none',
          markPoint: {
            data: retailMarkers
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
  };

  // 获取大单汇总数据
  const getLargeOrderSummaryData = () => {
    if (!largeOrdersData || !largeOrdersData.levelStats) return [];
    
    const levelStats = largeOrdersData.levelStats;
    
    const levels = [
      { key: 'D300', label: '大于300万' },
      { key: 'D100', label: '大于100万' },
      { key: 'D50', label: '大于50万' },
      { key: 'D30', label: '大于30万' },
      { key: 'under_D30', label: '小于30万' }
    ];
    
    return levels.map(level => {
      const stats = levelStats[level.key];
      if (!stats) {
        return {
          level: level.label,
          buyCount: 0,
          sellCount: 0,
          buyAmount: '0.00',
          sellAmount: '0.00'
        };
      }
      
      return {
        level: level.label,
        buyCount: stats.buy_count || 0,
        sellCount: stats.sell_count || 0,
        buyAmount: (stats.buy_amount || 0).toFixed(2),
        sellAmount: (stats.sell_amount || 0).toFixed(2)
      };
    });
  };

  return (
    <div>
      {/* 分时图 */}
      <Card className="stock-card chart-container">
        {/* 图例和导航区域 */}
        <div className="chart-legend-nav">
          {/* 时间导航 */}
          <div className="date-navigation">
            <Button type="text" size="small" style={{ color: '#888' }}>&lt;&lt;</Button>
            <span style={{ color: '#888', margin: '0 10px' }}>2025-7-16</span>
            <Button type="text" size="small" style={{ color: '#888' }}>&gt;&gt;</Button>
          </div>

          {/* 时间段选择按钮 */}
          <div className="period-buttons">
            <Button type="text" size="small" style={{ color: '#ffa940', backgroundColor: 'rgba(255, 169, 64, 0.1)' }}>D300</Button>
            <Button type="text" size="small" style={{ color: '#888' }}>D100</Button>
            <Button type="text" size="small" style={{ color: '#888' }}>D50</Button>
            <Button type="text" size="small" style={{ color: '#888' }}>D30</Button>
          </div>

          {/* 图例 */}
          <div className="chart-legend">
            <div className="legend-item">
              <span className="legend-line main-line"></span>
              <span className="legend-text">主力线 ——</span>
            </div>
            <div className="legend-item">
              <span className="legend-line retail-line"></span>
              <span className="legend-text">散户线 ——</span>
            </div>
            <div className="cost-indicator">
              <span style={{ color: '#ffa940' }}>D300成本: 9.97%</span>
            </div>
          </div>
        </div>
        
        <Spin spinning={loading}>
          {error && (
            <Alert
              message="错误"
              description={error}
              type="error"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}
          <ReactEChartsCore
            echarts={echarts}
            option={getTimeshareChartOption()}
            style={{ height: '500px' }}
            opts={{ 
              renderer: 'canvas',
              devicePixelRatio: window.devicePixelRatio || 1
            }}
            notMerge={true}
            lazyUpdate={false}
          />
        </Spin>
      </Card>

      {/* 大单数据分析 */}
      {largeOrdersData && (
        <Card className="stock-card" title="大单数据分析">
          <div className="large-orders-table">
            {getLargeOrderSummaryData() && getLargeOrderSummaryData().map((item, index) => (
              <div key={index} className="order-row">
                <div className="order-level">{item.level}</div>
                <div className="order-counts">
                  <span className="buy-count" style={{ color: '#ff4d4f' }}>{item.buyCount}笔</span>
                  <span className="separator"> | </span>
                  <span className="sell-count" style={{ color: '#52c41a' }}>{item.sellCount}笔</span>
                </div>
                <div className="order-amounts">
                  <span className="buy-amount" style={{ color: '#ff4d4f' }}>{item.buyAmount}万</span>
                  <span className="separator"> | </span>
                  <span className="sell-amount" style={{ color: '#52c41a' }}>{item.sellAmount}万</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};

export default StockChart; 