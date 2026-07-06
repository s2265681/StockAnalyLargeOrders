import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Spin } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../config/api';
import './index.css';

const getLastTradingDayStr = () => {
  const d = new Date();
  const dow = d.getDay();
  if (dow === 6) d.setDate(d.getDate() - 1);
  if (dow === 0) d.setDate(d.getDate() - 2);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
};

const offsetDate = (dateStr, delta) => {
  const d = new Date(
    parseInt(dateStr.slice(0, 4), 10),
    parseInt(dateStr.slice(4, 6), 10) - 1,
    parseInt(dateStr.slice(6, 8), 10),
  );
  let count = 0;
  const step = delta > 0 ? 1 : -1;
  while (count !== delta) {
    d.setDate(d.getDate() + step);
    const dow = d.getDay();
    if (dow !== 0 && dow !== 6) count += step;
  }
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
};

const formatDateDisplay = (dateStr) => {
  if (!dateStr || dateStr.length !== 8) return dateStr;
  return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`;
};

const BOARD_TABS = [
  { key: 'main', label: '主板' },
  { key: 'gem', label: '创业板' },
  { key: 'bond', label: '可转债' },
];

const matchBoard = (code, board) => {
  const c = String(code || '').padStart(6, '0');
  if (board === 'gem') return c.startsWith('30');
  if (board === 'bond') return c.startsWith('11') || c.startsWith('12');
  return (c.startsWith('00') || c.startsWith('60')) && !c.startsWith('30') && !c.startsWith('68');
};

const formatPct = (val, colored = true) => {
  const num = parseFloat(val);
  if (!Number.isFinite(num)) return '--';
  const text = `${num > 0 ? '+' : ''}${num.toFixed(2)}%`;
  if (!colored) return text;
  const cls = num > 0 ? 'sg-up' : num < 0 ? 'sg-down' : '';
  return <span className={cls}>{text}</span>;
};

const formatTurnover = (val) => {
  const num = parseFloat(val);
  if (!Number.isFinite(num)) return '--';
  return `${num.toFixed(2)}%`;
};

const formatSpeed = (val) => {
  const num = parseFloat(val);
  if (!Number.isFinite(num)) return '--';
  const abs = Math.abs(num);
  if (abs >= 100000000) return `${(num / 100000000).toFixed(2)}亿`;
  if (abs >= 10000) return `${(num / 10000).toFixed(0)}万`;
  return num.toFixed(0);
};

function SectorGrab() {
  const navigate = useNavigate();
  const todayStr = useMemo(() => getLastTradingDayStr(), []);
  const [currentDate, setCurrentDate] = useState(getLastTradingDayStr);
  const [sectors, setSectors] = useState([]);
  const [sectorsLoading, setSectorsLoading] = useState(true);
  const [selectedSector, setSelectedSector] = useState(null);
  const [stocks, setStocks] = useState([]);
  const [stocksLoading, setStocksLoading] = useState(false);
  const [activeBoard, setActiveBoard] = useState('main');
  const [refreshInterval, setRefreshInterval] = useState(null);
  const sectorsCache = useRef({});
  const stocksCache = useRef({});
  const fetchIdRef = useRef(0);
  const pollTimerRef = useRef(null);

  const isTodayView = currentDate === todayStr;

  const fetchSectors = useCallback(async (dt, { silent = false } = {}) => {
    const fetchId = ++fetchIdRef.current;
    if (!silent) setSectorsLoading(true);
    try {
      const res = await apiRequest(`/api/v1/sector-grab/sectors?dt=${dt}`, { timeout: 60000 });
      if (fetchId !== fetchIdRef.current) return;
      const payload = res?.data;
      if (payload?.sectors) {
        sectorsCache.current[dt] = payload;
        setSectors(payload.sectors);
        setRefreshInterval(payload.refresh_interval_sec || null);
        setSelectedSector((prev) => {
          if (prev) {
            const still = payload.sectors.find((s) => s.gn_code === prev.gn_code);
            return still || payload.sectors[0] || null;
          }
          return payload.sectors[0] || null;
        });
      }
    } catch (err) {
      console.error('Failed to fetch sector grab sectors:', err);
    } finally {
      if (fetchId === fetchIdRef.current && !silent) {
        setSectorsLoading(false);
      }
    }
  }, []);

  const fetchStocks = useCallback(async (dt, gnCode, { silent = false } = {}) => {
    if (!gnCode) return;
    const cacheKey = `${dt}_${gnCode}`;
    const fetchId = ++fetchIdRef.current;
    if (!silent) setStocksLoading(true);
    try {
      const res = await apiRequest(
        `/api/v1/sector-grab/stocks?dt=${dt}&gnCode=${gnCode}`,
        { timeout: 60000 },
      );
      if (fetchId !== fetchIdRef.current) return;
      const payload = res?.data;
      if (payload?.stocks) {
        stocksCache.current[cacheKey] = payload;
        setStocks(payload.stocks);
      }
    } catch (err) {
      console.error('Failed to fetch sector grab stocks:', err);
    } finally {
      if (fetchId === fetchIdRef.current && !silent) {
        setStocksLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    setSelectedSector(null);
    setStocks([]);
    const cached = sectorsCache.current[currentDate];
    if (cached?.sectors && !isTodayView) {
      setSectors(cached.sectors);
      setSectorsLoading(false);
      if (cached.sectors.length) setSelectedSector(cached.sectors[0]);
    } else {
      fetchSectors(currentDate);
    }
  }, [currentDate, fetchSectors, isTodayView]);

  useEffect(() => {
    if (!selectedSector?.gn_code) return;
    const cacheKey = `${currentDate}_${selectedSector.gn_code}`;
    const cached = stocksCache.current[cacheKey];
    if (cached?.stocks && !isTodayView) {
      setStocks(cached.stocks);
      return;
    }
    fetchStocks(currentDate, selectedSector.gn_code);
  }, [currentDate, selectedSector, fetchStocks, isTodayView]);

  useEffect(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    if (!isTodayView || !refreshInterval) return undefined;

    pollTimerRef.current = setInterval(() => {
      fetchSectors(currentDate, { silent: true });
      if (selectedSector?.gn_code) {
        fetchStocks(currentDate, selectedSector.gn_code, { silent: true });
      }
    }, refreshInterval * 1000);

    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [
    isTodayView,
    refreshInterval,
    currentDate,
    selectedSector?.gn_code,
    fetchSectors,
    fetchStocks,
  ]);

  const filteredStocks = useMemo(
    () => stocks.filter((s) => matchBoard(s.code, activeBoard)),
    [stocks, activeBoard],
  );

  const handleSectorClick = (sector) => {
    setSelectedSector(sector);
    setActiveBoard('main');
  };

  return (
    <div className="sg-container">
      <div className="sg-header-bar">
        <div className="page-date-nav sg-page-date-nav">
          <button
            type="button"
            className="date-nav-btn"
            onClick={() => setCurrentDate(offsetDate(currentDate, -1))}
          >
            <LeftOutlined /> 前一天
          </button>
          <span className="date-nav-label">{formatDateDisplay(currentDate)}</span>
          <button
            type="button"
            className="date-nav-btn"
            disabled={currentDate >= todayStr}
            onClick={() => setCurrentDate(offsetDate(currentDate, 1))}
          >
            后一天 <RightOutlined />
          </button>
        </div>
        {isTodayView && refreshInterval && (
          <div className="sg-refresh-hint">
            盘中自动刷新 · 每 {refreshInterval >= 60 ? `${refreshInterval / 60} 分钟` : `${refreshInterval} 秒`}
          </div>
        )}
      </div>

      <div className="sg-layout">
        <div className="sg-sector-panel">
          <div className="sg-panel-title">板块列表</div>
          <Spin spinning={sectorsLoading}>
            <div className="sg-sector-table-wrap">
              <table className="sg-table sg-sector-table">
                <thead>
                  <tr>
                    <th>板块名称</th>
                    <th>强度</th>
                    <th>强度变化</th>
                    <th>涨幅</th>
                    <th>涨停家数</th>
                  </tr>
                </thead>
                <tbody>
                  {sectors.length === 0 && !sectorsLoading ? (
                    <tr>
                      <td colSpan={5} className="sg-empty">暂无数据</td>
                    </tr>
                  ) : (
                    sectors.map((sector) => (
                      <tr
                        key={sector.gn_code}
                        className={
                          selectedSector?.gn_code === sector.gn_code ? 'sg-row-active' : ''
                        }
                        onClick={() => handleSectorClick(sector)}
                      >
                        <td className="sg-sector-name-cell">
                          <span className="sg-sector-name">{sector.name}</span>
                          {sector.is_hot ? (
                            <span className="sg-hot-tag">🔥 热</span>
                          ) : null}
                        </td>
                        <td>{sector.strength}</td>
                        <td>{sector.strength_change > 0 ? `+${sector.strength_change}` : sector.strength_change}</td>
                        <td>{formatPct(sector.change_pct)}</td>
                        <td>{sector.limit_up_count || 0}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Spin>
        </div>

        <div className="sg-stocks-panel">
          <div className="sg-stocks-header">
            <div className="sg-panel-title">
              {selectedSector ? `${selectedSector.name} · 抢筹个股` : '抢筹个股'}
            </div>
            <div className="sg-board-tabs">
              {BOARD_TABS.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  className={`sg-board-tab ${activeBoard === tab.key ? 'active' : ''}`}
                  onClick={() => setActiveBoard(tab.key)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <Spin spinning={stocksLoading}>
            <div className="sg-stocks-table-wrap">
              <table className="sg-table sg-stocks-table">
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th>涨幅</th>
                    <th>换手</th>
                    <th>主力净流入</th>
                    <th>领涨</th>
                    <th>主力</th>
                    <th>连板</th>
                    <th>板块</th>
                    <th>人气</th>
                  </tr>
                </thead>
                <tbody>
                  {!selectedSector ? (
                    <tr>
                      <td colSpan={10} className="sg-empty">请选择左侧板块</td>
                    </tr>
                  ) : filteredStocks.length === 0 && !stocksLoading ? (
                    <tr>
                      <td colSpan={10} className="sg-empty">该板块暂无个股</td>
                    </tr>
                  ) : (
                    filteredStocks.map((stock) => (
                      <tr
                        key={stock.code}
                        className="sg-stock-row"
                        onClick={() => navigate(`/stock-dashboard?code=${stock.code}`)}
                      >
                        <td className="sg-code">{stock.code}</td>
                        <td className="sg-name">{stock.name}</td>
                        <td className="sg-change">{formatPct(stock.change_pct)}</td>
                        <td>{formatTurnover(stock.turnover_pct)}</td>
                        <td className={parseFloat(stock.speed) >= 0 ? 'sg-up' : 'sg-down'}>
                          {formatSpeed(stock.speed)}
                        </td>
                        <td>
                          {stock.leader_rank ? (
                            <span className="sg-leader-tag">{stock.leader_rank}</span>
                          ) : '--'}
                        </td>
                        <td>{stock.main_force || '--'}</td>
                        <td>
                          {stock.board_label ? (
                            <span className="sg-board-tag">{stock.board_label}</span>
                          ) : '--'}
                        </td>
                        <td className="sg-sectors" title={stock.sectors}>
                          {stock.sectors || '--'}
                        </td>
                        <td>{stock.popularity || '--'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Spin>
        </div>
      </div>
    </div>
  );
}

export default SectorGrab;
