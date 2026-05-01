import { atom } from 'jotai';
import { apiRequest, getEnvironmentInfo } from '../config/api.js';
import { alignTimeshareToTradingAxis } from '../pages/StockDashboard/utils/l2Analysis.js';
// import quote from '../mock/quote.json'


// 股票代码原子
const initCode =  new URLSearchParams(window.location.search).get('code') || '000001';
export const stockCodeAtom = atom(initCode);

const MARKET_HOLIDAYS = new Set([
  '2026-05-01',
]);

const formatLocalDate = (date) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
};

const isTradingDay = (date) => {
  const day = date.getDay();
  return day !== 0 && day !== 6 && !MARKET_HOLIDAYS.has(formatLocalDate(date));
};

// 当前看板只展示最新有效交易日
const getLastTradingDay = () => {
  const d = new Date();
  const now = new Date();

  if (now.getHours() < 9 || (now.getHours() === 9 && now.getMinutes() < 30)) {
    d.setDate(d.getDate() - 1);
  }

  while (!isTradingDay(d)) {
    d.setDate(d.getDate() - 1);
  }

  return formatLocalDate(d);
};

export const selectedDateAtom = atom(getLastTradingDay());

// 股票基础数据原子
export const stockBasicDataAtom = atom(null);

// 大单数据原子`
export const largeOrdersDataAtom = atom(null);

// 分时图数据原子
export const timeshareDataAtom = atom(null);

// 题材与涨停池归纳
export const limitUpThemesAtom = atom(null);

// 实时交易数据原子
export const realtimeDataAtom = atom(null);

// 过滤金额原子
export const filterAmountAtom = atom(500000);

// 加载状态原子
export const loadingAtom = atom(false);

// 错误状态原子
export const errorAtom = atom(null);

// 数据验证相关原子
export const dataValidationAtom = atom(null);

// WebSocket 连接状态
export const wsConnectedAtom = atom(false);

// 封单监控数据
export const limitUpMonitorAtom = atom(null);

// 获取股票基础数据的异步原子（使用竞品接口）
export const fetchStockBasicAtom = atom(
  null,
  async (get, set, code) => {
    set(loadingAtom, true);
    set(errorAtom, null);
    
    try {
      const today = new Date().toISOString().split('T')[0];
      const data = await apiRequest(`/api/v1/base_info?code=${code}&dt=${today}`);
      if (data.success === true && data.data) {
        // 转换竞品接口格式为前端期望格式
        const baseInfo = data.data;
        const convertedData = {
          code: baseInfo.code,
          name: baseInfo.name,
          current_price: baseInfo.current_price,
          change_percent: baseInfo.change_percent,
          change_amount: baseInfo.change_amount,
          volume: Math.round(baseInfo.volume * 10000), // 转换万手为手
          turnover: Math.round(baseInfo.turnover * 100000000), // 转换亿元为元
          high: baseInfo.high,
          low: baseInfo.low,
          open: baseInfo.open,
          yesterday_close: baseInfo.yesterday_close,
          market_cap: baseInfo.market_cap,
          circulation_market_cap: baseInfo.circulation_market_cap,
          pe_ratio: baseInfo.pe_ratio,
          pb_ratio: baseInfo.pb_ratio,
          turnover_rate: baseInfo.turnover_rate,
          amplitude: baseInfo.amplitude,
          limit_up: baseInfo.limit_up,
          limit_down: baseInfo.limit_down,
          market_status: baseInfo.market_status,
          data_source: 'competitor_api'
        };
        set(stockBasicDataAtom, convertedData);
      } else {
        set(errorAtom, data.message || '获取基础数据失败');
      }
    } catch (error) {
      set(errorAtom, `获取股票数据失败: ${error.message}`);
    } finally {
      set(loadingAtom, false);
    }
  }
);

