import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Spin, Tag, Tooltip, Popover } from 'antd';
import { FireOutlined, ClockCircleOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../config/api';
import './index.css';

const boardColorMap = {
  1: { tag: '#3b82f6', label: '首板', rowClass: 'board-1' },
  2: { tag: '#10b981', label: '2板', rowClass: 'board-2' },
  3: { tag: '#f59e0b', label: '3板', rowClass: 'board-3' },
  4: { tag: '#f97316', label: '4板', rowClass: 'board-4' },
  5: { tag: '#ef4444', label: '5板', rowClass: 'board-5' },
  6: { tag: '#ec4899', label: '6板', rowClass: 'board-6' },
  7: { tag: '#a855f7', label: '7板', rowClass: 'board-7' },
};

const getBoardColor = (boards) => {
  if (boards >= 7) return boardColorMap[7];
  return boardColorMap[boards] || boardColorMap[1];
};

const formatTime = (t) => {
  if (!t || t.length < 6) return t || '--';
  return `${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4, 6)}`;
};

const getSealQuality = (stock) => {
  const { seal_ratio, first_time, break_count } = stock;
  let score = 0;
  if (seal_ratio >= 10) score += 3;
  else if (seal_ratio >= 3) score += 2;
  else if (seal_ratio >= 1) score += 1;
  const timeNum = parseInt(first_time || '150000', 10);
  if (timeNum <= 93000) score += 3;
  else if (timeNum <= 103000) score += 2;
  else if (timeNum <= 130000) score += 1;
  if (break_count === 0) score += 2;
  else if (break_count <= 1) score += 1;
  if (score >= 7) return { label: 'S', color: '#ff4d4f' };
  if (score >= 5) return { label: 'A', color: '#faad14' };
  if (score >= 3) return { label: 'B', color: '#1890ff' };
  return { label: 'C', color: '#666' };
};

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
    parseInt(dateStr.slice(6, 8), 10)
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

const toDtQuery = (dateStr) => `dt=${formatDateDisplay(dateStr)}`;

const formatRatePct = (value) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) return '--';
  return `${Number(value).toFixed(2)}%`;
};

const getRisePctClass = (value) => {
  if (value == null || Number.isNaN(Number(value))) return '';
  const n = Number(value);
  if (n >= 50) return 'green';
  if (n < 50) return 'down';
  return '';
};

const getBoardHitRateClass = (value) => {
  if (value == null || Number.isNaN(Number(value))) return '';
  const n = Number(value);
  if (n >= 65) return 'green';
  if (n < 40) return 'down';
  return 'orange';
};

const MIN_LOADING_MS = 300;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** 复盘图离线数据自 2026-05-11 起可用，此前日期不可选 */
const MIN_ECHELON_DATE = '20260511';

const clampEchelonDate = (dateStr) => {
  if (!dateStr || dateStr.length !== 8) return dateStr;
  if (dateStr < MIN_ECHELON_DATE) return MIN_ECHELON_DATE;
  const today = getLastTradingDayStr();
  return dateStr > today ? today : dateStr;
};

