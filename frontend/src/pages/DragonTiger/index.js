// frontend/src/pages/DragonTiger/index.js
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Spin, message } from 'antd';
import { LeftOutlined, RightOutlined, RobotOutlined, LoadingOutlined } from '@ant-design/icons';
import { apiRequest } from '../../config/api';
import './index.css';

// 获取最近交易日（周末退到周五）
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

const formatDateDisplay = (s) =>
  s && s.length === 8 ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s;

/** 核心游资仅展示最近 N 个交易日（与离线补全范围一致） */
const VISIBLE_TRADING_DAYS = 5;

const getMinVisibleDate = (endDate) => {
  let d = endDate;
  for (let i = 0; i < VISIBLE_TRADING_DAYS - 1; i += 1) {
    d = offsetDate(d, -1);
  }
  return d;
};

const fmtAmount = (val) => {
  const v = parseFloat(val || 0);
  if (isNaN(v)) return '--';
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(0)}万`;
  return `${v.toFixed(0)}`;
};

const HOT_MONEY_KW = ['知春路', '成都', '宁波', '佛山', '拉萨', '乐清千帆', '温州', '绍兴', '华鑫', '财通', '游资'];
const isHotMoney = (name) => HOT_MONEY_KW.some((kw) => name && name.includes(kw));

// 前端兜底映射（优先使用后端返回 seat.trader_tag）
const SEAT_TRADER_PATTERNS = [
  { pattern: '成都北一环路', trader: '成都系' },
  { pattern: '上海茅台路', trader: '炒股养家' },
  { pattern: '赵老哥', trader: '赵老哥' },
  { pattern: '作手新一', trader: '作手新一' },
  { pattern: '方新侠', trader: '方新侠' },
  { pattern: '章盟主', trader: '章盟主' },
  { pattern: '小鳄鱼', trader: '小鳄鱼' },
];

const getSeatTraderName = (seatName = '') => {
  const name = String(seatName || '');
  const hit = SEAT_TRADER_PATTERNS.find(({ pattern }) => name.includes(pattern));
  return hit ? hit.trader : '';
};

function renderAiAnalysisText(text) {
  if (!text) return null;

  const renderInline = (line, keyPrefix) => {
    const chunks = line.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
    return chunks.map((chunk, idx) => {
      const match = chunk.match(/^\*\*([\s\S]+)\*\*$/);
      if (match) {
        return (
          <strong key={`${keyPrefix}-strong-${idx}`} className="dt-ai-inline-strong">
            {match[1]}
          </strong>
        );
      }
      return <span key={`${keyPrefix}-text-${idx}`}>{chunk}</span>;
    });
  };

  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, idx) => {
      if (line.startsWith('## ')) {
        return (
          <div key={`ai-line-${idx}`} className="dt-ai-result-heading">
            {line.slice(3).trim()}
          </div>
        );
      }
      return (
        <div key={`ai-line-${idx}`} className="dt-ai-result-paragraph">
          {renderInline(line, `ai-line-${idx}`)}
        </div>
      );
    });
}

export function SeatTable({ seats, direction }) {
  if (!seats || seats.length === 0) {
    return <div style={{ padding: '20px 14px', color: '#555', fontSize: 12 }}>暂无数据</div>;
  }
  return (
    <>
      <div className="dt-seat-header">
        <span>席位名称</span>
        <span className="dt-seat-header-col">买入额</span>
        <span className="dt-seat-header-col">卖出额</span>
        <span className="dt-seat-header-col">净额</span>
      </div>
      {seats.map((seat, i) => {
        const hot = seat.is_hot_money || isHotMoney(seat.seat_name || '');
        const trader = seat.trader_tag || getSeatTraderName(seat.seat_name);
        const net = parseFloat(seat.net_amount || 0);
        return (
          <div key={i} className="dt-seat-row">
            <span className={`dt-seat-name ${hot ? 'hot-money' : ''}`} title={seat.seat_name}>
              <span className="dt-seat-name-text">{seat.seat_name || '--'}</span>
              {trader ? <em className="dt-seat-trader">{trader}</em> : null}
            </span>
            <span className="dt-seat-col buy-col">{fmtAmount(seat.buy_amount)}</span>
            <span className="dt-seat-col sell-col">{fmtAmount(seat.sell_amount)}</span>
            <span className={`dt-seat-col ${net > 0 ? 'net-pos' : net < 0 ? 'net-neg' : ''}`}>
              {fmtAmount(seat.net_amount)}
            </span>
          </div>
        );
      })}
    </>
  );
}

function DragonTiger() {
  const todayStr = useMemo(() => getLastTradingDayStr(), []);
  const minDate = useMemo(() => getMinVisibleDate(todayStr), [todayStr]);
  const [currentDate, setCurrentDate] = useState(() => getLastTradingDayStr());
  const [loading, setLoading] = useState(false);
  const [stocks, setStocks] = useState([]);
  const [selectedCode, setSelectedCode] = useState(null);
  const [aiResults, setAiResults] = useState({}); // code -> analysis
  const [aiEmptyHint, setAiEmptyHint] = useState(null); // code -> 未生成提示
  const [aiLoading, setAiLoading] = useState(new Set());
  const dataCache = useRef({}); // date -> stocks[]

  const fetchData = useCallback(async (date) => {
    if (dataCache.current[date]) {
      setStocks(dataCache.current[date]);
      if (dataCache.current[date].length > 0 && !selectedCode) {
        setSelectedCode(dataCache.current[date][0].code);
      }
      return;
    }
    setLoading(true);
    setStocks([]);
    setSelectedCode(null);
    try {
      const res = await apiRequest(`/api/v1/dragon-tiger?date=${date}`);
      if (res?.data?.stocks) {
        dataCache.current[date] = res.data.stocks;
        setStocks(res.data.stocks);
        if (res.data.stocks.length > 0) {
          setSelectedCode(res.data.stocks[0].code);
        }
      }
    } catch (e) {
      console.error('龙虎榜加载失败:', e);
    } finally {
      setLoading(false);
    }
  }, [selectedCode]);

  useEffect(() => {
    fetchData(currentDate);
  }, [currentDate]); // eslint-disable-line

  const handleDateChange = (delta) => {
    const next = delta > 0 ? offsetDate(currentDate, 1) : offsetDate(currentDate, -1);
    if (next < minDate || next > todayStr) return;
    setCurrentDate(next);
    setAiResults({});
    setAiEmptyHint(null);
  };

  const handleAiAnalysis = async (stock) => {
    const code = stock.code;
    if (aiLoading.has(code)) return;
    setAiLoading((prev) => new Set([...prev, code]));
    setAiEmptyHint((prev) => ({ ...prev, [code]: null }));
    try {
      const res = await apiRequest(
        `/api/v1/dragon-tiger/ai-analysis-cache?date=${currentDate}&code=${code}`
      );
      if (res?.data?.analysis) {
        setAiResults((prev) => ({ ...prev, [code]: res.data.analysis }));
        setAiEmptyHint((prev) => ({ ...prev, [code]: null }));
      } else {
        setAiResults((prev) => {
          const next = { ...prev };
          delete next[code];
          return next;
        });
        const hint = res?.message || '还未生成，由每日定时任务生成';
        setAiEmptyHint((prev) => ({ ...prev, [code]: hint }));
        message.info(hint);
      }
    } catch (e) {
      console.error('AI分析加载失败:', e);
      message.error('加载 AI 解读失败，请稍后重试');
    } finally {
      setAiLoading((prev) => {
        const next = new Set(prev);
        next.delete(code);
        return next;
      });
    }
  };

  const selectedStock = stocks.find((s) => s.code === selectedCode) || null;

  return (
    <div className="dt-container">
      {/* 顶部日期导航 */}
      <div className="dt-top-bar">
        <div className="date-nav">
          <button
            type="button"
            className="date-nav-btn"
            disabled={currentDate <= minDate}
            onClick={() => handleDateChange(-1)}
          >
            <LeftOutlined /> 前一天
          </button>
          <span className="date-nav-label">
            {formatDateDisplay(currentDate)}
            <span className="date-nav-hint">近{VISIBLE_TRADING_DAYS}日</span>
          </span>
          <button
            type="button"
            className="date-nav-btn"
            disabled={currentDate >= todayStr}
            onClick={() => handleDateChange(1)}
          >
            后一天 <RightOutlined />
          </button>
        </div>
      </div>

      {/* 主体 */}
      <div className="dt-main">
        {/* 左侧列表 */}
        <div className="dt-stock-list">
          {loading ? (
            <div className="dt-loading">
              <Spin size="large" tip="加载中..." />
            </div>
          ) : stocks.length === 0 ? (
            <div style={{ padding: 20, color: '#555', fontSize: 13 }}>暂无龙虎榜数据</div>
          ) : (
            stocks.map((stock) => {
              const pct = parseFloat(stock.change_pct || 0);
              const pctClass = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat';
              return (
                <div
                  key={stock.code}
                  className={`dt-stock-item ${selectedCode === stock.code ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedCode(stock.code);
                    setAiEmptyHint(null);
                  }}
                >
                  <div className="dt-stock-item-header">
                    <span className="dt-stock-name">{stock.name}</span>
                    <span className={`dt-stock-pct ${pctClass}`}>
                      {pct > 0 ? '+' : ''}{pct.toFixed(2)}%
                    </span>
                  </div>
                  <div className="dt-stock-code">{stock.code}</div>
                  <div className="dt-stock-net">
                    净额 {fmtAmount(stock.net_buy)}
                  </div>
                  <div className="dt-stock-reason" title={stock.reason}>
                    {stock.reason || '--'}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* 右侧详情 */}
        <div className="dt-detail">
          {!selectedStock ? (
            <div className="dt-detail-empty">← 点击左侧股票查看龙虎榜详情</div>
          ) : (
            <>
              {/* 头部 */}
              <div className="dt-detail-header">
                <div className="dt-detail-title">
                  <span className="dt-detail-name">{selectedStock.name}</span>
                  <span className="dt-detail-code">({selectedStock.code})</span>
                  <span className="dt-detail-meta">
                    上榜原因：<span className="dt-reason-badge" title={selectedStock.reason}>
                      {selectedStock.reason || '--'}
                    </span>
                  </span>
                  <span className={`dt-detail-net ${parseFloat(selectedStock.net_buy) > 0 ? 'positive' : 'negative'}`}>
                    净额：{fmtAmount(selectedStock.net_buy)}
                  </span>
                </div>
                <button
                  className="dt-ai-btn"
                  disabled={aiLoading.has(selectedStock.code)}
                  onClick={() => handleAiAnalysis(selectedStock)}
                >
                  {aiLoading.has(selectedStock.code)
                    ? <><LoadingOutlined style={{ marginRight: 4 }} />加载中...</>
                    : <><RobotOutlined style={{ marginRight: 4 }} />AI分析</>
                  }
                </button>
              </div>

              {/* AI分析结果 */}
              {aiEmptyHint?.[selectedStock.code] && !aiResults[selectedStock.code] && (
                <div className="dt-ai-result dt-ai-empty">
                  <div className="dt-ai-result-title">
                    <RobotOutlined style={{ marginRight: 6 }} />AI 资金意图解读
                  </div>
                  <div className="dt-ai-result-text dt-ai-empty-text">
                    {aiEmptyHint[selectedStock.code]}
                  </div>
                </div>
              )}
              {aiResults[selectedStock.code] && (
                <div className="dt-ai-result">
                  <div className="dt-ai-result-title">
                    <RobotOutlined style={{ marginRight: 6 }} />AI 资金意图解读
                  </div>
                  <div className="dt-ai-result-text">
                    {renderAiAnalysisText(aiResults[selectedStock.code])}
                  </div>
                </div>
              )}

              {/* 席位表格 */}
              <div className="dt-seats-row">
                <div className="dt-seats-panel">
                  <div className="dt-seats-title buy">买入席位</div>
                  <SeatTable seats={selectedStock.buy_seats} direction="buy" />
                </div>
                <div className="dt-seats-panel">
                  <div className="dt-seats-title sell">卖出席位</div>
                  <SeatTable seats={selectedStock.sell_seats} direction="sell" />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default DragonTiger;