// 获取大单数据的异步原子（使用竞品接口）
export const fetchLargeOrdersAtom = atom(
  null,
  async (get, set, { code, minAmount }) => {
    set(loadingAtom, true);
    set(errorAtom, null);
    
    try {
      const today = new Date().toISOString().split('T')[0];
      // 获取大单统计数据和大单明细（设置更长的超时时间，因为需要分析大量成交明细）
      const [statsData, dadanData] = await Promise.all([
        apiRequest(`/api/v1/dadantongji?code=${code}&dt=${today}`, { timeout: 60000 }), // 60秒
        apiRequest(`/api/v1/dadan?code=${code}&dt=${today}`, { timeout: 60000 }) // 60秒
      ]);
      
      // 大单统计和大单明细都使用 success: true 格式
      if (statsData.success === true && dadanData.success === true) {
        // 转换统计数据格式 - 适配新的后端数据结构
        const statsArray = statsData.statistics || [];
        const dadanResult = dadanData.data;
        const orders = dadanResult.dadan_list || [];
        
        // 将统计数组转换为映射对象，便于查找
        const statsMap = {};
        statsArray.forEach(stat => {
          const level = stat.level;
          statsMap[level] = {
            buy_count: stat.buy_count || 0,
            sell_count: stat.sell_count || 0,
            net_count: stat.net_count || 0
          };
        });
        
        // 合并数据为前端期望的格式
        const combinedData = {
          summary: {
            buyCount: (statsMap['大于300万']?.buy_count || 0) + (statsMap['大于100万']?.buy_count || 0) + 
                     (statsMap['大于50万']?.buy_count || 0) + (statsMap['大于30万']?.buy_count || 0),
            sellCount: (statsMap['大于300万']?.sell_count || 0) + (statsMap['大于100万']?.sell_count || 0) + 
                      (statsMap['大于50万']?.sell_count || 0) + (statsMap['大于30万']?.sell_count || 0),
            totalAmount: 0, // 暂时设为0，因为后端没有返回金额汇总
            netInflow: 0,   // 暂时设为0，因为后端没有返回净流入
            categoryStats: {
              D300: (statsMap['大于300万']?.buy_count || 0) + (statsMap['大于300万']?.sell_count || 0),
              D100: (statsMap['大于100万']?.buy_count || 0) + (statsMap['大于100万']?.sell_count || 0),
              D50: (statsMap['大于50万']?.buy_count || 0) + (statsMap['大于50万']?.sell_count || 0),
              D30: (statsMap['大于30万']?.buy_count || 0) + (statsMap['大于30万']?.sell_count || 0)
            }
          },
          largeOrders: Array.isArray(orders) ? orders.map(order => ({
            time: order.time,
            type: order.status === '被买' || order.status === '主买' ? 'buy' : 'sell',
            price: parseFloat(order.price),
            volume: parseInt(order.volume),
            amount: parseFloat(order.amount) * 10000, // 万元转元
            category: order.category || determineCategory(parseFloat(order.amount) * 10000)
          })) : [],
          levelStats: {
            D300: {
              buy_count: statsMap['大于300万']?.buy_count || 0,
              sell_count: statsMap['大于300万']?.sell_count || 0,
              buy_amount: 0, // 后端暂未返回金额统计
              sell_amount: 0
            },
            D100: {
              buy_count: statsMap['大于100万']?.buy_count || 0,
              sell_count: statsMap['大于100万']?.sell_count || 0,
              buy_amount: 0, // 后端暂未返回金额统计
              sell_amount: 0
            },
            D50: {
              buy_count: statsMap['大于50万']?.buy_count || 0,
              sell_count: statsMap['大于50万']?.sell_count || 0,
              buy_amount: 0, // 后端暂未返回金额统计
              sell_amount: 0
            },
            D30: {
              buy_count: statsMap['大于30万']?.buy_count || 0,
              sell_count: statsMap['大于30万']?.sell_count || 0,
              buy_amount: 0, // 后端暂未返回金额统计
              sell_amount: 0
            },
            under_D30: {
              buy_count: statsMap['小于30万']?.buy_count || 0,
              sell_count: statsMap['小于30万']?.sell_count || 0,
              buy_amount: 0, // 后端暂未返回金额统计
              sell_amount: 0
            }
          }
        };
        
        set(largeOrdersDataAtom, combinedData);
        // 移除设置filterAmountAtom，避免循环调用
      } else {
        set(errorAtom, statsData.message || dadanData.message || '获取大单数据失败');
      }
    } catch (error) {
      set(errorAtom, `获取大单数据失败: ${error.message}`);
    } finally {
      set(loadingAtom, false);
    }
  }
);

// 帮助函数：根据金额确定类别
const determineCategory = (amount) => {
  if (amount >= 3000000) return 'D300';
  if (amount >= 1000000) return 'D100';
  if (amount >= 500000) return 'D50';
  if (amount >= 300000) return 'D30';
  return 'under_D30';
};

