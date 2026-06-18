import { atom } from 'jotai';
import { apiRequest, getEnvironmentInfo } from '../config/api.js';
import {
  alignTimeshareToTradingAxis,
  buildTimeshareBaseInfo,
  buildTradingTimeAxis,
  isSameStockCode,
  isTimesharePriceStale,
  sliceL2DataByTime,
} from '../pages/StockDashboard/utils/l2Analysis.js';
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
export const getLatestTradingDay = () => {
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

/** 按交易日偏移，dateStr 格式 YYYY-MM-DD，delta 为交易日个数 */
export const offsetTradingDay = (dateStr, delta) => {
  const [y, m, d] = dateStr.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  let remaining = Math.abs(delta);
  const step = delta > 0 ? 1 : -1;
  while (remaining > 0) {
    date.setDate(date.getDate() + step);
    if (isTradingDay(date)) remaining -= 1;
  }
  return formatLocalDate(date);
};

/** 从最新交易日往前数 lookbackDays 个交易日（含当天） */
export const getMinTradingDay = (lookbackDays = 5) => {
  let date = getLatestTradingDay();
  for (let i = 1; i < lookbackDays; i += 1) {
    date = offsetTradingDay(date, -1);
  }
  return date;
};

export const STOCK_DASHBOARD_MAX_TRADING_DAYS = 5;

export const selectedDateAtom = atom(getLatestTradingDay());

// 股票基础数据原子
export const stockBasicDataAtom = atom(null);

// 大单数据原子
export const largeOrdersDataAtom = atom(null);

// 分时图数据原子
export const timeshareDataAtom = atom(null);

// 同花顺资金分时数据（超大单/大单/小单流入流出）
export const moneyflowAtom = atom(null);

// 题材与涨停池归纳
export const limitUpThemesAtom = atom(null);

// 实时交易数据原子
export const realtimeDataAtom = atom(null);

// 过滤金额原子
export const filterAmountAtom = atom(500000);

// 加载状态原子（页面级，仅首次拉取分时等关键数据时使用）
export const loadingAtom = atom(false);

// 分时图专用加载态，避免与大单/基础信息请求共用 loadingAtom 导致图表闪烁
export const timeshareLoadingAtom = atom(false);

// 错误状态原子
export const errorAtom = atom(null);

// WebSocket 连接状态
export const wsConnectedAtom = atom(false);

// 封单监控数据
export const limitUpMonitorAtom = atom(null);

// 获取股票基础数据的异步原子（使用竞品接口）
export const fetchStockBasicAtom = atom(
  null,
  async (get, set, code) => {
    set(errorAtom, null);

    try {
      const dt = get(selectedDateAtom);
      const data = await apiRequest(`/api/v1/base_info?code=${code}&dt=${dt}`);
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

// 帮助函数：根据金额（元）确定类别
const determineCategory = (amount) => {
  if (amount >= 3000000) return 'D300';
  if (amount >= 1000000) return 'D100';
  if (amount >= 500000) return 'D50';
  if (amount >= 300000) return 'D30';
  return 'under_D30';
};

// 帮助函数：根据万元金额确定类别
const determineCategoryFromWan = (amountWan) => {
  return determineCategory(amountWan * 10000);
};

const mapOrdersPayload = (ordersPayload) => {
  const orders = ordersPayload.large_orders || ordersPayload.orders || [];
  const stats = ordersPayload.statistics || {};
  const buyCount = orders.filter(o => o.direction === '被买' || o.direction === '主买').length;
  const sellCount = orders.filter(o => o.direction === '被卖' || o.direction === '主卖').length;
  const neutralCount = orders.length - buyCount - sellCount;
  const totalAmount = orders.reduce((sum, o) => sum + (o.amount || 0), 0);
  const buyAmount = orders
    .filter(o => o.direction === '被买' || o.direction === '主买')
    .reduce((sum, o) => sum + (o.amount || 0), 0);

  return {
    summary: {
      buyCount,
      sellCount,
      neutralCount,
      totalAmount,
      netInflow: buyAmount - (totalAmount - buyAmount),
    },
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
    big_map: ordersPayload.big_map || {},
  };
};

const applyOrdersPayload = (set, ordersPayload, requestedCode) => {
  if (!ordersPayload) return;
  const mapped = mapOrdersPayload(ordersPayload);
  set(largeOrdersDataAtom, {
    summary: mapped.summary,
    largeOrders: mapped.largeOrders,
    levelStats: mapped.levelStats,
  });
  if (Object.keys(mapped.big_map).length === 0) return;
  set(timeshareDataAtom, (prev) => {
    if (!prev?.base_info?.code || !isSameStockCode(prev.base_info.code, requestedCode)) {
      return prev;
    }
    return { ...prev, big_map: { ...prev.big_map, ...mapped.big_map } };
  });
};

const applyTimesharePayload = (set, timeshareResp, requestedCode, {
  moneyFlow = null,
  bigMap = {},
  skipBasic = false,
} = {}) => {
  const d = timeshareResp.data;
  const timeshare = d.timeshare || [];
  const aligned = alignTimeshareToTradingAxis(timeshare);

  set(timeshareDataAtom, {
    timeAxis: aligned.axis,
    fenshi: aligned.fenshi,
    volume: aligned.volume,
    zhuli: [],
    sanhu: [],
    big_map: bigMap,
    order_book: d.order_book || null,
    session_snapshot: d.session_snapshot || null,
    money_flow: moneyFlow,
    base_info: buildTimeshareBaseInfo(d.stock_info, requestedCode),
  });

  if (d.stock_info && !skipBasic) {
    set(stockBasicDataAtom, {
      ...d.stock_info,
      current_price: d.stock_info.current_price ?? d.stock_info.price,
      yesterday_close: d.stock_info.yesterday_close ?? d.stock_info.pre_close,
    });
  }
};

const applyStockBasicPayload = (set, basicData, requestedCode) => {
  if (!basicData) return;
  const code = basicData.code ?? requestedCode;
  set(stockBasicDataAtom, {
    ...basicData,
    code,
    current_price: basicData.current_price ?? basicData.price,
    yesterday_close: basicData.yesterday_close ?? basicData.pre_close,
  });
  set(timeshareDataAtom, (prev) => {
    if (!prev?.base_info?.code || !isSameStockCode(prev.base_info.code, requestedCode)) {
      return prev;
    }
    return {
      ...prev,
      base_info: buildTimeshareBaseInfo({
        code,
        yesterday_close: basicData.yesterday_close ?? basicData.pre_close,
        open: basicData.open,
        high: basicData.high,
        low: basicData.low,
      }, requestedCode, prev.base_info),
    };
  });
};

// 帮助函数：根据金额确定订单大小标签
const determineOrderSize = (amount) => {
  if (amount >= 3000000) return 'large';
  if (amount >= 1000000) return 'medium';
  return 'small';
};

// 获取分时图数据的异步原子（使用竞品接口）
export const fetchTimeshareDataAtom = atom(
  null,
  async (get, set, code) => {
    set(loadingAtom, true);
    set(errorAtom, null);

    try {
      const today = new Date().toISOString().split('T')[0];
      const quote = await apiRequest(`/api/v1/quote?code=${code}&dt=${today}`);
      set(timeshareDataAtom, quote.data);
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

/**
 * 解析 L2 Dashboard 返回数据并更新 atoms
 * 供 HTTP 轮询和 WebSocket 推送共用
 */
export const applyL2DashboardData = (set, data, cutoffTime, moneyFlow, expectedCode) => {
  if (!data?.success || !data?.data) return false;

  const d = data.data;
  const responseCode = d.stock_info?.code ?? expectedCode;
  if (expectedCode && responseCode && !isSameStockCode(expectedCode, responseCode)) {
    return false;
  }

  // 1. 分时图
  const timeshare = d.timeshare || [];
  const alignedTimeshare = alignTimeshareToTradingAxis(timeshare);

  // 资金流切片：moneyFlow 数组按分钟排列（从 09:31 开始），根据 cutoffTime 截断
  let slicedMoneyFlow = moneyFlow || d.money_flow || null;
  if (slicedMoneyFlow && cutoffTime) {
    const axis = buildTradingTimeAxis(); // 09:30, 09:31, ..., 15:00
    const cutoff = String(cutoffTime).slice(0, 5);
    // 资金流数据从 09:31 开始，axis[1] 对应 moneyFlow[0]
    const cutoffIdx = axis.indexOf(cutoff);
    if (cutoffIdx > 0) {
      const sliceLen = cutoffIdx; // axis[1]->mf[0], axis[cutoffIdx]->mf[cutoffIdx-1]
      const sliceArr = (arr) => Array.isArray(arr) ? arr.slice(0, sliceLen) : arr;
      slicedMoneyFlow = {
        zhuli: sliceArr(slicedMoneyFlow.zhuli),
        sanhu: sliceArr(slicedMoneyFlow.sanhu),
        chaoda: sliceArr(slicedMoneyFlow.chaoda),
        dadan: sliceArr(slicedMoneyFlow.dadan),
        zhongdan: sliceArr(slicedMoneyFlow.zhongdan),
        chaoda_delta: sliceArr(slicedMoneyFlow.chaoda_delta),
        sanhu_delta: sliceArr(slicedMoneyFlow.sanhu_delta),
      };
    }
  }

  set(timeshareDataAtom, {
    timeAxis: alignedTimeshare.axis,
    fenshi: alignedTimeshare.fenshi,
    volume: alignedTimeshare.volume,
    zhuli: [],
    sanhu: [],
    big_map: d.big_map || {},
    order_book: d.order_book || null,
    session_snapshot: d.session_snapshot ?? null,
    money_flow: slicedMoneyFlow,
    base_info: buildTimeshareBaseInfo(d.stock_info, expectedCode),
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

  // 3. 股票基础数据（与分时同源，避免 header 走实时 base_info 接口）
  if (d.stock_info) {
    set(stockBasicDataAtom, {
      ...d.stock_info,
      current_price: d.stock_info.current_price ?? d.stock_info.price,
      yesterday_close: d.stock_info.yesterday_close ?? d.stock_info.pre_close,
    });
  }

  // 4. 封单监控
  if (d.limit_up_monitor) {
    set(limitUpMonitorAtom, d.limit_up_monitor);
  }

  // 5. 同花顺资金分时
  if (d.moneyflow) {
    set(moneyflowAtom, d.moneyflow);
  }

  return true;
};

// 获取L2看板统一数据的异步原子
// 普通模式：分时 / 大单 / 资金流 三接口并行，分时先到先渲染，大单与资金流后续增量合并。
// 参数可以是 code 字符串，或 { code, dt } 对象（simulate/simulateTime 仍走全量接口）
export const fetchL2DashboardAtom = atom(
  null,
  async (get, set, params) => {
    const code = typeof params === 'string' ? params : params.code;
    const requestedCode = code;
    const dt = typeof params === 'string' ? get(selectedDateAtom) : (params.dt || get(selectedDateAtom));
    const isStale = () => !isSameStockCode(get(stockCodeAtom), requestedCode);
    const simulate = typeof params === 'object' && params.simulate;
    const simulateTime = typeof params === 'object' ? params.simulateTime : null;
    const isInitialLoad = !get(timeshareDataAtom);
    set(errorAtom, null);
    if (isInitialLoad) {
      set(loadingAtom, true);
      set(timeshareLoadingAtom, true);
    }

    // 模拟回放 / 有 simulate_time 参数 → 仍走全量接口（前端切片用）
    if (simulate && simulateTime) {
      try {
        const query = new URLSearchParams({ code, dt, simulate: '1', simulate_time: simulateTime });
        const data = await apiRequest(`/api/v1/l2_dashboard?${query.toString()}`, { timeout: 45000 });
        if (isStale()) return;
        if (!applyL2DashboardData(set, data, null, null, requestedCode)) {
          set(errorAtom, data.message || '获取L2看板数据失败');
        }
      } catch (error) {
        if (!isStale()) {
          set(errorAtom, `获取L2看板数据失败: ${error.message}`);
        }
      } finally {
        if (isInitialLoad && !isStale()) {
          set(loadingAtom, false);
          set(timeshareLoadingAtom, false);
        }
      }
      return;
    }

    // 普通模式：首屏 chart_only 先出图，行情 /api/stock/basic 后补；轮询走全量 l2_timeshare。
    const query = new URLSearchParams({ code, dt });
    let timeshareReady = false;
    const finishTimeshareLoading = () => {
      if (!isInitialLoad || isStale()) return;
      set(loadingAtom, false);
      set(timeshareLoadingAtom, false);
    };

    const ordersPromise = apiRequest(`/api/v1/l2_orders?${query}`, { timeout: 60000 })
      .catch(() => null)
      .then((ordersResp) => {
        if (isStale()) return;
        const ordersPayload = ordersResp?.success && ordersResp?.data ? ordersResp.data : null;
        applyOrdersPayload(set, ordersPayload, requestedCode);
      });

    let resolvedMoneyFlow = null;
    const moneyFlowPromise = apiRequest(`/api/v1/l2_money_flow?${query}`, { timeout: 30000 })
      .catch(() => null)
      .then((moneyFlowResp) => {
        if (isStale()) return;
        resolvedMoneyFlow = moneyFlowResp?.success ? moneyFlowResp.data : null;
      });

    const mergeMoneyFlow = () => {
      if (resolvedMoneyFlow && !isStale()) {
        set(timeshareDataAtom, (prev) => prev ? { ...prev, money_flow: resolvedMoneyFlow } : prev);
      }
    };

    try {
      if (isInitialLoad) {
        const chartQuery = new URLSearchParams({ code, dt, chart_only: '1' });
        const chartPromise = apiRequest(`/api/v1/l2_timeshare?${chartQuery}`, { timeout: 45000 });
        const quotePromise = apiRequest(`/api/stock/basic?code=${code}`, { timeout: 30000 })
          .catch(() => null);

        // 首屏只等分时 + 行情，大单 / 主力散户线后台合并
        const [timeshareResp, basicResp] = await Promise.all([
          chartPromise,
          quotePromise,
        ]);

        if (!isStale()) {
          const timeshareOk = timeshareResp?.success && timeshareResp?.data;
          if (timeshareOk) {
            const d = timeshareResp.data;
            if (!d.stock_info?.code || isSameStockCode(requestedCode, d.stock_info.code)) {
              applyTimesharePayload(set, timeshareResp, requestedCode, {
                moneyFlow: null,
                skipBasic: true,
              });
              timeshareReady = true;
              finishTimeshareLoading();
            }
          } else {
            set(errorAtom, '分时数据获取失败，请检查网络');
          }

          applyStockBasicPayload(set, basicResp?.data, requestedCode);

          const aligned = alignTimeshareToTradingAxis(timeshareResp?.data?.timeshare || []);
          const basicPrice = basicResp?.data?.current_price ?? basicResp?.data?.price;
          if (timeshareOk && isTimesharePriceStale(aligned.fenshi, basicPrice)) {
            void apiRequest(`/api/v1/l2_timeshare?${query}`, { timeout: 45000 })
              .catch(() => null)
              .then((retryResp) => {
                if (isStale() || !retryResp?.success || !retryResp?.data) return;
                const rd = retryResp.data;
                if (!rd.stock_info?.code || isSameStockCode(requestedCode, rd.stock_info.code)) {
                  applyTimesharePayload(set, retryResp, requestedCode, {
                    moneyFlow: null,
                    skipBasic: true,
                  });
                }
              });
          }
        }

        void Promise.all([ordersPromise, moneyFlowPromise]).then(() => mergeMoneyFlow());
        return;
      }

      const timeshareResp = await apiRequest(`/api/v1/l2_timeshare?${query}`, { timeout: 45000 });

      if (isStale()) return;

      const timeshareOk = timeshareResp?.success && timeshareResp?.data;
      if (!timeshareOk) {
        if (!isStale()) {
          set(errorAtom, '分时数据获取失败，请检查网络');
        }
        return;
      }

      const d = timeshareResp.data;
      if (d.stock_info?.code && !isSameStockCode(requestedCode, d.stock_info.code)) {
        return;
      }

      const moneyFlowFromTimeshare = d.money_flow || null;
      applyTimesharePayload(set, timeshareResp, requestedCode, {
        moneyFlow: moneyFlowFromTimeshare,
      });
      timeshareReady = true;
      finishTimeshareLoading();

      await Promise.all([ordersPromise, moneyFlowPromise]);
      mergeMoneyFlow();
    } catch (error) {
      if (!isStale()) {
        set(errorAtom, `获取L2看板数据失败: ${error.message}`);
      }
    } finally {
      if (isInitialLoad && !isStale() && !timeshareReady) {
        set(loadingAtom, false);
        set(timeshareLoadingAtom, false);
      }
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

/**
 * 前端模拟回放专用写原子
 * 直接接受完整看板数据 + 截止时间，本地切片后更新所有 atoms，不发任何网络请求
 * 用法：applySimulatedData({ fullData, cutoffTime: 'HH:MM' })
 */
export const applySimulatedDataAtom = atom(
  null,
  (get, set, { fullData, cutoffTime, moneyFlow }) => {
    const expectedCode = get(stockCodeAtom);
    const sliced = sliceL2DataByTime(fullData, cutoffTime);
    if (sliced) applyL2DashboardData(set, sliced, cutoffTime, moneyFlow, expectedCode);
  }
); 