import React, { useEffect, useRef, useCallback } from 'react';
import { useAtom } from 'jotai';
import { useSearchParams } from 'react-router-dom';
import StockBasicInfo from './components/StockBasicInfo';
import StockChart from './components/StockChart';
import StockOrderDetails from './components/StockOrderDetails';
import {
  stockCodeAtom,
  fetchL2DashboardAtom
} from '../../store/atoms';

const POLL_INTERVAL = 5000; // 5秒轮询

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
  const [searchParams] = useSearchParams();
  const [stockCode, setStockCode] = useAtom(stockCodeAtom);
  const [, fetchL2Dashboard] = useAtom(fetchL2DashboardAtom);
  const timerRef = useRef(null);

  const handleStockCodeChange = (newCode) => {
    setStockCode(newCode);
  };

  // 数据获取函数
  const fetchData = useCallback(() => {
    if (stockCode) {
      fetchL2Dashboard(stockCode);
    }
  }, [stockCode, fetchL2Dashboard]);

  // 初始加载 + 轮询
  useEffect(() => {
    // 立即加载一次
    fetchData();

    // 设置轮询
    timerRef.current = setInterval(() => {
      if (isTradeTime()) {
        fetchData();
      }
    }, POLL_INTERVAL);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [fetchData]);

  return (
    <div className='stock-dashboard-container' style={{ backgroundColor: '#141213', minHeight: '100vh' }}>
      <StockBasicInfo onStockCodeChange={handleStockCodeChange} />
      <StockChart />
      <StockOrderDetails />
    </div>
  );
};

export default StockDashboard;