// 获取分时图数据的异步原子（使用竞品接口）
export const fetchTimeshareDataAtom = atom(
  null,
  async (get, set, code) => {
    console.log('🔄 fetchTimeshareDataAtom 被调用，股票代码:', code);
    set(loadingAtom, true);
    set(errorAtom, null);
    
    try {
      const today = new Date().toISOString().split('T')[0];
      console.log('📅 请求日期:', today);
      
      // 注释掉实际的 API 调用，直接使用 mock 数据
     const quote = await apiRequest(`/api/v1/quote?code=${code}&dt=${today}`)
     console.log(quote,'quote;;;;;')
      
      console.log('📊 Mock 数据结构:', Object.keys(quote.data || {}));
      console.log('📊 Mock 数据样本:', {
        fenshi: quote.data?.fenshi?.slice(0, 3),
        zhuli: quote.data?.zhuli?.slice(0, 3),
        sanhu: quote.data?.sanhu?.slice(0, 3),
        volume: quote.data?.volume?.slice(0, 3)
      });
      
      // 通过mock 数据展示 
      set(timeshareDataAtom, quote.data);
      console.log('✅ Mock 数据已设置到 timeshareDataAtom');
      
      // if (data.success === true && data.data) {
      //   // 转换为前端期望的格式
      //   const quoteData = data.data;
        
      //   // 处理分时数据
      //   const timeshareArray = Array.isArray(quoteData.timeshare) ? quoteData.timeshare : [];
        
      //   const timeshareData = {
      //     timeshare: timeshareArray.map(item => ({
      //       time: item.time,
      //       price: parseFloat(item.price),
      //       volume: parseInt(item.volume || 0)
      //     })),
      //     statistics: {
      //       current_price: parseFloat(quoteData.current_price || 0),
      //       yesterdayClose: parseFloat(quoteData.yesterday_close || 0),
      //       change_percent: parseFloat(quoteData.change_percent || 0),
      //       change_amount: parseFloat(quoteData.change_amount || 0),
      //       high: parseFloat(quoteData.high || 0),
      //       low: parseFloat(quoteData.low || 0),
      //       volume: parseInt(quoteData.volume || 0),
      //       turnover: parseFloat(quoteData.turnover || 0)
      //     }
      //   };
        
      //   set(timeshareDataAtom, timeshareData);
      // } else {
      //   set(errorAtom, data.message || '获取分时数据失败');
      // }
    } catch (error) {
      console.error('❌ fetchTimeshareDataAtom 错误:', error);
      set(errorAtom, `获取分时图数据失败: ${error.message}`);
    } finally {
      set(loadingAtom, false);
      console.log('🏁 fetchTimeshareDataAtom 执行完成');
    }
  }
);

// 获取实时交易数据的异步原子（使用竞品大单接口）
export const fetchRealtimeDataAtom = atom(
  null,
  async (get, set, code) => {
    set(loadingAtom, true);
    set(errorAtom, null);
    
    try {
      const today = new Date().toISOString().split('T')[0];
      const data = await apiRequest(`/api/v1/dadan?code=${code}&dt=${today}`, { timeout: 60000 }); // 60秒
      
      if (data.success === true && data.data) {
        // 转换为前端期望的实时交易格式
        const dadanResult = data.data;
        const orders = dadanResult.dadan_list || [];
        
        const realtimeData = {
          recentTrades: Array.isArray(orders) ? orders.slice(0, 20).map(order => ({
            time: order.time,
            buy: order.status === '被买' || order.status === '主买' || order.is_buy,
            price: parseFloat(order.price),
            volume: parseInt(order.volume),
            amount: parseFloat(order.amount) * 10000, // 万元转元
            order_size: determineOrderSize(parseFloat(order.amount) * 10000)
          })) : []
        };
        
        set(realtimeDataAtom, realtimeData);
      } else {
        set(errorAtom, data.message || '获取实时数据失败');
      }
    } catch (error) {
      set(errorAtom, `获取实时交易数据失败: ${error.message}`);
    } finally {
      set(loadingAtom, false);
    }
  }
); 

// 帮助函数：根据金额确定订单大小
const determineOrderSize = (amount) => {
  if (amount >= 3000000) return 'large';
  if (amount >= 1000000) return 'medium';
  return 'small';
};

// 帮助函数：根据万元金额确定类别
const determineCategoryFromWan = (amountWan) => {
  if (amountWan >= 300) return 'D300';
  if (amountWan >= 100) return 'D100';
  if (amountWan >= 50) return 'D50';
  if (amountWan >= 30) return 'D30';
  return 'under_D30';
};

