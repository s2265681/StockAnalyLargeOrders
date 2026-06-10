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
  { key: 'score', label: '推荐度' },
  { key: 'wtje',  label: '委托金额' },
  { key: 'cjje',  label: '成交金额' },
  { key: 'kpje',  label: '开盘金额' },
  { key: 'zf',    label: '竞价涨幅' },
  { key: 'jrzf',  label: '今日涨幅' },
  { key: 'zrzf',  label: '昨日涨幅' },
  { key: 'crzf',  label: '次日涨幅' },
];

const normalizeCode = (code) => String(code || '').padStart(6, '0');

const limitUpThreshold = (code) => {
  const c = normalizeCode(code);
  if (c.startsWith('30') || c.startsWith('68')) return 19.5;
  if (c.startsWith('4') || c.startsWith('8')) return 29.5;
  return 9.5;
};

const isAtLimitUp = (item) => {
  const vals = [item.today_change_pct, item.close_change_pct, item.grab_change_pct]
    .map((v) => parseFloat(v))
    .filter((v) => Number.isFinite(v));
  if (!vals.length) return false;
  const pct = Math.max(...vals);
  return pct >= limitUpThreshold(item.code);
};

const mergeEnrichments = (items, enrichments) => {
  if (!items?.length || !enrichments) return items;
  return items.map((item) => {
    const extra = enrichments[normalizeCode(item.code)] || enrichments[item.code];
    const merged = extra ? { ...item, ...extra } : { ...item };
    if (isAtLimitUp(merged)) {
      merged.recommend_stars = 0;
      merged.recommend_reason = '当日已涨停，不参与推荐';
    }
    return merged;
  });
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const sortAuctionItems = (items, sortKey) => {
  const list = [...(items || [])];
  const num = (v) => {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : 0;
  };
  const numOrNull = (v) => {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : null;
  };
  const star = (x) => parseInt(x.recommend_stars, 10) || 0;
  const score = (x) => parseFloat(x.recommend_score) || 0;

  // 按推荐度：有评分的在前（按 score 降序），无评分的在后（按委托金额降序）
  if (sortKey === 'score') {
    return list.sort((a, b) => {
      const sa = score(a), sb = score(b);
      const hasA = sa > 0, hasB = sb > 0;
      if (hasA !== hasB) return hasA ? -1 : 1;
      if (hasA && hasB) return sb - sa;
      return num(b.grab_order_amount) - num(a.grab_order_amount);
    });
  }

  // 涨幅类排序：无数据的排最后
  const changeSortField = {
    jrzf: (x) => numOrNull(x.close_change_pct) ?? numOrNull(x.today_change_pct),
    zrzf: (x) => numOrNull(x.prev_day_change_pct),
    crzf: (x) => numOrNull(x.next_day_change_pct),
  };
  if (changeSortField[sortKey]) {
    const getVal = changeSortField[sortKey];
    return list.sort((a, b) => {
      const va = getVal(a), vb = getVal(b);
      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;
      return vb - va;
    });
  }

  // 其他排序（wtje/cjje/kpje/zf）：有推荐的置顶，再按字段排
  const byField = {
    wtje: (a, b) => num(b.grab_order_amount) - num(a.grab_order_amount),
    cjje: (a, b) => num(b.grab_turnover) - num(a.grab_turnover),
    kpje: (a, b) => num(b.open_amount) - num(a.open_amount),
    zf:   (a, b) => num(b.grab_change_pct) - num(a.grab_change_pct),
  };
  const cmpField = byField[sortKey] || byField.wtje;
  return list.sort((a, b) => {
    const starDiff = star(b) - star(a);
    if (starDiff !== 0) return starDiff;
    return cmpField(a, b);
  });
};

function RecommendStars({ stars, reason }) {
  const n = Math.min(3, Math.max(0, parseInt(stars, 10) || 0));
  if (n === 0) return <span className="ag-stars-empty">—</span>;
  const starEl = (
    <span className="ag-stars ag-stars-hover">
      {Array.from({ length: n }).map((_, i) => (
        <span key={i} className="ag-star">★</span>
      ))}
    </span>
  );
  if (!reason) return starEl;
  return (
    <Popover
      content={<div className="ag-rec-popover-content">{reason}</div>}
      trigger={['hover', 'click']}
      placement="topLeft"
      overlayClassName="ag-rec-popover"
    >
      {starEl}
    </Popover>
  );
}

function AuctionGrab() {
  const navigate = useNavigate();
  const todayStr = useMemo(() => getLastTradingDayStr(), []);
  const [currentDate, setCurrentDate] = useState(getLastTradingDayStr);
  const [activeTab, setActiveTab] = useState('morning'); // morning | tail
  const [sortBy, setSortBy] = useState('score');
  const [sortOpen, setSortOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const dataCache = useRef({});
  const fetchIdRef = useRef(0);
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

  const pollScoreEnrichments = useCallback(async (dt, tab, fetchId, { live = false, continuous = false } = {}) => {
    const period = tab === 'tail' ? '1' : '0';
    const cacheKey = `${dt}_${period}`;
    const isTodayView = dt === todayStr;
    const maxBootstrapAttempts = 30;
    let mergedOnce = false;

    for (let attempt = 0; attempt < 9999; attempt += 1) {
      if (fetchId !== fetchIdRef.current) return;

      // 首次立即请求；未拿到数据前每 2s 重试，拿到后再按 45s 刷新
      if (attempt > 0) {
        const intervalMs = (!mergedOnce || !continuous)
          ? 2000
          : (isTodayView && live ? 45000 : 2000);
        await sleep(intervalMs);
      }
      if (fetchId !== fetchIdRef.current) return;

      try {
        const liveParam = (live || isTodayView) ? '&live=1' : '';
        const res = await apiRequest(
          `/api/v1/auction-grab/score?dt=${dt}&period=${period}${liveParam}`,
          { timeout: 60000 },
        );
        if (fetchId !== fetchIdRef.current) return;

        const payload = res?.data;
        const enrichments = payload?.enrichments;
        const hasEnrichments = enrichments && Object.keys(enrichments).length > 0;

        if (hasEnrichments) {
          const cached = dataCache.current[cacheKey];
          if (cached?.items) {
            const merged = {
              ...cached,
              items: mergeEnrichments(cached.items, enrichments),
              emotion_stage: payload.emotion_stage || cached.emotion_stage || '',
              recommend_hint: payload.recommend_hint || cached.recommend_hint || '',
              score_ready: Boolean(payload.ready),
              live_refresh: Boolean(payload.live_refresh),
            };
            dataCache.current[cacheKey] = merged;
            setData({ ...merged, items: [...merged.items] });
            mergedOnce = true;
          }
        }

        if (!continuous) {
          if (payload?.ready || mergedOnce) return;
          if (attempt >= maxBootstrapAttempts - 1) return;
        } else if (mergedOnce && !(isTodayView && live)) {
          return;
        }
      } catch (err) {
        console.error('Failed to fetch auction grab enrichments:', err);
        if (!continuous && attempt >= maxBootstrapAttempts - 1) return;
      }
    }
  }, [todayStr]);

  const fetchData = useCallback(async (dt, tab) => {
    const period = tab === 'tail' ? '1' : '0';
    const cacheKey = `${dt}_${period}`;
    const fetchId = ++fetchIdRef.current;
    const isTodayView = dt === todayStr;

    if (dataCache.current[cacheKey] && !isTodayView) {
      setData(dataCache.current[cacheKey]);
      setLoading(false);
      pollScoreEnrichments(dt, tab, fetchId);
      return;
    }

    // 当日：跳过 stale 缓存，确保重新拉 score
    if (dataCache.current[cacheKey] && isTodayView) {
      setData(dataCache.current[cacheKey]);
      setLoading(false);
      pollScoreEnrichments(dt, tab, fetchId, { live: true, continuous: true });
      return;
    }

    setLoading(true);
    try {
      const res = await apiRequest(`/api/v1/auction-grab?dt=${dt}&period=${period}`, {
        timeout: 120000,
      });
      if (fetchId !== fetchIdRef.current) return;
      if (res?.data) {
        dataCache.current[cacheKey] = res.data;
        setData(res.data);
        const isLive = isTodayView || Boolean(res.data.live_refresh);
        pollScoreEnrichments(dt, tab, fetchId, {
          live: isLive,
          continuous: isLive,
        });
      }
    } catch (err) {
      console.error('Failed to fetch auction grab data:', err);
    } finally {
      if (fetchId === fetchIdRef.current) {
        setLoading(false);
      }
    }
  }, [pollScoreEnrichments, todayStr]);

  useEffect(() => {
    fetchData(currentDate, activeTab);
  }, [fetchData, currentDate, activeTab]);

  const items = useMemo(
    () => sortAuctionItems(data?.items || [], sortBy),
    [data?.items, sortBy]
  );
  const emotionStage = data?.emotion_stage || '';
  const recommendHint = data?.recommend_hint || '';

  const isTodayView = currentDate === todayStr;

  const displayTodayChange = (item) => {
    if (isTodayView && item.today_change_pct != null) return item.today_change_pct;
    return item.close_change_pct;
  };

  const renderStars = (stars, reason) => (
    <RecommendStars stars={stars} reason={reason} />
  );

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
      <div className="ag-header-bar">
        <div className="page-date-nav ag-page-date-nav">
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
          <div className="ag-col ag-col-meta">行业 / 题材</div>
          <div className="ag-col ag-col-amount">开盘金额</div>
          <div className="ag-col ag-col-change">竞价涨幅</div>
          <div className="ag-col ag-col-close-change">{isTodayView ? '今日涨幅' : '收盘涨幅'}</div>
          <div className="ag-col ag-col-prev-change">昨日涨幅</div>
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
              <div className="ag-col ag-col-meta">
                {item.industry
                  ? <span className="ag-meta-industry">{item.industry}</span>
                  : null}
                {item.concepts
                  ? <span className="ag-meta-concepts">{item.concepts}</span>
                  : null}
                {!item.industry && !item.concepts
                  ? <span className="ag-meta-empty">--</span>
                  : null}
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
                style={{ color: getChangeColor(displayTodayChange(item)) }}
              >
                {formatPct(displayTodayChange(item))}
              </div>
              <div
                className="ag-col ag-col-prev-change"
                style={{ color: getChangeColor(item.prev_day_change_pct) }}
              >
                {formatPct(item.prev_day_change_pct)}
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
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default AuctionGrab;
