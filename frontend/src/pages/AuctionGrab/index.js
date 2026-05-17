import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Spin, Popover } from 'antd';
import { LeftOutlined, RightOutlined, DownOutlined } from '@ant-design/icons';
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
    parseInt(dateStr.slice(0, 4)),
    parseInt(dateStr.slice(4, 6)) - 1,
    parseInt(dateStr.slice(6, 8))
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

const SORT_OPTIONS = [
  { key: 'wtje', label: '委托金额' },
  { key: 'cjje', label: '成交金额' },
  { key: 'kpje', label: '开盘金额' },
  { key: 'zf', label: '涨幅' },
];

function RecommendReason({ text }) {
  if (!text) return null;
  return (
    <Popover
      content={<div className="ag-rec-popover-content">{text}</div>}
      trigger={['hover', 'click']}
      placement="topLeft"
      overlayClassName="ag-rec-popover"
    >
      <span
        className="ag-rec-reason"
        role="button"
        tabIndex={0}
        onClick={(e) => e.stopPropagation()}
      >
        {text}
      </span>
    </Popover>
  );
}

function AuctionGrab() {
  const navigate = useNavigate();
  const todayStr = useMemo(() => getLastTradingDayStr(), []);
  const [currentDate, setCurrentDate] = useState(getLastTradingDayStr);
  const [activeTab, setActiveTab] = useState('morning'); // morning | tail
  const [sortBy, setSortBy] = useState('wtje');
  const [sortOpen, setSortOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const dataCache = useRef({});
  const dropdownRef = useRef(null);

  // 点击外部关闭下拉
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setSortOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const fetchData = useCallback(async (dt, tab, sort) => {
    const period = tab === 'tail' ? '1' : '0';
    const cacheKey = `${dt}_${period}_${sort}`;

    if (dataCache.current[cacheKey]) {
      setData(dataCache.current[cacheKey]);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const res = await apiRequest(`/api/v1/auction-grab?dt=${dt}&period=${period}&sort=${sort}`);
      if (res?.data) {
        dataCache.current[cacheKey] = res.data;
        setData(res.data);
      }
    } catch (err) {
      console.error('Failed to fetch auction grab data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(currentDate, activeTab, sortBy);
  }, [fetchData, currentDate, activeTab, sortBy]);

  const items = data?.items || [];
  const emotionStage = data?.emotion_stage || '';
  const recommendHint = data?.recommend_hint || '';

  const renderStars = (stars, reason) => {
    const n = Math.min(3, Math.max(0, parseInt(stars, 10) || 0));
    if (n === 0) return <span className="ag-stars-empty">—</span>;
    return (
      <span className="ag-stars" title={reason || ''}>
        {Array.from({ length: n }).map((_, i) => (
          <span key={i} className="ag-star">★</span>
        ))}
      </span>
    );
  };

  const getChangeColor = (val) => {
    const num = parseFloat(val);
    if (num > 0) return '#ff4d4f';
    if (num < 0) return '#52c41a';
    return '#999';
  };

  const formatAmount = (val) => {
    const num = parseFloat(val);
    if (isNaN(num)) return '--';
    if (num >= 10000) return `${(num / 10000).toFixed(2)}亿`;
    return `${num.toFixed(2)}万`;
  };

  const formatPct = (val) => {
    const num = parseFloat(val);
    if (isNaN(num)) return '--';
    return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`;
  };

  const currentSortLabel = SORT_OPTIONS.find(o => o.key === sortBy)?.label || '委托金额';

  return (
    <div className="ag-container">
      <div className="page-date-nav">
        <button
          type="button"
          className="date-nav-btn"
          onClick={() => setCurrentDate(offsetDate(currentDate, -1))}
        >
          <LeftOutlined /> 前一天
        </button>
        <div className="page-date-nav-end">
          <button
            type="button"
            className="date-nav-btn"
            disabled={currentDate >= todayStr}
            onClick={() => setCurrentDate(offsetDate(currentDate, 1))}
          >
            后一天 <RightOutlined />
          </button>
          <span className="date-nav-label">{formatDateDisplay(currentDate)}</span>
        </div>
      </div>

      <div className="ag-toolbar">
        <div className="ag-toolbar-left">
          <div className="ag-tabs">
            <span
              className={`ag-tab ${activeTab === 'morning' ? 'active' : ''}`}
              onClick={() => setActiveTab('morning')}
            >
              早盘竞价抢筹
            </span>
            <span
              className={`ag-tab ${activeTab === 'tail' ? 'active' : ''}`}
              onClick={() => setActiveTab('tail')}
            >
              尾盘抢筹
            </span>
          </div>

          <div className="ag-sort-dropdown" ref={dropdownRef}>
            <div
              className="ag-sort-trigger"
              onClick={() => setSortOpen(!sortOpen)}
            >
              <span>{currentSortLabel}</span>
              <DownOutlined className={`ag-sort-arrow ${sortOpen ? 'open' : ''}`} />
            </div>
            {sortOpen && (
              <div className="ag-sort-menu">
                {SORT_OPTIONS.map(opt => (
                  <div
                    key={opt.key}
                    className={`ag-sort-item ${sortBy === opt.key ? 'active' : ''}`}
                    onClick={() => {
                      setSortBy(opt.key);
                      setSortOpen(false);
                    }}
                  >
                    {opt.label}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {(emotionStage || recommendHint) && (
        <div className="ag-rec-hint">
          {emotionStage && <span className="ag-rec-stage">情绪周期：{emotionStage}</span>}
          {recommendHint && <span className="ag-rec-text">{recommendHint}</span>}
        </div>
      )}

      {/* 表格 */}
      <div className="ag-table-wrap">
        <div className="ag-table-header">
          <div className="ag-col ag-col-name">股票名称</div>
          <div className="ag-col ag-col-amount">开盘金额</div>
          <div className="ag-col ag-col-change">竞价涨幅</div>
          <div className="ag-col ag-col-close-change">当日收盘涨幅</div>
          <div className="ag-col ag-col-next-change">次日涨幅</div>
          <div className="ag-col ag-col-turnover">抢筹成交额</div>
          <div className="ag-col ag-col-order">抢筹委托金额</div>
          <div className="ag-col ag-col-date">时间</div>
          <div className="ag-col ag-col-recommend">推荐度</div>
        </div>

        {loading ? (
          <div className="ag-loading">
            <Spin size="large" />
          </div>
        ) : items.length === 0 ? (
          <div className="ag-empty">暂无数据</div>
        ) : (
          items.map((item) => (
            <div
              key={item.code}
              className="ag-table-row"
              onClick={() => navigate(`/stock-dashboard?code=${item.code}`)}
            >
              <div className="ag-col ag-col-name">
                <span className="ag-stock-name">{item.name}</span>
                <span className="ag-stock-code">{item.code}</span>
              </div>
              <div className="ag-col ag-col-amount">
                {formatAmount(item.open_amount)}
              </div>
              <div
                className="ag-col ag-col-change"
                style={{ color: getChangeColor(item.grab_change_pct) }}
              >
                {parseFloat(item.grab_change_pct) > 0 ? '+' : ''}{item.grab_change_pct}%
              </div>
              <div
                className="ag-col ag-col-close-change"
                style={{ color: getChangeColor(item.close_change_pct) }}
              >
                {formatPct(item.close_change_pct)}
              </div>
              <div
                className="ag-col ag-col-next-change"
                style={{ color: getChangeColor(item.next_day_change_pct) }}
              >
                {formatPct(item.next_day_change_pct)}
              </div>
              <div className="ag-col ag-col-turnover">
                {formatAmount(item.grab_turnover)}
              </div>
              <div className="ag-col ag-col-order">
                {formatAmount(item.grab_order_amount)}
              </div>
              <div className="ag-col ag-col-date">
                {item.date}
              </div>
              <div
                className="ag-col ag-col-recommend"
                onClick={(e) => e.stopPropagation()}
              >
                {renderStars(item.recommend_stars, item.recommend_reason)}
                <RecommendReason text={item.recommend_reason} />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default AuctionGrab;
