import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Spin, Tag, Tooltip, Popover, Button } from 'antd';
import { FireOutlined, ClockCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../config/api';
import './index.css';

const boardColorMap = {
  1: { bg: '#1a2332', border: '#2a4a6b', tag: '#3b82f6', label: '首板' },
  2: { bg: '#1a2f2a', border: '#2a6b4a', tag: '#10b981', label: '2板' },
  3: { bg: '#2a2f1a', border: '#6b6a2a', tag: '#f59e0b', label: '3板' },
  4: { bg: '#2f2a1a', border: '#6b4a2a', tag: '#f97316', label: '4板' },
  5: { bg: '#2f1a1a', border: '#6b2a2a', tag: '#ef4444', label: '5板' },
  6: { bg: '#2f1a2a', border: '#6b2a5a', tag: '#ec4899', label: '6板' },
  7: { bg: '#2a1a2f', border: '#5a2a6b', tag: '#a855f7', label: '7板' },
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
  const timeNum = parseInt(first_time || '150000');
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

function LimitUpEchelon() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);


  const [aiStatus, setAiStatus] = useState('none'); // none | pending | done | error

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // 带 analysis=1：有缓存直接返回完整数据，无缓存触发后台AI并立即返回基础数据
      const res = await apiRequest('/api/v1/limit-up-echelon?analysis=1');
      if (res?.data) {
        setData(res.data);
        const status = res.data.ai?.status || 'none';
        setAiStatus(status);
      }
    } catch (err) {
      console.error('Failed to fetch limit up echelon:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // AI分组轮询：pending 时每2秒查一次
  useEffect(() => {
    if (aiStatus !== 'pending') return;
    const timer = setInterval(async () => {
      try {
        const res = await apiRequest('/api/v1/limit-up-echelon/ai-status');
        if (res?.data?.status === 'done') {
          setAiStatus('done');
          // 合并AI分组到现有数据
          setData((prev) => {
            if (!prev) return prev;
            const themedStocks = res.data.themed_stocks || {};
            const newEchelons = prev.echelons.map((echelon) => ({
              ...echelon,
              stocks: echelon.stocks.map((stock) => {
                const ai = themedStocks[stock.code];
                return ai ? { ...stock, ...ai } : stock;
              }),
            }));
            return {
              ...prev,
              echelons: newEchelons,
              theme_ranking: res.data.theme_ranking || prev.theme_ranking,
              ai: { ...prev.ai, ok: true, status: 'done' },
            };
          });
        } else if (res?.data?.status === 'error') {
          setAiStatus('error');
        }
      } catch (e) {
        console.error('AI status poll failed:', e);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [aiStatus]);

  const echelons = useMemo(() => data?.echelons || [], [data]);
  const summary = data?.summary || {};
  const themedStocks = {};
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

  // 按大标签分组所有股票，并排序（其他概念放最后）
  const stocksByTheme = useMemo(() => {
    const getTheme = (stock) => stock.group_label || stock.theme || stock.industry;
    const map = {};
    for (const stock of allStocks) {
      const theme = getTheme(stock);
      if (!theme) continue;
      if (!map[theme]) map[theme] = [];
      map[theme].push(stock);
    }
    // 按连板高度 > 封单额排序每个组内的股票
    for (const key of Object.keys(map)) {
      map[key].sort((a, b) => {
        const boardDiff = (b.boards || 0) - (a.boards || 0);
        if (boardDiff !== 0) return boardDiff;
        return (b.seal_amount || 0) - (a.seal_amount || 0);
      });
    }
    return map;
  }, [allStocks]);

  // 排序后的主题列表（其他概念放最后）
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

  if (loading) {
    return (
      <div className="echelon-container">
        <div className="loading-container">
          <Spin size="large" tip="加载涨停板梯队..." />
        </div>
      </div>
    );
  }

  if (!data || !data.echelons || data.echelons.length === 0) {
    return (
      <div className="echelon-container">
        <div className="echelon-empty">暂无涨停板数据</div>
      </div>
    );
  }

  return (
    <div className="echelon-container">
      {/* 顶部统计 + AI分析按钮 */}
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
            <span className="summary-value purple">{summary?.max_boards || 0}板</span>
          </div>
          {aiStatus === 'pending' && (
            <div className="summary-item ai-loading">
              <LoadingOutlined style={{ marginRight: 4, color: '#1890ff' }} />
              <span style={{ color: '#1890ff', fontSize: 12 }}>AI分组中...</span>
            </div>
          )}
        </div>
      </div>

      {/* 题材排行 */}
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

      {/* 梯队列表 */}
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
                const stockTheme = themedStocks[stock.code];
                const primary =
                  stock.group_label ||
                  stockTheme?.group_label ||
                  stockTheme?.theme ||
                  stock.theme ||
                  stock.industry;
                const themeCount =
                  stock.theme_count ||
                  stock.group_count ||
                  stockTheme?.theme_count ||
                  0;
                const hasAiGroup = !!(stock.group_label || stock.theme || stockTheme);
                const thsTag = (stock.ths_hot_tag || '').trim();
                const themeReason =
                  stock.ths_analyse_title ||
                  stock.theme_reason ||
                  stockTheme?.theme_reason ||
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
                  primary && `AI 分组：${primary}${themeCount > 1 ? `（${themeCount} 家）` : ''}`,
                  themeReason && `涨停原因：${themeReason}`,
                  isThemeLeader && currentLeader?.reason && `龙头理由：${currentLeader.reason}`,
                ].filter(Boolean);
                return (
                  <div
                    key={stock.code}
                    className="echelon-table-row"
                    style={{ background: color.bg }}
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
                          <span className={`theme-tag ${hasAiGroup ? 'ai-theme' : ''}`}>
                            {primary}
                            {hasAiGroup && themeCount > 1 && (
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
