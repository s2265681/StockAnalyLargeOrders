/* eslint-disable react-hooks/exhaustive-deps */
import React, { useEffect, useRef, useCallback, useMemo, useState } from 'react';
import { Radio, Switch, Tag } from 'antd';
import { useAtom } from 'jotai';
import StockBasicInfo from './components/StockBasicInfo';
import StockChart from './components/StockChart';
import HandicapLanguagePanel from './components/HandicapLanguagePanel';
import ThemeLimitUpPanel from './components/ThemeLimitUpPanel';
import StockOrderDetails from './components/StockOrderDetails';
import { buildTradingTimeAxis, alignTimeshareToTradingAxis } from './utils/l2Analysis';
import { stockWS } from '../../services/websocket';
import {
  stockCodeAtom,
  fetchL2DashboardAtom,
  fetchLimitUpThemesAtom,
  wsConnectedAtom,
  timeshareDataAtom,
  largeOrdersDataAtom,
  stockBasicDataAtom,
  limitUpMonitorAtom,
} from '../../store/atoms';

const L2_POLL_INTERVAL = 10000;
const THEME_POLL_INTERVAL = 90000;
const SIMULATION_SPEED_OPTIONS = [
  { label: '3s', value: 3000 },
  { label: '20s', value: 20000 },
  { label: '1分钟', value: 60000 },
];

const isTradeTime = () => {
  const now = new Date();
  const hour = now.getHours();
  const minute = now.getMinutes();
  const day = now.getDay();

  // 周末不交易
  if (day === 0 || day === 6) return false;

  // 上午 9:30 - 11:30
  if ((hour === 9 && minute >= 30) || hour === 10 || (hour === 11 && minute <= 30)) return true;
  // 下午 13:00 - 15:00
  if (hour === 13 || hour === 14 || (hour === 15 && minute === 0)) return true;

  return false;
};

