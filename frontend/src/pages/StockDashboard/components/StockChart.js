import React, { useEffect } from 'react';
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
    
    const { base_info, fenshi, sanhu, volume, zhuli } = timeshareData;
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
    
    const fullTimeAxis = generateTimeAxisByLength(dataLength);
    
    // 生成big_map数据标注点
    const generateBigMapMarkers = (bigMapData, institutionalData, retailData, fullTimeAxis, filterThreshold = 300) => {
      if (!bigMapData) {
        return { institutionalMarkers: [], retailMarkers: [] };
      }

      const institutionalMarkers = [];
      const usedPositions = new Map(); // 记录每个时间点已使用的位置
      
      // 遍历big_map中的每个时间点
      Object.keys(bigMapData).forEach(timeStr => {
        const timeData = bigMapData[timeStr];
        if (!Array.isArray(timeData)) return;
        
        // 过滤出大于阈值的数据
        const filteredData = timeData.filter(item => parseFloat(item.v) > filterThreshold);
        
        filteredData.forEach(item => {
          const value = parseFloat(item.v);
          const type = parseInt(item.t);
          
          // 找到对应时间点的索引
          const timeIndex = fullTimeAxis.indexOf(timeStr);
          if (timeIndex === -1) return;
          
          // 只处理主力线数据（t=1、t=2、t=3、t=4）
          if (type === 1 || type === 2 || type === 3 || type === 4) {
            // 根据t值确定颜色和Y坐标
            let color, yValue;
            
            if (type === 1) {
              // 主买 - 深红色
              color = '#f00';
              yValue = institutionalData[timeIndex] ? institutionalData[timeIndex][1] : null;
            } else if (type === 2) {
              // 被买 - 红色
              color = '#f48cae';
              yValue = institutionalData[timeIndex] ? institutionalData[timeIndex][1] : null;
            } else if (type === 3) {
              // 主卖 - 深绿色
              color = '#0f0';
              yValue = institutionalData[timeIndex] ? institutionalData[timeIndex][1] : null;
            } else if (type === 4) {
              // 被卖 - 浅绿色
              color = '#7cf7cc';
              yValue = institutionalData[timeIndex] ? institutionalData[timeIndex][1] : null;
            }
            
            if (yValue !== null) {
              // 智能分配位置，避免重合
              const positions = ['top', 'bottom', 'left', 'right'];
              let position = 'top'; // 默认位置
              
              // 检查该时间点已使用的位置
              const usedPos = usedPositions.get(timeStr) || [];
              
              // 根据类型选择合适的位置
              if (type === 1 || type === 2) {
                // 买入类型优先选择上方位置
                if (!usedPos.includes('top')) {
                  position = 'top';
                } else if (!usedPos.includes('right')) {
                  position = 'right';
                } else if (!usedPos.includes('bottom')) {
                  position = 'bottom';
                } else {
                  position = 'left';
                }
              } else {
                // 卖出类型优先选择下方位置
                if (!usedPos.includes('bottom')) {
                  position = 'bottom';
                } else if (!usedPos.includes('left')) {
                  position = 'left';
                } else if (!usedPos.includes('top')) {
                  position = 'top';
                } else {
                  position = 'right';
                }
              }
              
              // 记录已使用的位置
              usedPositions.set(timeStr, [...usedPos, position]);
              
              // 特别调试15:00的数据
              // if (timeStr === '15:00') {
              //   console.log('🔍 15:00标注生成:', {
              //     timeStr,
              //     value,
              //     type,
              //     color,
              //     position,
              //     yValue,
              //     timeIndex,
              //     institutionalDataLength: institutionalData.length
              //   });
              // }
              
              const markerData = {
                name: Math.round(value).toString(), // 数值取整
                coord: [timeStr, yValue],
                symbol: 'circle',
                symbolSize: 4,
                itemStyle: {
                  color: 'transparent', // 透明圆点
                  borderColor: 'transparent',
                  borderWidth: 0
                },
                label: {
                  show: true,
                  position: position,
                  color: color,
                  fontSize: 9, // 加大字体
                  fontWeight: 'bold',
                  backgroundColor: 'transparent', // 透明背景
                  padding: [2, 4],
                  borderRadius: 2
                }
              };

              institutionalMarkers.push(markerData);
            } else {
              // 如果主力线数据为空，尝试使用价格数据
                              if (timeStr === '15:00') {
                  // console.log('❌ 15:00 yValue为null，尝试使用价格数据');
                  const priceIndex = fullTimeAxis.indexOf(timeStr);
                  if (priceIndex !== -1 && fenshi[priceIndex]) {
                    const price = parseFloat(fenshi[priceIndex]);
                    const percentChange = ((price - prevClosePrice) / prevClosePrice) * 100;
                  
                  // 智能分配位置
                  const usedPos = usedPositions.get(timeStr) || [];
                  let position = 'top';
                  
                  if (type === 1 || type === 2) {
                    if (!usedPos.includes('top')) {
                      position = 'top';
                    } else if (!usedPos.includes('right')) {
                      position = 'right';
                    } else if (!usedPos.includes('bottom')) {
                      position = 'bottom';
                    } else {
                      position = 'left';
                    }
                  } else {
                    if (!usedPos.includes('bottom')) {
                      position = 'bottom';
                    } else if (!usedPos.includes('left')) {
                      position = 'left';
                    } else if (!usedPos.includes('top')) {
                      position = 'top';
                    } else {
                      position = 'right';
                    }
                  }
                  
                  usedPositions.set(timeStr, [...usedPos, position]);
                  
                  const markerData = {
                    name: Math.round(value).toString(),
                    coord: [timeStr, percentChange],
                    symbol: 'circle',
                    symbolSize: 4,
                    itemStyle: {
                      color: 'transparent',
                      borderColor: 'transparent',
                      borderWidth: 0
                    },
                    label: {
                      show: true,
                      position: position,
                      color: color,
                      fontSize: 9,
                      fontWeight: 'bold',
                      backgroundColor: 'transparent',
                      padding: [2, 4],
                      borderRadius: 2
                    }
                  };

                  institutionalMarkers.push(markerData);
                  // console.log('✅ 15:00使用价格数据生成标注:', {
                  //   timeStr,
                  //   value,
                  //   type,
                  //   color,
                  //   position,
                  //   percentChange
                  // });
                }
              }
            }
          }
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
    
    // 主力线数据（红色）- 净流入流出趋势线
    const institutionalData = zhuli.map((value, index) => {
      const timePoint = fullTimeAxis[index];
      if (timePoint && value) {
        const rawValue = parseFloat(value);
        // 将主力资金数据转换为净流入流出趋势线
        // 从0轴开始，净流入为正（向上），净流出为负（向下）
        // 数据范围约-5000到+2000，转换为百分比变化
        const netFlowPercent = (rawValue / 10000) * 2; // 每1万资金对应2%的变化
        
        // 限制在合理范围内
        return [timePoint, Math.max(-10, Math.min(10, netFlowPercent))];
      }
      return [timePoint, null];
    });
    
    // 调试15:00的主力线数据
    const timeIndex15 = fullTimeAxis.indexOf('15:00');
    if (timeIndex15 !== -1) {
      // console.log('🔍 15:00主力线数据:', {
      //   timeIndex15,
      //   zhuliLength: zhuli.length,
      //   institutionalDataLength: institutionalData.length,
      //   zhuliAt15: zhuli[timeIndex15],
      //   institutionalDataAt15: institutionalData[timeIndex15],
      //   fullTimeAxisAt15: fullTimeAxis[timeIndex15]
      // });
    }
    
    // 散户线数据（绿色）- 净流入流出趋势线
    const retailData = sanhu.map((value, index) => {
      const timePoint = fullTimeAxis[index];
      if (timePoint && value) {
        const rawValue = parseFloat(value);
        // 将散户资金数据转换为净流入流出趋势线
        // 从0轴开始，净流入为正（向上），净流出为负（向下）
        // 数据范围约-600到+2500，转换为百分比变化
        const netFlowPercent = (rawValue / 10000) * 3; // 每1万资金对应3%的变化
        
        // 限制在合理范围内
        return [timePoint, Math.max(-10, Math.min(10, netFlowPercent))];
      }
      return [timePoint, null];
    });
    
    // 根据base_info动态计算Y轴范围
    const highPrice = parseFloat(base_info?.highPrice || 6.08);
    const lowPrice = parseFloat(base_info?.lowPrice || 5.53);
    
    // 计算涨停价和跌停价（A股涨跌停幅度为10%）
    const upperLimitPrice = prevClosePrice * 1.1; // 涨停价
    const lowerLimitPrice = prevClosePrice * 0.9; // 跌停价
    
    // 计算最高价与涨停价的比值，最低价与跌停价的比值
    const highToUpperRatio = ((highPrice - prevClosePrice) / (upperLimitPrice - prevClosePrice)) * 10; // 转换为百分比
    const lowToLowerRatio = ((lowPrice - prevClosePrice) / (lowerLimitPrice - prevClosePrice)) * 10; // 转换为百分比
    
    // 设置Y轴范围，取较大的绝对值作为范围，确保上下对称
    const maxRange = Math.max(Math.abs(highToUpperRatio), Math.abs(lowToLowerRatio));
    // 确保最小范围为±1%，最大范围为±10%
    const adjustedRange = Math.max(1, Math.min(10, maxRange));
    const yAxisMax = adjustedRange; // 例如5%
    const yAxisMin = -adjustedRange; // 例如-5%
    
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
      filterThreshold // 传递筛选阈值
    );
    
    // 详细调试big_map数据处理
    if (timeshareData.big_map) {
      // console.log('🔍 详细big_map数据处理:');
      // console.log('时间轴范围:', fullTimeAxis[0], '到', fullTimeAxis[fullTimeAxis.length - 1]);
      // console.log('时间轴长度:', fullTimeAxis.length);
      
      Object.keys(timeshareData.big_map).forEach(timeStr => {
        const timeData = timeshareData.big_map[timeStr];
        const filteredData = timeData.filter(item => parseFloat(item.v) > filterThreshold);
        if (filteredData.length > 0) {
          const timeIndex = fullTimeAxis.indexOf(timeStr);
          // console.log(`时间 ${timeStr} (索引: ${timeIndex}):`, filteredData);
        }
      });
      
      // 特别检查15:00的数据
      if (timeshareData.big_map['15:00']) {
        // console.log('🔍 15:00数据详情:', timeshareData.big_map['15:00']);
        const timeIndex15 = fullTimeAxis.indexOf('15:00');
        // console.log('15:00在时间轴中的索引:', timeIndex15);
      }
    }

    const chartOption = {
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
            color: '#fff',
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
          min: yAxisMin,
          max: yAxisMax,
          interval: Math.ceil((yAxisMax - yAxisMin) / 6), // 确保上下各3个刻度，总共7个刻度（包括0轴）
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
          markPoint: {
            symbol: 'circle',
            symbolSize: 4,
            z: 100,
            itemStyle: {
              color: 'transparent', // 透明圆点
              borderColor: 'transparent',
              borderWidth: 0
            },
            label: {
              show: true,
              position: 'top',
              color: '#ff4d4f',
              fontSize: 12, // 缩小字体
              fontWeight: 'bold',
              backgroundColor: 'transparent', // 去掉背景
              padding: [2, 4], // 减少padding
              borderRadius: 2,
              formatter: function(params) {
                return params.name || params.value || '0';
              }
            },
            data: bigMapInstitutionalMarkers
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
        const value = parseFloat(item.v);
        const type = parseInt(item.t);
        
        // 判断买入还是卖出
        const isBuy = type === 1 || type === 2; // 主买或被买
        const isSell = type === 3 || type === 4; // 主卖或被卖
        
        if (isBuy || isSell) {
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
          } else {
            levelStats[level].sell_count++;
            levelStats[level].sell_amount += value;
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
        sellCount: stats.sell_count || 0,
        buyAmount: (stats.buy_amount || 0).toFixed(2),
        sellAmount: (stats.sell_amount || 0).toFixed(2)
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
      <div className="stock-card chart-container">
        {/* 图例和导航区域 */}
        <div className="chart-legend-nav">
          {/* 时间导航 */}
          <div className="date-navigation">
            <Button type="text" size="small" style={{ color: '#fff' }}>&lt;&lt;</Button>
            <span style={{ color: '#fff', margin: '0 10px' }}>2025-7-16</span>
            <Button type="text" size="small" style={{ color: '#fff' }}>&gt;&gt;</Button>
          </div>

          {/* 时间段选择按钮 */}
          <div className="period-buttons">
            <Button 
              type="text" 
              size="small" 
              style={{ 
                color: filterThreshold === 300 ? '#ffa940' : '#fff', 
                backgroundColor: filterThreshold === 300 ? 'rgba(255, 169, 64, 0.1)' : 'transparent' 
              }}
              onClick={() => handleFilterChange(300)}
            >
              D300
            </Button>
            <Button 
              type="text" 
              size="small" 
              style={{ 
                color: filterThreshold === 100 ? '#ffa940' : '#fff', 
                backgroundColor: filterThreshold === 100 ? 'rgba(255, 169, 64, 0.1)' : 'transparent' 
              }}
              onClick={() => handleFilterChange(100)}
            >
              D100
            </Button>
            <Button 
              type="text" 
              size="small" 
              style={{ 
                color: filterThreshold === 50 ? '#ffa940' : '#fff', 
                backgroundColor: filterThreshold === 50 ? 'rgba(255, 169, 64, 0.1)' : 'transparent' 
              }}
              onClick={() => handleFilterChange(50)}
            >
              D50
            </Button>
            <Button 
              type="text" 
              size="small" 
              style={{ 
                color: filterThreshold === 30 ? '#ffa940' : '#fff', 
                backgroundColor: filterThreshold === 30 ? 'rgba(255, 169, 64, 0.1)' : 'transparent' 
              }}
              onClick={() => handleFilterChange(30)}
            >
              D30
            </Button>
          </div>

          {/* 图例 */}
          <div className="chart-legend">
            <div className="legend-item">
              <span className="legend-line main-line"></span>
              <span className="legend-text">主力净流入</span>
            </div>
            <div className="legend-item">
              <span className="legend-line retail-line"></span>
              <span className="legend-text">散户净流入</span>
            </div>
            {/* <div className="legend-item">
              <span className="legend-line avg-line"></span>
              <span className="legend-text">价格均线 ——</span>
            </div> */}
            <div className="cost-indicator">
              <span style={{ color: '#ffa940' }}>D300成本: {getD300Cost()}</span>
            </div>
          </div>
        </div>
        
        <Spin spinning={loading}>
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
            style={{  }}
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
        </Spin>
      </div>

      {/* 大单数据分析 */}
      {timeshareData?.big_map && (
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
      )}
    </div>
  );
};

export default StockChart; 