/**
 * 解析 L2 Dashboard 返回数据并更新 atoms
 * 供 HTTP 轮询和 WebSocket 推送共用
 */
export const applyL2DashboardData = (set, data) => {
  if (!data?.success || !data?.data) return false;

  const d = data.data;

  // 1. 分时图
  const timeshare = d.timeshare || [];
  const alignedTimeshare = alignTimeshareToTradingAxis(timeshare);
  set(timeshareDataAtom, {
    timeAxis: alignedTimeshare.axis,
    fenshi: alignedTimeshare.fenshi,
    volume: alignedTimeshare.volume,
    zhuli: [],
    sanhu: [],
    big_map: d.big_map || {},
    order_book: d.order_book || null,
    base_info: {
      prevClosePrice: d.stock_info.yesterday_close,
      openPrice: d.stock_info.open,
      highPrice: d.stock_info.high,
      lowPrice: d.stock_info.low,
    },
  });

  // 2. 大单数据
  const orders = d.large_orders || d.orders || [];
  const stats = d.statistics || {};
  const buyCount = orders.filter(o => o.direction === '被买' || o.direction === '主买').length;
  const sellCount = orders.filter(o => o.direction === '被卖' || o.direction === '主卖').length;
  const neutralCount = orders.length - buyCount - sellCount;
  const totalAmount = orders.reduce((sum, o) => sum + (o.amount || 0), 0);
  const buyAmount = orders.filter(o => o.direction === '被买' || o.direction === '主买').reduce((sum, o) => sum + (o.amount || 0), 0);
  const netInflow = buyAmount - (totalAmount - buyAmount);

  set(largeOrdersDataAtom, {
    summary: { buyCount, sellCount, neutralCount, totalAmount, netInflow },
    largeOrders: orders.map(order => ({
      time: order.time,
      type: (order.direction === '被买' || order.direction === '主买') ? 'buy' : 'sell',
      price: order.price,
      volume: order.volume_lots,
      amount: order.amount * 10000,
      category: determineCategoryFromWan(order.amount),
      direction: order.direction,
    })),
    levelStats: {
      D300: stats.above_300,
      D100: stats.above_100,
      D50: stats.above_50,
      D30: stats.above_30,
      under_D30: stats.below_30,
    },
  });

  // 3. 股票基础数据
  set(stockBasicDataAtom, d.stock_info);

  // 4. 封单监控
  if (d.limit_up_monitor) {
    set(limitUpMonitorAtom, d.limit_up_monitor);
  }

  return true;
};

// 获取L2看板统一数据的异步原子
// 参数可以是 code 字符串，或 { code, dt } 对象
export const fetchL2DashboardAtom = atom(
  null,
  async (get, set, params) => {
    const code = typeof params === 'string' ? params : params.code;
    const dt = typeof params === 'string' ? get(selectedDateAtom) : (params.dt || get(selectedDateAtom));
    const simulate = typeof params === 'object' && params.simulate;
    const simulateTime = typeof params === 'object' ? params.simulateTime : null;
    set(loadingAtom, true);
    set(errorAtom, null);

    try {
      const query = new URLSearchParams({ code, dt });
      if (simulate && simulateTime) {
        query.set('simulate', '1');
        query.set('simulate_time', simulateTime);
      }
      const data = await apiRequest(`/api/v1/l2_dashboard?${query.toString()}`, { timeout: 45000 });

      if (!applyL2DashboardData(set, data)) {
        set(errorAtom, data.message || '获取L2看板数据失败');
      }
    } catch (error) {
      set(errorAtom, `获取L2看板数据失败: ${error.message}`);
    } finally {
      set(loadingAtom, false);
    }
  }
);

// 获取当前股票题材与当天涨停池归纳
export const fetchLimitUpThemesAtom = atom(
  null,
  async (get, set, code) => {
    const dt = get(selectedDateAtom);

    try {
      const data = await apiRequest(`/api/v1/limit_up_themes?code=${code}&dt=${dt}`, { timeout: 30000 });
      if (data.code === 200 && data.data) {
        set(limitUpThemesAtom, data.data);
      } else {
        set(limitUpThemesAtom, null);
      }
    } catch (error) {
      set(limitUpThemesAtom, {
        error: error.message,
        themes: [],
      });
    }
  }
);

// 环境信息原子 (用于调试)
export const environmentInfoAtom = atom(getEnvironmentInfo()); 