function LimitUpEchelon() {
  const navigate = useNavigate();
  const todayStr = useMemo(() => getLastTradingDayStr(), []);
  const [currentDate, setCurrentDate] = useState(() => clampEchelonDate(getLastTradingDayStr()));
  const dataCache = useRef({});
  const requestSeq = useRef(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async (dt) => {
    const targetDate = dt || getLastTradingDayStr();
    const requestId = requestSeq.current + 1;
    requestSeq.current = requestId;
    const startedAt = Date.now();

    const finishLoading = async () => {
      const elapsed = Date.now() - startedAt;
      if (elapsed < MIN_LOADING_MS) {
        await wait(MIN_LOADING_MS - elapsed);
      }
      if (requestSeq.current === requestId) {
        setLoading(false);
      }
    };

    setLoading(true);

    if (dataCache.current[targetDate]) {
      if (requestSeq.current === requestId) {
        setData(dataCache.current[targetDate]);
      }
      await finishLoading();
      return;
    }

    try {
      const res = await apiRequest(`/api/v1/limit-up-echelon?${toDtQuery(targetDate)}`);
      if (res?.data && requestSeq.current === requestId) {
        dataCache.current[targetDate] = res.data;
        setData(res.data);
      }
    } catch (err) {
      console.error('Failed to fetch limit up echelon:', err);
    } finally {
      await finishLoading();
    }
  }, []);

  useEffect(() => {
    fetchData(currentDate);
  }, [fetchData, currentDate]);

  const echelons = useMemo(() => data?.echelons || [], [data]);
  const summary = data?.summary || {};
  const themeRanking = useMemo(() => data?.theme_ranking || [], [data]);
  const allStocks = useMemo(() => echelons.flatMap((e) => e.stocks || []), [echelons]);

  const themeRankingWithLeaders = useMemo(() => {
    const getTheme = (stock) => stock.group_label || stock.theme || stock.industry;
    return themeRanking.map((theme) => {
      const explicitLeaders = theme.leaders || (theme.leader?.code ? [theme.leader] : []);
      if (explicitLeaders.length) return theme;

      const candidates = allStocks
        .filter((stock) => getTheme(stock) === theme.theme)
        .sort((a, b) => {
          const boardDiff = (b.boards || 0) - (a.boards || 0);
          if (boardDiff !== 0) return boardDiff;
          const rankA = a.ths_rank > 0 ? a.ths_rank : 9999;
          const rankB = b.ths_rank > 0 ? b.ths_rank : 9999;
          if (rankA !== rankB) return rankA - rankB;
          return (b.seal_amount || 0) - (a.seal_amount || 0);
        })
        .slice(0, 2)
        .map((stock, index) => ({
          code: stock.code,
          name: stock.name,
          role: index === 0 ? '先锋' : '中军',
          reason: index === 0
            ? '按连板高度、热度和封单强度自动兜底识别'
            : '按热度和容量补充识别',
        }));

      return {
        ...theme,
        leader: candidates[0] || {},
        leaders: candidates,
      };
    });
  }, [allStocks, themeRanking]);

  const stocksByTheme = useMemo(() => {
    const getTheme = (stock) => stock.group_label || stock.theme || stock.industry;
    const map = {};
    for (const stock of allStocks) {
      const theme = getTheme(stock);
      if (!theme) continue;
      if (!map[theme]) map[theme] = [];
      map[theme].push(stock);
    }
    for (const key of Object.keys(map)) {
      map[key].sort((a, b) => {
        const boardDiff = (b.boards || 0) - (a.boards || 0);
        if (boardDiff !== 0) return boardDiff;
        return (b.seal_amount || 0) - (a.seal_amount || 0);
      });
    }
    return map;
  }, [allStocks]);

  const sortedThemeRanking = useMemo(() => {
    const others = [];
    const normal = [];
    for (const t of themeRankingWithLeaders) {
      if (t.theme === '其他概念' || t.theme === '其他') {
        others.push(t);
      } else {
        normal.push(t);
      }
    }
    return [...normal, ...others];
  }, [themeRankingWithLeaders]);

  const dateNav = (
    <div className="page-date-nav">
      <button
        type="button"
        className="date-nav-btn"
        disabled={currentDate <= MIN_ECHELON_DATE}
        onClick={() => setCurrentDate(clampEchelonDate(offsetDate(currentDate, -1)))}
      >
        <LeftOutlined /> 前一天
      </button>
      <div className="page-date-nav-end">
        <button
          type="button"
          className="date-nav-btn"
          disabled={currentDate >= todayStr}
          onClick={() => setCurrentDate(clampEchelonDate(offsetDate(currentDate, 1)))}
        >
          后一天 <RightOutlined />
        </button>
        <span className="date-nav-label">{formatDateDisplay(currentDate)}</span>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="echelon-container">
        {dateNav}
        <div className="loading-container">
          <Spin size="large" />
          <div className="loading-text">加载涨停板梯队...</div>
        </div>
      </div>
    );
  }

  if (!data || !data.echelons || data.echelons.length === 0) {
    return (
      <div className="echelon-container">
        {dateNav}
        <div className="echelon-empty">暂无涨停板数据（收盘后由系统离线生成，请稍后刷新）</div>
      </div>
    );
  }

  return (
    <div className="echelon-container">
      {dateNav}
      <div className="echelon-top-bar">
        <div className="echelon-summary">
          <div className="summary-item">
            <span className="summary-label">涨停</span>
            <span className="summary-value red">{summary?.total || 0}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">首板</span>
            <span className="summary-value blue">{summary?.first_board_count || 0}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">连板</span>
            <span className="summary-value orange">{summary?.consec_count || 0}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">最高</span>
            <span className="summary-value purple">
              {summary?.max_boards || 0}
              <span className="summary-unit">板</span>
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-label">跌停</span>
            <span className="summary-value teal">{summary?.limit_down_count ?? '--'}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">炸板</span>
            <span className="summary-value amber">{summary?.broken_board_count ?? '--'}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">炸板率</span>
            <span className="summary-value amber">
              {summary?.broken_board_rate != null ? `${summary.broken_board_rate}%` : '--'}
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-label">上涨比例</span>
            <span className={`summary-value ${getRisePctClass(summary?.rise_pct)}`}>
              {formatRatePct(summary?.rise_pct)}
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-label">打板成功率</span>
            <span className={`summary-value ${getBoardHitRateClass(summary?.board_hit_rate)}`}>
              {formatRatePct(summary?.board_hit_rate)}
            </span>
          </div>
        </div>
      </div>

      {sortedThemeRanking.length > 0 && (
        <div className="theme-ranking-bar">
          {sortedThemeRanking.map((t) => {
            const leaders = t.leaders || (t.leader?.code ? [t.leader] : []);
            const leaderCodes = new Set(leaders.map((l) => l.code));
            const stocks = stocksByTheme[t.theme] || [];
            const popoverContent = (
              <div className="theme-popover">
                {t.reason && <div className="theme-popover-reason">{t.reason}</div>}
                <div className="theme-popover-list">
                  {stocks.map((stock) => {
                    const leader = leaders.find((l) => l.code === stock.code);
                    const isLeader = leaderCodes.has(stock.code);
                    return (
                      <div key={stock.code} className={`theme-popover-stock ${isLeader ? 'is-leader' : ''}`}>
                        <span className="theme-popover-stock-name">{stock.name}</span>
                        <span className="theme-popover-stock-code">{stock.code}</span>
                        {stock.boards > 1 && (
                          <span className="theme-popover-boards">{stock.boards}板</span>
                        )}
                        {isLeader && (
                          <span className={`theme-popover-role ${leader?.role === '先锋龙' || leader?.role === '先锋' ? 'dragon' : 'general'}`}>
                            {leader?.role || '龙头'}
                          </span>
                        )}
                        <span className="theme-popover-seal">{stock.seal_amount_text}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
            return (
              <Popover
                key={t.theme}
                content={popoverContent}
                title={null}
                placement="bottom"
                overlayClassName="theme-popover-overlay"
                mouseEnterDelay={0.15}
                mouseLeaveDelay={0.1}
              >
                <span className="theme-ranking-item">
                  <span className="theme-ranking-name">{t.theme}</span>
                  <span className="theme-ranking-count">{t.count}</span>
                </span>
              </Popover>
            );
          })}
        </div>
      )}

      {echelons.map((echelon) => {
        const color = getBoardColor(echelon.boards);
        return (
          <div
            key={echelon.boards}
            className="echelon-group"
            style={{ borderLeftColor: color.tag }}
          >
            <div className="echelon-header">
              <Tag color={color.tag} className="echelon-tag">
                {echelon.boards >= 7 ? `${echelon.boards}板` : color.label}
              </Tag>
              <span className="echelon-count">{echelon.count}只</span>
            </div>

            <div className="echelon-table">
              <div className="echelon-table-header">
                <div className="col-name">名称</div>
                <div className="col-theme">题材</div>
                <div className="col-seal">封单额</div>
                <div className="col-ratio">封成比</div>
                <div className="col-turnover">成交额</div>
                <div className="col-rate">换手率</div>
                <div className="col-time">首封时间</div>
                <div className="col-break">炸板</div>
                <div className="col-quality">评级</div>
                <div className="col-reason">涨停原因</div>
              </div>

              {echelon.stocks.map((stock) => {
                const quality = getSealQuality(stock);
                const primary = stock.group_label || stock.theme || stock.industry;
                const themeCount = stock.theme_count || stock.group_count || 0;
                const hasTheme = !!(stock.group_label || stock.theme);
                const thsTag = (stock.ths_hot_tag || '').trim();
                const themeReason =
                  stock.ths_analyse_title ||
                  stock.theme_reason ||
                  themeRankingWithLeaders.find((t) => t.theme === primary)?.reason ||
                  '';
                const rankingTheme = themeRankingWithLeaders.find((t) => t.theme === primary);
                const leaders =
                  stock.theme_leaders ||
                  rankingTheme?.leaders ||
                  (rankingTheme?.leader?.code ? [rankingTheme.leader] : []);
                const isThemeLeader = stock.is_theme_leader || leaders.some((item) => item.code === stock.code);
                const currentLeader = leaders.find((item) => item.code === stock.code);
                const tooltipLines = [
                  stock.ths_analyse && `同花顺：${stock.ths_analyse}`,
                  primary && `题材：${primary}${themeCount > 1 ? `（${themeCount} 家）` : ''}`,
                  themeReason && `涨停原因：${themeReason}`,
                  isThemeLeader && currentLeader?.reason && `龙头理由：${currentLeader.reason}`,
                ].filter(Boolean);
                return (
                  <div
                    key={stock.code}
                    className={`echelon-table-row ${color.rowClass || 'board-1'}`}
                  >
                    <div className="col-name" onClick={() => navigate(`/stock-dashboard?code=${stock.code}`)} style={{ cursor: 'pointer' }}>
                      <span className="stock-name-wrap">
                        <span className="stock-name-line">
                          <span className="stock-name">{stock.name}</span>
                          {stock.ths_rank > 0 ? (
                            <Tooltip
                              title={stock.ths_analyse || stock.ths_analyse_title || ''}
                              placement="right"
                              overlayStyle={{ maxWidth: 400 }}
                            >
                              <span className="ths-rank ths-rank--name">
                                <FireOutlined style={{ color: '#ff4d4f', marginRight: 2 }} />
                                {stock.ths_rank}
                              </span>
                            </Tooltip>
                          ) : null}
                        </span>
                        <span className="stock-code">{stock.code}</span>
                      </span>
                    </div>
                    <div className="col-theme">
                      <Tooltip
                        title={tooltipLines.length ? tooltipLines.join('\n') : '暂无分析'}
                        placement="right"
                        overlayStyle={{ maxWidth: 400 }}
                      >
                        <div className="theme-tags-cell">
                          <span className={`theme-tag ${hasTheme ? 'ai-theme' : ''}`}>
                            {primary}
                            {hasTheme && themeCount > 1 && (
                              <em className="theme-count">{themeCount}</em>
                            )}
                          </span>
                          {thsTag ? (
                            <span className="theme-tag theme-tag--ths" title="同花顺热股标签">
                              {thsTag}
                            </span>
                          ) : null}
                        </div>
                      </Tooltip>
                    </div>
                    <div className="col-seal">
                      <span className="seal-amount">{stock.seal_amount_text}</span>
                    </div>
                    <div className="col-ratio">
                      <span
                        className="seal-ratio"
                        style={{
                          color:
                            stock.seal_ratio >= 10
                              ? '#ff4d4f'
                              : stock.seal_ratio >= 3
                              ? '#faad14'
                              : '#999',
                        }}
                      >
                        {stock.seal_ratio}
                      </span>
                    </div>
                    <div className="col-turnover">{stock.turnover_text}</div>
                    <div className="col-rate">{stock.turnover_rate}%</div>
                    <div className="col-time">
                      <ClockCircleOutlined style={{ marginRight: 4, fontSize: 11 }} />
                      {formatTime(stock.first_time)}
                    </div>
                    <div className="col-break">
                      {stock.break_count > 0 ? (
                        <span className="break-warn">{stock.break_count}次</span>
                      ) : (
                        <span className="break-ok">0</span>
                      )}
                    </div>
                    <div className="col-quality">
                      <span
                        className="quality-badge"
                        style={{ color: quality.color, borderColor: quality.color }}
                      >
                        {quality.label}
                      </span>
                    </div>
                    <div className="col-reason">
                      <Tooltip
                        title={themeReason || stock.ths_analyse || '暂无涨停原因'}
                        placement="left"
                        overlayStyle={{ maxWidth: 520 }}
                      >
                        <span className="theme-reason-text">
                          {themeReason || stock.ths_analyse_title || '--'}
                        </span>
                      </Tooltip>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default LimitUpEchelon;
