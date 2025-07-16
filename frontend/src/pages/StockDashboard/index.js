import React, { useEffect, useRef } from 'react';
import { useAtom } from 'jotai';
import { useSearchParams } from 'react-router-dom';
import StockBasicInfo from './components/StockBasicInfo';
import StockChart from './components/StockChart';
import StockOrderDetails from './components/StockOrderDetails';
import { 
  stockCodeAtom, 
  filterAmountAtom,
  fetchStockBasicAtom,
  fetchLargeOrdersAtom,
  fetchTimeshareDataAtom,
  fetchRealtimeDataAtom
} from '../../store/atoms';

const StockDashboard = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [stockCode, setStockCode] = useAtom(stockCodeAtom);
  const [filterAmount] = useAtom(filterAmountAtom);
  const [, fetchStockBasic] = useAtom(fetchStockBasicAtom);
  const [, fetchLargeOrders] = useAtom(fetchLargeOrdersAtom);
  const [, fetchTimeshareData] = useAtom(fetchTimeshareDataAtom);
  const [, fetchRealtimeData] = useAtom(fetchRealtimeDataAtom);

  // 组件初始化时从URL获取股票代码（只执行一次）
  useEffect(() => {
    const codeFromUrl = searchParams.get('code');
    if (codeFromUrl && codeFromUrl !== stockCode) {
      // 如果URL中有不同的股票代码，使用URL中的代码
      setStockCode(codeFromUrl);
    } else if (!codeFromUrl) {
      // 如果URL中没有代码，将当前代码设置到URL中
      setSearchParams({ code: stockCode }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // 只在组件初始化时执行一次

  // 当股票代码改变时更新URL
  const handleStockCodeChange = (newCode) => {
    setStockCode(newCode);
    setSearchParams({ code: newCode });
  };

  // 组件加载时获取数据（不包括大单数据，大单数据由filterAmount变化触发）
  useEffect(() => {
    if (stockCode) {
      fetchStockBasic(stockCode);
      fetchTimeshareData(stockCode);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stockCode]); // 只依赖stockCode，避免fetch函数引起的重复调用

  // 获取大单数据（处理filterAmount和stockCode变化）
  useEffect(() => {
    if (stockCode && filterAmount) {
      fetchLargeOrders({ code: stockCode, minAmount: filterAmount });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterAmount, stockCode]); // 只依赖数据参数，避免fetch函数引起的重复调用

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stockCode]); // 只依赖stockCode，避免fetch函数引起的重复调用

  return (
    <div style={{ padding: '24px', backgroundColor: '#141213', minHeight: '100vh' }}>
      {/* 股票基本信息 */}
      <StockBasicInfo onStockCodeChange={handleStockCodeChange} />
      
      {/* 股票分时图和大单统计 */}
      <StockChart />
      
      {/* 股票大单明细 */}
      <StockOrderDetails />
    </div>
  );
};

export default StockDashboard;
