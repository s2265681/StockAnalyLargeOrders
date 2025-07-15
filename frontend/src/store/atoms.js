import { atom } from 'jotai';
import { apiRequest, getEnvironmentInfo } from '../config/api.js';

// 股票代码原子
export const stockCodeAtom = atom('603001');

// 股票基础数据原子
export const stockBasicDataAtom = atom(null);

// 大单数据原子
export const largeOrdersDataAtom = atom(null);

// 分时图数据原子
export const timeshareDataAtom = atom(null);

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
      // 获取大单统计数据和大单明细
      const [statsData, dadanData] = await Promise.all([
        apiRequest(`/api/v1/dadantongji?code=${code}&dt=${today}`),
        apiRequest(`/api/v1/dadan?code=${code}&dt=${today}`)
      ]);
      
      // 大单统计使用 code: 0 格式，大单明细使用 success: true 格式
      if (statsData.code === 0 && dadanData.success === true) {
        // 转换统计数据格式
        const stats = statsData.data;
        const dadanResult = dadanData.data;
        const orders = dadanResult.dadan_list || [];
        
        // 合并数据为前端期望的格式
        const combinedData = {
          summary: {
            buyCount: parseInt(stats.buy_nums_300 || 0) + parseInt(stats.buy_nums_100 || 0) + parseInt(stats.buy_nums_50 || 0) + parseInt(stats.buy_nums_30 || 0),
            sellCount: parseInt(stats.sell_nums_300 || 0) + parseInt(stats.sell_nums_100 || 0) + parseInt(stats.sell_nums_50 || 0) + parseInt(stats.sell_nums_30 || 0),
            totalAmount: (parseFloat(stats.total_buy_amount || 0) + parseFloat(stats.total_sell_amount || 0)) * 10000,
            netInflow: (parseFloat(stats.total_buy_amount || 0) - parseFloat(stats.total_sell_amount || 0)) * 10000,
            categoryStats: {
              D300: parseInt(stats.buy_nums_300 || 0) + parseInt(stats.sell_nums_300 || 0),
              D100: parseInt(stats.buy_nums_100 || 0) + parseInt(stats.sell_nums_100 || 0),
              D50: parseInt(stats.buy_nums_50 || 0) + parseInt(stats.sell_nums_50 || 0),
              D30: parseInt(stats.buy_nums_30 || 0) + parseInt(stats.sell_nums_30 || 0)
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
              buy_count: parseInt(stats.buy_nums_300 || 0),
              sell_count: parseInt(stats.sell_nums_300 || 0),
              buy_amount: parseFloat(stats.buy_amount_300 || 0),
              sell_amount: parseFloat(stats.sell_amount_300 || 0)
            },
            D100: {
              buy_count: parseInt(stats.buy_nums_100 || 0),
              sell_count: parseInt(stats.sell_nums_100 || 0),
              buy_amount: parseFloat(stats.buy_amount_100 || 0),
              sell_amount: parseFloat(stats.sell_amount_100 || 0)
            },
            D50: {
              buy_count: parseInt(stats.buy_nums_50 || 0),
              sell_count: parseInt(stats.sell_nums_50 || 0),
              buy_amount: parseFloat(stats.buy_amount_50 || 0),
              sell_amount: parseFloat(stats.sell_amount_50 || 0)
            },
            D30: {
              buy_count: parseInt(stats.buy_nums_30 || 0),
              sell_count: parseInt(stats.sell_nums_30 || 0),
              buy_amount: parseFloat(stats.buy_amount_30 || 0),
              sell_amount: parseFloat(stats.sell_amount_30 || 0)
            },
            under_D30: {
              buy_count: parseInt(stats.buy_nums_below_30 || 0),
              sell_count: parseInt(stats.sell_nums_below_30 || 0),
              buy_amount: parseFloat(stats.buy_amount_below_30 || 0),
              sell_amount: parseFloat(stats.sell_amount_below_30 || 0)
            }
          }
        };
        
        set(largeOrdersDataAtom, combinedData);
        // 移除设置filterAmountAtom，避免循环调用
      } else {
        set(errorAtom, statsData.msg || dadanData.message || '获取大单数据失败');
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
    set(loadingAtom, true);
    set(errorAtom, null);
    
    try {
      const today = new Date().toISOString().split('T')[0];
      const data = await apiRequest(`/api/v1/quote?code=${code}&dt=${today}`);
      
      if (data.success === true && data.data) {
        // 转换为前端期望的格式
        const quoteData = data.data;
        
        // 处理分时数据
        const timeshareArray = Array.isArray(quoteData.timeshare) ? quoteData.timeshare : [];
        
        const timeshareData = {
          timeshare: timeshareArray.map(item => ({
            time: item.time,
            price: parseFloat(item.price),
            volume: parseInt(item.volume || 0)
          })),
          statistics: {
            current_price: parseFloat(quoteData.current_price || 0),
            yesterdayClose: parseFloat(quoteData.yesterday_close || 0),
            change_percent: parseFloat(quoteData.change_percent || 0),
            change_amount: parseFloat(quoteData.change_amount || 0),
            high: parseFloat(quoteData.high || 0),
            low: parseFloat(quoteData.low || 0),
            volume: parseInt(quoteData.volume || 0),
            turnover: parseFloat(quoteData.turnover || 0)
          }
        };
        
        set(timeshareDataAtom, timeshareData);
      } else {
        set(errorAtom, data.message || '获取分时数据失败');
      }
    } catch (error) {
      set(errorAtom, `获取分时图数据失败: ${error.message}`);
    } finally {
      set(loadingAtom, false);
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
      const data = await apiRequest(`/api/v1/dadan?code=${code}&dt=${today}`);
      
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

// 验证股票数据的异步原子
export const validateStockDataAtom = atom(
  null,
  async (get, set, code) => {
    set(loadingAtom, true);
    set(errorAtom, null);
    
    try {
      const data = await apiRequest(`/api/stock/validate?code=${code}`);
      
      if (data.code === 200) {
        set(dataValidationAtom, data.data);
      } else {
        set(errorAtom, data.message || '数据验证失败');
      }
    } catch (error) {
      set(errorAtom, `数据验证失败: ${error.message}`);
    } finally {
      set(loadingAtom, false);
    }
  }
);

// 环境信息原子 (用于调试)
export const environmentInfoAtom = atom(getEnvironmentInfo()); 