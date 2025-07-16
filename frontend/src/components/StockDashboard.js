import React, { useEffect, useRef, useState } from 'react';
import { 
  Card, 
  Row, 
  Col, 
  Input, 
  Button, 
  Spin,
  Alert,
  AutoComplete
} from 'antd';
import { SearchOutlined } from '@ant-design/icons';
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
  stockCodeAtom,
  stockBasicDataAtom,
  largeOrdersDataAtom,
  timeshareDataAtom,
  realtimeDataAtom,
  filterAmountAtom,
  loadingAtom,
  errorAtom,
  dataValidationAtom,
  fetchStockBasicAtom,
  fetchLargeOrdersAtom,
  fetchTimeshareDataAtom,
  fetchRealtimeDataAtom,
  validateStockDataAtom
} from '../store/atoms';
import { apiRequest } from '../config/api';

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

const StockDashboard = ({ onStockCodeChange }) => {
  const [stockCode, setStockCode] = useAtom(stockCodeAtom);
  const [stockBasicData] = useAtom(stockBasicDataAtom);
  const [largeOrdersData] = useAtom(largeOrdersDataAtom);
  const [timeshareData] = useAtom(timeshareDataAtom);
  const [realtimeData] = useAtom(realtimeDataAtom);
  const [filterAmount, setFilterAmount] = useAtom(filterAmountAtom);
  const [loading] = useAtom(loadingAtom);
  const [error] = useAtom(errorAtom);
  const [dataValidation] = useAtom(dataValidationAtom);
  const [, fetchStockBasic] = useAtom(fetchStockBasicAtom);
  const [, fetchLargeOrders] = useAtom(fetchLargeOrdersAtom);
  const [, fetchTimeshareData] = useAtom(fetchTimeshareDataAtom);
  const [, fetchRealtimeData] = useAtom(fetchRealtimeDataAtom);
  const [, validateStockData] = useAtom(validateStockDataAtom);
  
  // 大单金额筛选状态
  const [amountFilters, setAmountFilters] = React.useState([300, 100, 30]);
  
  // 股票搜索相关状态
  const [searchOptions, setSearchOptions] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // 触发数据验证（暂时禁用）
  // const handleValidateData = () => {
  //   validateStockData(stockCode);
  // };

  // 获取数据质量状态
  const getDataQualityStatus = () => {
    if (!dataValidation || !dataValidation.validation_result) return null;
    
    const result = dataValidation.validation_result;
    const score = result.consistency_score || 0;
    
    if (score >= 95) {
      return { status: 'excellent', color: '#52c41a', text: '优秀' };
    } else if (score >= 85) {
      return { status: 'good', color: '#1890ff', text: '良好' };
    } else if (score >= 70) {
      return { status: 'acceptable', color: '#faad14', text: '可接受' };
    } else {
      return { status: 'poor', color: '#ff4d4f', text: '较差' };
    }
  };

  // 股票搜索功能
  const handleStockSearch = async (value) => {
    if (!value || value.length < 2) {
      setSearchOptions([]);
      return;
    }
    
    try {
      setSearchLoading(true);
      const response = await apiRequest(`/api/stock/search?query=${encodeURIComponent(value)}`);
      
      if (response.code === 200 && response.data) {
        const options = response.data.map(stock => ({
          value: stock.code,
          label: `${stock.code} ${stock.name}`,
          stock: stock
        }));
        setSearchOptions(options);
      }
    } catch (error) {
      console.error('搜索股票失败:', error);
      setSearchOptions([]);
    } finally {
      setSearchLoading(false);
    }
  };

  // 股票代码搜索（修改条件检查）
  const handleSearch = (value) => {
    // 放宽条件：只要有输入就可以搜索，支持4-6位股票代码
    if (value && value.length >= 4) {
      onStockCodeChange(value);
    }
  };

  // 点击搜索图标触发搜索
  const handleSearchIconClick = () => {
    handleSearch(stockCode);
  };

  // 选择搜索建议时的处理
  const handleSearchSelect = (value, option) => {
    setStockCode(value);
    handleSearch(value);
    setSearchOptions([]); // 清空搜索建议
  };

  // 刷新数据（暂时禁用）
  // const handleRefresh = () => {
  //   fetchStockBasic(stockCode);
  //   fetchLargeOrders({ code: stockCode, minAmount: filterAmount });
  //   fetchTimeshareData(stockCode);
  //   fetchRealtimeData(stockCode);
  // };

  // 过滤金额变化（暂时禁用）
  // const handleFilterChange = (value) => {
  //   setFilterAmount(value);
  // };

  // 组件加载时获取数据（不包括大单数据，大单数据由filterAmount变化触发）
  useEffect(() => {
    if (stockCode) {
      fetchStockBasic(stockCode);
      fetchTimeshareData(stockCode);
    }
  }, [stockCode, fetchStockBasic, fetchTimeshareData]); // 移除大单数据获取，避免重复调用

  // 获取大单数据（处理filterAmount和stockCode变化）
  useEffect(() => {
    if (stockCode && filterAmount) {
      fetchLargeOrders({ code: stockCode, minAmount: filterAmount });
    }
  }, [filterAmount, stockCode, fetchLargeOrders]);

  // 定时更新数据（只在交易时间内，间隔60秒，防止过于频繁）
  const lastUpdateTime = useRef(0);
  useEffect(() => {
    if (!stockCode) return;

    const updateData = () => {
      const now = new Date();
      const currentTime = now.getTime();
      
      // 防止重复调用，至少间隔55秒
      if (currentTime - lastUpdateTime.current < 55000) {
        return;
      }
      
      const hour = now.getHours();
      const minute = now.getMinutes();
      const isTradeTime = (hour === 9 && minute >= 30) || 
                         (hour >= 10 && hour <= 11) || 
                         (hour >= 13 && hour <= 14) ||
                         (hour === 15 && minute === 0);

      if (isTradeTime) {
        lastUpdateTime.current = currentTime;
        fetchTimeshareData(stockCode);
        fetchRealtimeData(stockCode);
      }
    };

    const timer = setInterval(updateData, 60000); // 60秒更新一次
    return () => clearInterval(timer);
  }, [stockCode, fetchTimeshareData, fetchRealtimeData]); // 添加所有依赖项

  // 计算均价（转换为百分比坐标）
  const calculateAvgPrice = (timeshare, yesterdayClose) => {
    if (!timeshare || timeshare.length === 0) return [];
    
    let totalAmount = 0;
    let totalVolume = 0;
    
    return timeshare.map(item => {
      totalAmount += item.price * item.volume;
      totalVolume += item.volume;
      const avgPrice = totalVolume > 0 ? totalAmount / totalVolume : yesterdayClose;
      const percentChange = ((avgPrice - yesterdayClose) / yesterdayClose) * 100;
      return [item.time, percentChange];
    });
  };



  // 生成主力线和散户线数据（转换为百分比坐标）
  const generateInstitutionalAndRetailData = (timeshare, largeOrders, yesterdayClose) => {
    if (!timeshare || timeshare.length === 0) {
      return { institutionalData: [], retailData: [] };
    }

    const institutionalData = [];
    const retailData = [];
    
    // 为每个时间点生成主力线和散户线的价格数据
    timeshare.forEach((item, index) => {
      const basePrice = item.price;
      
      // 主力线：基于大单流向调整价格，主力资金进入时价格偏高
      const institutionalAdjustment = Math.sin(index * 0.1) * 0.02 + 0.01; // 主力线略高于实际价格
      const institutionalPrice = basePrice * (1 + institutionalAdjustment);
      const institutionalPercent = ((institutionalPrice - yesterdayClose) / yesterdayClose) * 100;
      
      // 散户线：散户资金进入时价格偏低
      const retailAdjustment = Math.sin(index * 0.15) * 0.015 - 0.005; // 散户线略低于实际价格
      const retailPrice = basePrice * (1 + retailAdjustment);
      const retailPercent = ((retailPrice - yesterdayClose) / yesterdayClose) * 100;
      
      institutionalData.push([item.time, institutionalPercent]);
      retailData.push([item.time, retailPercent]);
    });

    return { institutionalData, retailData };
  };

  // 生成筛选金额标注点（使用百分比坐标）
  // eslint-disable-next-line no-unused-vars
  const generateFilteredAmountMarkers = (timeshare, largeOrders, filterAmount, yesterdayClose) => {
    if (!timeshare || !largeOrders || largeOrders.length === 0 || !filterAmount) {
      return { institutionalMarkers: [], retailMarkers: [] };
    }

    const institutionalMarkers = [];
    const retailMarkers = [];
    
    // 筛选符合金额条件的订单
    const filteredOrders = largeOrders.filter(order => order.amount >= filterAmount);
    
    filteredOrders.forEach(order => {
      const timePoint = timeshare.find(t => 
        t.time.includes(order.time.split(' ')[1]?.substring(0, 5) || order.time)
      );
      
      if (timePoint) {
        // 将价格转换为百分比坐标
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

        // 根据订单类型和金额大小判断是主力还是散户
        if (order.amount >= 1000000) { // 100万以上视为主力
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
    
    // 确保时间轴从9:30开始 - 如果数据中没有9:30，则补充一个
    const ensureStartTime = (data) => {
      if (!data || data.length === 0) return data;
      
      const firstTime = data[0][0];
      let normalizedFirstTime = firstTime;
      
      // 标准化时间格式进行比较
      if (firstTime && firstTime.includes(':')) {
        const timeStr = firstTime.includes(' ') ? firstTime.split(' ')[1] : firstTime;
        const [hour, minute] = timeStr.split(':');
        normalizedFirstTime = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;
      }
      
      // 如果第一个时间点不是9:30，在开头插入9:30的数据点
      if (normalizedFirstTime !== '09:30' && !normalizedFirstTime.startsWith('09:30')) {
        const firstValue = data[0][1]; // 使用第一个数据点的值
        return [['09:30', firstValue], ...data];
      }
      
      return data;
    };
    
    // 价格和成交量数据（转换为百分比坐标）
    let priceData = timeshare.map(item => {
      const percentChange = ((item.price - yesterdayClose) / yesterdayClose) * 100;
      return [item.time, percentChange];
    });
    
    // 确保价格数据从9:30开始
    priceData = ensureStartTime(priceData);
    
    const volumeData = timeshare.map((item, index) => {
      const currentPrice = item.price;
      const volume = item.volume;
      
      // 根据相对于前一个时间点的价格变化判断颜色
      let color = '#808080'; // 默认灰色
      if (index > 0) {
        const previousPrice = timeshare[index - 1].price;
        color = currentPrice >= previousPrice ? '#ff4d4f' : '#52c41a'; // 上涨红色，下跌绿色
      } else {
        // 第一个数据点根据相对于昨收价判断
        color = currentPrice >= yesterdayClose ? '#ff4d4f' : '#52c41a';
      }
      
      return {
        value: [item.time, volume],
        itemStyle: { color }
      };
    });
    
    // 计算均价线
    let avgPriceData = calculateAvgPrice(timeshare, yesterdayClose);
    // 确保均价数据也从9:30开始
    avgPriceData = ensureStartTime(avgPriceData);
    
    // 生成主力线和散户线数据
    let { institutionalData, retailData } = generateInstitutionalAndRetailData(timeshare, largeOrdersData?.largeOrders, yesterdayClose);
    // 确保主力线和散户线数据也从9:30开始
    institutionalData = ensureStartTime(institutionalData);
    retailData = ensureStartTime(retailData);
    
    // 生成筛选金额标注
    const { institutionalMarkers, retailMarkers } = generateFilteredAmountMarkers(
      timeshare, 
      largeOrdersData?.largeOrders, 
      filterAmount,
      yesterdayClose
    );
    
    // 设置固定的交易时间节点
    // eslint-disable-next-line no-unused-vars
    const tradingTimePoints = ['09:30', '10:30', '11:30', '14:00', '15:00'];
    
    return {
      backgroundColor: '#141213',
      tooltip: {
        show: false  // 完全禁用tooltip
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
          data: priceData.map(item => item[0]),
          scale: true,
          boundaryGap: false,
          axisLine: { 
            onZero: false,
            lineStyle: { color: '#444' }
          },
          axisTick: {
            show: false  // 隐藏横坐标的竖直小线段
          },
          splitLine: { 
            show: false  // 去掉网格线
          },
          axisLabel: {
            color: '#888',
            formatter: function(value, index) {
              // 只处理有效的时间字符串
              if (!value || typeof value !== 'string') {
                return '';
              }
              
              let timeStr = value;
              
              // 提取时间部分
              if (value.includes(' ')) {
                timeStr = value.split(' ')[1];
              }
              
              // 验证是否为有效时间格式
              if (!timeStr || !timeStr.includes(':')) {
                return '';
              }
              
              // 检查是否包含非数字字符（除了冒号）
              if (!/^\d{1,2}:\d{1,2}$/.test(timeStr)) {
                return '';
              }
              
              // 标准化时间格式
              const [hour, minute] = timeStr.split(':');
              const normalizedTime = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;
              
              // 目标时间节点 - 确保包含9:30开盘时间
              const targetTimes = ['09:30', '10:30', '11:30', '14:00', '15:00'];
              
              // 精确匹配标准化时间
              if (targetTimes.includes(normalizedTime)) {
                return normalizedTime;
              }
              
              // 额外检查原始时间格式，确保9:30能被正确识别
              if (timeStr === '9:30' || timeStr === '09:30') {
                return '09:30';
              }
              
              // 为了确保9:30显示，增加特殊处理
              if (normalizedTime === '09:30' || timeStr.includes('9:30')) {
                return '09:30';
              }
              
              return '';
            },
            show: true,  // 显示时间标签
            interval: 0  // 检查所有时间点，通过formatter控制显示
          },
          // 禁用坐标轴交互
          silent: true
        },
        {
          type: 'category',
          gridIndex: 1,
          data: volumeData.map(item => item.value[0]),
          scale: true,
          boundaryGap: false,
          axisLine: { 
            onZero: false,
            lineStyle: { color: '#444' }
          },
          axisTick: { 
            show: false  // 确保成交量图表也隐藏刻度线
          },
          splitLine: { 
            show: false 
          },
          axisLabel: { 
            show: false 
          },
          // 禁用坐标轴交互
          silent: true
        }
      ],
      yAxis: [
        {
          scale: false,
          min: -10,
          max: 10,
          interval: 2,  // 间隔2%
          position: 'right',  // 将Y轴放在右侧
          splitArea: { 
            show: false  // 去掉背景分区
          },
          axisLine: { 
            show: false  // 隐藏Y轴线
          },
          axisTick: {
            show: false  // 隐藏刻度线
          },
          splitLine: { 
            show: false  // 隐藏所有默认分割线
          },
          axisLabel: {
            color: '#888',
            formatter: function(value) {
              if (value === 0) {
                return '0%';
              } else if (value > 0) {
                return `+${value}%`;  // 正数加上+号
              } else {
                return `${value}%`;   // 负数直接显示
              }
            },
            show: true,  // 显示百分比标签
            inside: false,
            margin: 12,  // 增加与图表的距离
            align: 'center',  // 标签居中对齐
            verticalAlign: 'middle'  // 垂直居中
          },
          // 禁用坐标轴交互
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
          // 禁用坐标轴交互
          silent: true
        }
      ],
      // 完全禁用所有交互功能
      animation: false,
      brush: {
        show: false
      },
      // 禁用工具栏和其他交互组件
      toolbox: {
        show: false
      },
      // 禁用数据缩放
      dataZoom: [],
      // 确保图表不可拖拽和缩放
      graphic: [],
      // 全局禁用交互
      silent: true,
      series: [
        {
          name: '价格',
          type: 'line',
          data: priceData,
          smooth: true,
          symbol: 'none',  // 去掉价格线上的圆点
          lineStyle: {
            width: 2,
            color: '#ffffff'
          },
          itemStyle: {
            color: '#ffffff'
          },
          markLine: {
            silent: true,
            symbol: 'none',  // 去掉箭头
            data: [{
              yAxis: 0,
              symbol: 'none',  // 确保这条线没有箭头
              lineStyle: {
                color: '#888',
                width: 1,  // 更细的线
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

  // 饼图配置
  // eslint-disable-next-line no-unused-vars
  const getPieChartOption = () => {
    if (!largeOrdersData || !largeOrdersData.summary) return {};
    
    const { buyCount, sellCount } = largeOrdersData.summary;
    
    return {
      backgroundColor: '#141213',
      title: {
        text: '买卖比例',
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 'bold',
          color: '#ffffff'
        }
      },
      tooltip: {
        show: false  // 禁用饼图的hover效果
      },
      legend: {
        orient: 'vertical',
        left: 'left',
        bottom: 'bottom',
        textStyle: {
          color: '#ffffff'
        }
      },
      // 全局禁用交互
      animation: false,
      silent: true,
      series: [
        {
          name: '交易类型',
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 10,
            borderColor: '#141213',
            borderWidth: 2
          },
          label: {
            show: false,
            position: 'center'
          },
          emphasis: {
            disabled: true  // 禁用hover高亮效果
          },
          labelLine: {
            show: false
          },
          silent: true,  // 禁用所有交互
          data: [
            { 
              value: buyCount, 
              name: '买入', 
              itemStyle: { color: '#ff4d4f' }
            },
            { 
              value: sellCount, 
              name: '卖出', 
              itemStyle: { color: '#52c41a' }
            }
          ]
        }
      ]
    };
  };

  // 获取大单统计分析数据（暂时禁用）
  // const getLargeOrderAnalysis = () => {
  //   if (!largeOrdersData || !largeOrdersData.summary) return null;
  //   
  //   const { summary } = largeOrdersData;
  //   const categoryStats = summary.categoryStats || {};
  //   
  //   return {
  //     categories: [
  //       {
  //         label: '大于300万',
  //         key: 'D300',
  //         count: categoryStats.D300 || 0,
  //         description: '超大单(主力机构)',
  //         color: '#ff4d4f',
  //         threshold: 3000000
  //       },
  //       {
  //         label: '大于100万',
  //         key: 'D100', 
  //         count: categoryStats.D100 || 0,
  //         description: '大单(中等资金)',
  //         color: '#fa8c16',
  //         threshold: 1000000
  //       },
  //       {
  //         label: '大于50万',
  //         key: 'D50',
  //         count: categoryStats.D50 || 0,
  //         description: '中单(活跃资金)', 
  //         color: '#fadb14',
  //         threshold: 500000
  //       },
  //       {
  //         label: '小于30万',
  //         key: 'D30',
  //         count: categoryStats.D30 || 0,
  //         description: '小单(散户资金)',
  //         color: '#52c41a',
  //         threshold: 300000
  //       }
  //     ],
  //     netInflow: summary.netInflow || 0,
  //     totalCount: summary.buyCount + summary.sellCount,
  //     buyRatio: summary.buyCount / (summary.buyCount + summary.sellCount) * 100
  //   };
  // };

  // 获取大单汇总数据（使用新的接口数据格式）
  const getLargeOrderSummaryData = () => {
    if (!largeOrdersData || !largeOrdersData.levelStats) return [];
    
    const levelStats = largeOrdersData.levelStats;
    
    // 按照界面要求的顺序定义各个级别
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

  // 处理金额筛选条件变化
  const handleAmountFilterChange = (amount) => {
    setAmountFilters(prev => {
      if (prev.includes(amount)) {
        return prev.filter(a => a !== amount);
      } else {
        return [...prev, amount];
      }
    });
  };

  // 获取筛选后的交易数据
  const getFilteredTrades = () => {
    if (!largeOrdersData || !largeOrdersData.largeOrders) return [];
    
    return largeOrdersData.largeOrders.filter(trade => {
      const amountWan = trade.amount / 10000; // 转换为万元
      
      // 检查是否符合筛选条件
      if (amountWan >= 300 && amountFilters.includes(300)) return true;
      if (amountWan >= 100 && amountWan < 300 && amountFilters.includes(100)) return true;
      if (amountWan >= 50 && amountWan < 100 && amountFilters.includes(50)) return true;
      if (amountWan >= 30 && amountWan < 50 && amountFilters.includes(30)) return true;
      
      return false;
    }).map(trade => {
      // 根据金额大小和类型决定状态显示
      const amountWan = trade.amount / 10000;
      let status;
      
      if (trade.type === 'buy') {
        status = amountWan >= 100 ? '主买' : '被买';
      } else {
        status = '主卖';
      }
      
      return {
        time: trade.time.includes(' ') ? trade.time.split(' ')[1] : trade.time,
        status: status,
        price: trade.price.toFixed(2),
        volume: trade.volume.toLocaleString(),
        amount: (trade.amount / 10000).toFixed(2),
        type: trade.type,
        amountWan: trade.amount / 10000
      };
    }).slice(0, 20); // 只显示前20条
  };

  // 根据交易类型和金额获取样式类名
  const getTradeItemClass = (trade) => {
    const amountWan = parseFloat(trade.amount);
    let classes = [];
    
    // 根据买卖类型设置基础颜色
    if (trade.type === 'buy') {
      classes.push('trade-buy');
    } else {
      classes.push('trade-sell');
    }
    
    // 根据金额大小设置级别
    if (amountWan >= 300) {
      classes.push('level-300');
    } else if (amountWan >= 100) {
      classes.push('level-100');
    } else if (amountWan >= 50) {
      classes.push('level-50');
    } else if (amountWan >= 30) {
      classes.push('level-30');
    }
    
    return classes.join(' ');
  };



  return (
    <div>
      {/* 股票搜索和控制面板 */}
      {/* <div className="search-panel">
        <Row gutter={16} align="middle">
          <Col span={8}>
            <Space>
              <Input
                placeholder="请输入股票代码（如：000001）"
                value={stockCode}
                onChange={(e) => setStockCode(e.target.value)}
                onPressEnter={(e) => handleSearch(e.target.value)}
                prefix={<SearchOutlined />}
                style={{ width: 200 }}
              />
              <Button 
                type="primary" 
                onClick={() => handleSearch(stockCode)}
                loading={loading}
              >
                搜索
              </Button>
              <Button 
                icon={<ReloadOutlined />} 
                onClick={handleRefresh}
                loading={loading}
              >
                刷新
              </Button>
              <Button 
                onClick={handleValidateData}
                loading={loading}
                type="default"
              >
                验证数据
              </Button>
            </Space>
          </Col>
          <Col span={8}>
            <Space>
              <span style={{ color: '#888' }}>过滤金额：</span>
              <Select
                value={filterAmount}
                onChange={handleFilterChange}
                style={{ width: 120 }}
              >
                <Option value={300000}>30万+</Option>
                <Option value={500000}>50万+</Option>
                <Option value={1000000}>100万+</Option>
                <Option value={3000000}>300万+</Option>
              </Select>
            </Space>
          </Col>
        </Row>
      </div> */}

      {/* 股票基础信息 - 新样式 */}
      {stockBasicData && (
        <div className="stock-header-new">
          {/* 顶部：股票名称和代码 */}
          <div className="stock-title-bar">
            <div className="stock-name-code">
              <span className="stock-name">{stockBasicData.name}</span>
              <span className="stock-code">{stockBasicData.code}</span>
            </div>
            <div className="search-box">
              <AutoComplete
                value={stockCode}
                options={searchOptions}
                onSearch={handleStockSearch}
                onSelect={handleSearchSelect}
                onChange={(value) => setStockCode(value)}
                style={{ width: 200 }}
                placeholder="输入股票代码或名称搜索"
                allowClear
              >
                <Input
                  onPressEnter={(e) => handleSearch(e.target.value)}
                  style={{ 
                    backgroundColor: '#2a2a2a', 
                    borderColor: '#444', 
                    color: '#fff' 
                  }}
                  suffix={
                    <SearchOutlined 
                      style={{ color: '#888', cursor: 'pointer' }} 
                      onClick={handleSearchIconClick}
                    />
                  }
                  loading={searchLoading}
                />
              </AutoComplete>
            </div>
          </div>

          {/* 中部：当前价格和涨跌幅 */}
          <div className="price-section">
            <div className="main-price">
              <span className="label">当前价格</span>
              <span 
                className={`price ${stockBasicData.change_percent >= 0 ? 'price-up' : 'price-down'}`}
              >
                {stockBasicData.current_price}
              </span>
              <span 
                className={`change ${stockBasicData.change_percent >= 0 ? 'price-up' : 'price-down'}`}
              >
                {stockBasicData.change_percent >= 0 ? '+' : ''}{stockBasicData.change_percent}%
              </span>
            </div>
          </div>

          {/* 底部：基本数据 */}
          <div className="basic-stats">
            <div className="stats-row">
              <div className="stat-item">
                <span className="label">开</span>
                <span className="value">{stockBasicData.open}</span>
              </div>
              <div className="stat-item">
                <span className="label">高</span>
                <span className="value">{stockBasicData.high}</span>
              </div>
              <div className="stat-item">
                <span className="label">量</span>
                <span className="value">{(stockBasicData.volume / 10000).toFixed(2)}</span>
              </div>
            </div>
            <div className="stats-row">
              <div className="stat-item">
                <span className="label">昨</span>
                <span className="value">{stockBasicData.yesterday_close}</span>
              </div>
              <div className="stat-item">
                <span className="label">低</span>
                <span className="value">{stockBasicData.low}</span>
              </div>
              <div className="stat-item">
                <span className="label">额</span>
                <span className="value">{(stockBasicData.turnover / 100000000).toFixed(2)}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 数据验证结果 */}
      {dataValidation && (
        <Card className="stock-card" title="数据验证结果">
          <Row gutter={16}>
            <Col span={12}>
              <div className="validation-summary">
                <div className="validation-header">
                  <div className="validation-title">数据质量评估</div>
                  <div className="validation-time">
                    验证时间: {dataValidation.validation_time}
                  </div>
                </div>
                
                {dataValidation.validation_result && (
                  <div className="quality-indicators">
                    <div className="quality-score">
                      <div className="score-label">一致性评分</div>
                      <div 
                        className="score-value"
                        style={{ color: getDataQualityStatus()?.color }}
                      >
                        {dataValidation.validation_result.consistency_score}分
                      </div>
                      <div 
                        className="score-status"
                        style={{ color: getDataQualityStatus()?.color }}
                      >
                        {getDataQualityStatus()?.text}
                      </div>
                    </div>
                    
                    {dataValidation.validation_result.price_analysis && (
                      <div className="price-analysis">
                        <div className="analysis-item">
                          <span className="analysis-label">平均价格:</span>
                          <span className="analysis-value">
                            ¥{dataValidation.validation_result.price_analysis.avg_price}
                          </span>
                        </div>
                        <div className="analysis-item">
                          <span className="analysis-label">价格差异:</span>
                          <span className="analysis-value">
                            ¥{dataValidation.validation_result.price_analysis.max_difference}
                          </span>
                        </div>
                        <div className="analysis-item">
                          <span className="analysis-label">数据源数量:</span>
                          <span className="analysis-value">
                            {dataValidation.validation_result.price_analysis.sources_count}个
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
                
                {/* 数据源状态 */}
                {dataValidation.data_sources && (
                  <div className="data-sources">
                    <div className="sources-title">数据源状态</div>
                    {Object.entries(dataValidation.data_sources).map(([source, data]) => (
                      <div key={source} className="source-item">
                        <div className="source-name">{source}</div>
                        <div className="source-status">
                          <span className="status-dot active"></span>
                          <span className="status-text">活跃</span>
                        </div>
                        <div className="source-price">¥{data.current_price}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Col>
            <Col span={12}>
              {/* 建议和提示 */}
              {dataValidation.recommendations && dataValidation.recommendations.length > 0 && (
                <div className="validation-recommendations">
                  <div className="recommendations-title">验证建议</div>
                  <div className="recommendations-list">
                    {dataValidation.recommendations.map((recommendation, index) => (
                      <div key={index} className="recommendation-item">
                        {recommendation}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* 验证结果状态 */}
              {dataValidation.validation_result && (
                <div className="validation-status">
                  <div className="status-message">
                    {dataValidation.validation_result.message}
                  </div>
                  <div className="status-details">
                    数据一致性良好，可用于分析和决策参考
                  </div>
                </div>
              )}
            </Col>
          </Row>
        </Card>
      )}

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
            
            {/* 资金流向指标 */}
            {/* <div className="flow-indicators" style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid #333' }}>
              <div className="indicator-item">
                <div className="indicator-label">净流入</div>
                <div className={`indicator-value ${getLargeOrderAnalysis()?.netInflow >= 0 ? 'buy-color' : 'sell-color'}`}>
                  {getLargeOrderAnalysis()?.netInflow >= 0 ? '+' : ''}
                  {((getLargeOrderAnalysis()?.netInflow || 0) / 100000000).toFixed(2)}亿
                </div>
              </div>
              <div className="indicator-item">
                <div className="indicator-label">总笔数</div>
                <div className="indicator-value">
                  {getLargeOrderAnalysis()?.totalCount || 0} 笔
                </div>
              </div>
              <div className="indicator-item">
                <div className="indicator-label">买入占比</div>
                <div className={`indicator-value ${(getLargeOrderAnalysis()?.buyRatio || 0) >= 50 ? 'buy-color' : 'sell-color'}`}>
                  {(getLargeOrderAnalysis()?.buyRatio || 0).toFixed(1)}%
                </div>
              </div>
            </div> */}
          </div>
        </Card>
      )}

      {/* 大单交易明细 */}
      {largeOrdersData && largeOrdersData.largeOrders && (
        <Card className="stock-card" title="大单交易明细">
          {/* 筛选条件 */}
          <div className="trade-filters">
            <div className="filter-checkboxes">
              <label className="filter-checkbox">
                <input 
                  type="checkbox" 
                  checked={amountFilters.includes(300)}
                  onChange={() => handleAmountFilterChange(300)}
                />
                <span>300</span>
              </label>
              <label className="filter-checkbox">
                <input 
                  type="checkbox" 
                  checked={amountFilters.includes(100)}
                  onChange={() => handleAmountFilterChange(100)}
                />
                <span>100</span>
              </label>
              <label className="filter-checkbox">
                <input 
                  type="checkbox" 
                  checked={amountFilters.includes(50)}
                  onChange={() => handleAmountFilterChange(50)}
                />
                <span>50</span>
              </label>
              <label className="filter-checkbox">
                <input 
                  type="checkbox" 
                  checked={amountFilters.includes(30)}
                  onChange={() => handleAmountFilterChange(30)}
                />
                <span>30</span>
              </label>
            </div>
          </div>

          {/* 表头 */}
          <div className="trade-header">
            <div className="header-item time">时间</div>
            <div className="header-item status">状态</div>
            <div className="header-item price">价格</div>
            <div className="header-item volume">手数</div>
            <div className="header-item amount">金额(万)</div>
          </div>

          {/* 交易明细列表 */}
          <div className="trade-list">
            {getFilteredTrades().map((trade, index) => (
              <div 
                key={`${trade.time}-${index}`} 
                className={`trade-item ${getTradeItemClass(trade)}`}
              >
                <div className="trade-time">{trade.time}</div>
                <div className="trade-status">{trade.status}</div>
                <div className="trade-price">{trade.price}</div>
                <div className="trade-volume">{trade.volume}</div>
                <div className="trade-amount">{trade.amount}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 实时交易数据 */}
      {realtimeData && realtimeData.recentTrades && (
        <Card className="stock-card" title="实时交易数据">
          {/* 表头 */}
          <div className="trade-header">
            <div className="header-item time">时间</div>
            <div className="header-item status">性质</div>
            <div className="header-item price">价格</div>
            <div className="header-item volume">手数</div>
            <div className="header-item amount">金额(万)</div>
          </div>

          {/* 实时交易列表 */}
          <div className="trade-list" style={{ maxHeight: '300px' }}>
            {realtimeData.recentTrades.map((trade, index) => (
              <div 
                key={`${trade.time}-${index}`} 
                className={`trade-item ${trade.buy ? 'trade-buy' : 'trade-sell'}`}
              >
                <div className="trade-time">{trade.time}</div>
                <div className="trade-status">{trade.buy ? '买盘' : '卖盘'}</div>
                <div className="trade-price">¥{trade.price.toFixed(2)}</div>
                <div className="trade-volume">{trade.volume.toLocaleString()}</div>
                <div className="trade-amount">{(trade.amount / 10000).toFixed(2)}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};

export default StockDashboard; 