const StockDashboard = () => {
  const [stockCode, setStockCode] = useAtom(stockCodeAtom);
  const [, fetchL2Dashboard] = useAtom(fetchL2DashboardAtom);
  const [, fetchLimitUpThemes] = useAtom(fetchLimitUpThemesAtom);
  const l2TimerRef = useRef(null);
  const themeTimerRef = useRef(null);
  const simulationTimerRef = useRef(null);
  const simulationIndexRef = useRef(1);
  const tradingAxis = useMemo(() => buildTradingTimeAxis(), []);
  const [simulationEnabled, setSimulationEnabled] = useState(false);
  const [simulationIndex, setSimulationIndex] = useState(1);
  const [simulationInterval, setSimulationInterval] = useState(3000);
  const simulationTime = tradingAxis[Math.min(simulationIndex, tradingAxis.length - 1)] || '09:31';

  const [wsConnected, setWsConnected] = useAtom(wsConnectedAtom);
  const [, setTimeshareData] = useAtom(timeshareDataAtom);
  const [, setLargeOrdersData] = useAtom(largeOrdersDataAtom);
  const [, setStockBasicData] = useAtom(stockBasicDataAtom);
  const [, setLimitUpMonitor] = useAtom(limitUpMonitorAtom);

  const handleStockCodeChange = (newCode) => {
    setStockCode(newCode);
    simulationIndexRef.current = 1;
    setSimulationIndex(1);
  };

  const handleSimulationToggle = (checked) => {
    setSimulationEnabled(checked);
    if (checked) {
      simulationIndexRef.current = 1;
      setSimulationIndex(1);
    }
  };

  const fetchL2Data = useCallback((simIndex = 1) => {
    if (stockCode) {
      if (simulationEnabled) {
        const nextTime = tradingAxis[Math.min(simIndex, tradingAxis.length - 1)] || '09:31';
        fetchL2Dashboard({ code: stockCode, simulate: true, simulateTime: nextTime });
      } else {
        fetchL2Dashboard(stockCode);
      }
    }
  }, [stockCode, fetchL2Dashboard, simulationEnabled, tradingAxis]);

  const fetchThemeData = useCallback(() => {
    if (stockCode) {
      fetchLimitUpThemes(stockCode);
    }
  }, [stockCode, fetchLimitUpThemes]);

  useEffect(() => {
    fetchL2Data();

    if (l2TimerRef.current) {
      clearInterval(l2TimerRef.current);
    }

    l2TimerRef.current = setInterval(() => {
      if (!simulationEnabled && isTradeTime()) {
        fetchL2Data();
      }
    }, L2_POLL_INTERVAL);

    return () => {
      if (l2TimerRef.current) {
        clearInterval(l2TimerRef.current);
      }
    };
  }, [fetchL2Data, simulationEnabled]);

  useEffect(() => {
    fetchThemeData();

    if (themeTimerRef.current) {
      clearInterval(themeTimerRef.current);
    }

    themeTimerRef.current = setInterval(() => {
      if (isTradeTime() || simulationEnabled) {
        fetchThemeData();
      }
    }, THEME_POLL_INTERVAL);

    return () => {
      if (themeTimerRef.current) {
        clearInterval(themeTimerRef.current);
      }
    };
  }, [fetchThemeData, simulationEnabled]);

  useEffect(() => {
    if (simulationTimerRef.current) {
      clearInterval(simulationTimerRef.current);
      simulationTimerRef.current = null;
    }

    if (!simulationEnabled) {
      return undefined;
    }

    const currentIndex = simulationIndexRef.current;
    fetchL2Dashboard({
      code: stockCode,
      simulate: true,
      simulateTime: tradingAxis[currentIndex] || '09:31'
    });

    simulationTimerRef.current = setInterval(() => {
      setSimulationIndex(prevIndex => {
        if (prevIndex >= tradingAxis.length - 1) {
          clearInterval(simulationTimerRef.current);
          simulationTimerRef.current = null;
          return prevIndex;
        }

        const nextIndex = Math.min(prevIndex + 1, tradingAxis.length - 1);
        simulationIndexRef.current = nextIndex;
        const nextTime = tradingAxis[nextIndex] || '15:00';
        fetchL2Dashboard({ code: stockCode, simulate: true, simulateTime: nextTime });
        return nextIndex;
      });
    }, simulationInterval);

    return () => {
      if (simulationTimerRef.current) {
        clearInterval(simulationTimerRef.current);
        simulationTimerRef.current = null;
      }
    };
  }, [simulationEnabled, stockCode, fetchL2Dashboard, tradingAxis, simulationInterval]);

  // WebSocket 连接管理
  useEffect(() => {
    if (simulationEnabled) {
      stockWS.disconnect();
      setWsConnected(false);
      return;
    }

    if (!isTradeTime()) return;

    stockWS.connect();

    const removeUpdate = stockWS.onL2Update((data) => {
      if (data?.success && data?.data) {
        const d = data.data;
        const timeshare = d.timeshare || [];
        const aligned = alignTimeshareToTradingAxis(timeshare);
        setTimeshareData({
          timeAxis: aligned.axis,
          fenshi: aligned.fenshi,
          volume: aligned.volume,
          zhuli: [],
          sanhu: [],
          big_map: d.big_map || {},
          order_book: d.order_book || null,
          base_info: {
            prevClosePrice: d.stock_info?.yesterday_close,
            openPrice: d.stock_info?.open,
            highPrice: d.stock_info?.high,
            lowPrice: d.stock_info?.low,
          },
        });

        const orders = d.large_orders || d.orders || [];
        const stats = d.statistics || {};
        const buyCount = orders.filter(o => o.direction === '被买' || o.direction === '主买').length;
        const sellCount = orders.filter(o => o.direction === '被卖' || o.direction === '主卖').length;
        const neutralCount = orders.length - buyCount - sellCount;
        const totalAmount = orders.reduce((sum, o) => sum + (o.amount || 0), 0);
        const buyAmount = orders.filter(o => o.direction === '被买' || o.direction === '主买').reduce((sum, o) => sum + (o.amount || 0), 0);
        const netInflow = buyAmount - (totalAmount - buyAmount);

        setLargeOrdersData({
          summary: { buyCount, sellCount, neutralCount, totalAmount, netInflow },
          largeOrders: orders.map(order => ({
            time: order.time,
            type: (order.direction === '被买' || order.direction === '主买') ? 'buy' : 'sell',
            price: order.price,
            volume: order.volume_lots,
            amount: order.amount * 10000,
            direction: order.direction,
          })),
          levelStats: {
            D300: stats.above_300, D100: stats.above_100,
            D50: stats.above_50, D30: stats.above_30,
            under_D30: stats.below_30,
          },
        });

        setStockBasicData(d.stock_info);
        if (d.limit_up_monitor) setLimitUpMonitor(d.limit_up_monitor);
      }
    });

    const removeConnect = stockWS.onConnect(() => {
      setWsConnected(true);
      stockWS.subscribe(stockCode);
      if (l2TimerRef.current) {
        clearInterval(l2TimerRef.current);
        l2TimerRef.current = null;
      }
    });

    const removeDisconnect = stockWS.onDisconnect(() => {
      setWsConnected(false);
      if (!l2TimerRef.current && !simulationEnabled) {
        l2TimerRef.current = setInterval(() => {
          if (isTradeTime()) fetchL2Data();
        }, L2_POLL_INTERVAL);
      }
    });

    if (stockWS.isConnected()) {
      stockWS.subscribe(stockCode);
    }

    return () => {
      removeUpdate();
      removeConnect();
      removeDisconnect();
    };
  }, [stockCode, simulationEnabled]);

  return (
    <div className='stock-dashboard-container' style={{ minHeight: '100vh' }}>
      <div className="simulation-toolbar">
        <span className="simulation-title">模拟开盘</span>
        <Switch size="small" checked={simulationEnabled} onChange={handleSimulationToggle} />
        {simulationEnabled && (
          <>
            <Radio.Group
              className="simulation-speed"
              size="small"
              optionType="button"
              buttonStyle="solid"
              value={simulationInterval}
              options={SIMULATION_SPEED_OPTIONS}
              onChange={(event) => setSimulationInterval(event.target.value)}
            />
            <span className="simulation-time">回放到 {simulationTime}</span>
          </>
        )}
        {!simulationEnabled && (
          <Tag color={wsConnected ? 'green' : 'default'} style={{ marginLeft: 'auto' }}>
            {wsConnected ? 'WS 实时' : 'HTTP 轮询'}
          </Tag>
        )}
      </div>
      <div className="dashboard-layout">
        <div className="dashboard-main">
          <StockBasicInfo onStockCodeChange={handleStockCodeChange} />
          <StockChart />
          <ThemeLimitUpPanel />
          <StockOrderDetails />
        </div>
        <aside className="dashboard-side">
          <HandicapLanguagePanel />
        </aside>
      </div>
    </div>
  );
};

export default StockDashboard;
