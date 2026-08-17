import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Spin } from 'antd';
import { apiRequest } from '../../config/api';
import { LadderHoverPopover } from './LadderHoverPopover';
import './LadderGantt.css';

const MARKET_LABEL = { cyb: '创', kcb: '科', main: '' };

// 情绪周期配色（键与后端 stage 去「期」后一致）
const STAGE_COLOR = {
  '冰点': '#94a3b8', '修复': '#0d9488', '升温': '#7c3aed',
  '高潮': '#e11d48', '退潮': '#d97706',
};
const CYCLE_ORDER = ['冰点', '修复', '升温', '高潮', '退潮'];

const stageKey = (stage) => (stage ? String(stage).replace(/期$/, '') : '');
const stageFull = (stage) => { const k = stageKey(stage); return k ? `${k}期` : ''; };
const stageBaseColor = (stage) => STAGE_COLOR[stageKey(stage)] || '#5b6678';

const hexToRgba = (hex, a) => {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
};

// 卡片底色/描边/溢价文字色，按次日溢价强弱分档（红涨绿跌）
const premiumTint = (pm) => {
  if (pm >= 8) return { bg: 'rgba(207,54,54,.34)', bd: '#ff6b6b', pv: '#ff8a8a' };
  if (pm >= 4) return { bg: 'rgba(207,54,54,.24)', bd: 'rgba(255,107,107,.6)', pv: '#ff6b6b' };
  if (pm > 0) return { bg: 'rgba(239,68,68,.13)', bd: 'rgba(255,107,107,.42)', pv: '#ff8080' };
  if (pm > -3) return { bg: 'rgba(46,199,122,.13)', bd: 'rgba(55,217,138,.42)', pv: '#37d98a' };
  if (pm > -7) return { bg: 'rgba(31,158,87,.22)', bd: 'rgba(55,217,138,.6)', pv: '#37d98a' };
  return { bg: 'rgba(31,158,87,.34)', bd: '#37d98a', pv: '#4ade80' };
};

const MIN_BOARD = 2;
const LIVE_POLL_SEC = 60;

// 网格几何（与 CSS 变量保持一致，用于能量线定位）
const AXIS_W = 96;
const COL_W = 184;
const ROWH = 84;

const PREVIEW = {
  days: 5,
  dates: [
    { dt: '20260806', display: '08-06', weekday: '周三', stage: '修复期', max_boards: 3, advance_count: 3, consec_count: 20, limit_up_count: 68, rise_count: 2610, fall_count: 1980, broken_board_count: 14 },
    { dt: '20260807', display: '08-07', weekday: '周四', stage: '升温期', max_boards: 4, advance_count: 2, consec_count: 18, limit_up_count: 67, rise_count: 2890, fall_count: 1760, broken_board_count: 16 },
    { dt: '20260808', display: '08-08', weekday: '周五', stage: '升温期', max_boards: 5, advance_count: 3, consec_count: 22, limit_up_count: 69, rise_count: 3010, fall_count: 1650, broken_board_count: 18 },
    { dt: '20260811', display: '08-11', weekday: '周一', stage: '高潮期', max_boards: 6, advance_count: 4, consec_count: 25, limit_up_count: 67, rise_count: 3120, fall_count: 1580, broken_board_count: 19 },
    { dt: '20260812', display: '08-12', weekday: '周二', stage: '高潮期', max_boards: 7, advance_count: 4, consec_count: 23, limit_up_count: 66, rise_count: 3260, fall_count: 1490, broken_board_count: 22 },
  ],
  stocks: (() => {
    const D = ['20260806', '20260807', '20260808', '20260811', '20260812'];
    const c = (r, b, premium, status) => ({ dt: D[r], boards: b, premium, status });
    return [
      { code: '600501', name: '航天晨光', theme: '军工', market: 'main', max_boards: 7,
        cells: [c(0, 3, 6.6, 'up'), c(1, 4, 5.2, 'up'), c(2, 5, 3.1, 'up'), c(3, 6, -4.8, 'down'), c(4, 7, -10, 'limit_down')] },
      { code: '002413', name: '雷科防务', theme: '军工', market: 'main', max_boards: 5,
        cells: [c(1, 2, 4.9, 'up'), c(2, 3, 1.3, 'up'), c(3, 4, -3.9, 'down'), c(4, 5, -8.2, 'down')] },
      { code: '600685', name: '中船应急', theme: '船舶', market: 'main', max_boards: 4,
        cells: [c(2, 2, 10.0, 'up'), c(3, 3, 7.5, 'up'), c(4, 4, -6.1, 'down')] },
      { code: '688525', name: '佰维存储', theme: 'HBM', market: 'kcb', max_boards: 3,
        cells: [c(3, 2, 2.0, 'up'), c(4, 3, 3.9, 'up')] },
      { code: '301029', name: '华丰科技', theme: '机器人', market: 'cyb', max_boards: 3,
        cells: [c(3, 2, 2.9, 'up'), c(4, 3, -1.4, 'down')] },
      { code: '001259', name: '利仁科技', theme: '大消费', market: 'main', max_boards: 3,
        cells: [c(2, 2, 1.3, 'up'), c(3, 3, 0.6, 'up'), c(4, 3, null, 'broken')] },
      { code: '002999', name: '广电计量', theme: '检测', market: 'main', max_boards: 2,
        cells: [c(0, 2, 2.2, 'up'), c(1, 2, null, 'broken')] },
      { code: '002917', name: '金奥博', theme: '民爆', market: 'main', max_boards: 2,
        cells: [c(0, 2, 0.8, 'up'), c(1, 2, null, 'broken')] },
    ];
  })(),
};

const fmtPrem = (prem) => ((prem > 0 ? '+' : '') + prem);

// 单只票在某天某板位的卡片（单行 chip：名字 + 溢价）
function LadderCard({ code, name, market, cell, peak = false, preview = false }) {
  const marketTag = MARKET_LABEL[market] || '';
  const nameCls = `lb-name lb-mk-${market || 'main'}`;
  const peakCls = peak ? ' lb-peak' : '';

  const wrap = (card) => (
    <LadderHoverPopover code={code} name={name} disabled={preview}>
      {card}
    </LadderHoverPopover>
  );

  if (cell.status === 'broken') {
    const hasChg = cell.premium != null;
    return wrap(
      <div className={`lb-chip lb-broken${peakCls}`} title={`${name} 断板${hasChg ? ` ${fmtPrem(cell.premium)}%` : ''}`}>
        <span className={nameCls}>{name}</span>
        <span className="lb-chip-r">
          <span className="lb-brk">断板</span>
          {hasChg && (
            <span className="lb-prem" style={{ color: premiumTint(cell.premium).pv }}>{fmtPrem(cell.premium)}</span>
          )}
        </span>
      </div>,
    );
  }
  if (cell.status === 'limit_down') {
    return wrap(
      <div className={`lb-chip lb-limitdown${peakCls}`} title={`${name} 跌停`}>
        <span className={nameCls}>{name}</span>
        <span className="lb-ld">跌停</span>
      </div>,
    );
  }
  const isLive = cell.live === true;
  const pending = !isLive && (cell.status === 'pending' || cell.premium == null);
  const tint = pending
    ? { bg: 'transparent', bd: 'var(--lb-pending-bd)', pv: 'var(--lb-muted)' }
    : premiumTint(cell.premium);
  const chgLabel = isLive ? '盘中' : '收盘';
  return wrap(
    <div className={`lb-chip${peakCls}`} style={{ background: tint.bg, borderColor: tint.bd }}
      title={`${name} ${cell.boards}板 ${pending ? '待揭晓' : `${chgLabel} ${fmtPrem(cell.premium)}%`}`}>
      <span className={nameCls}>{name}{marketTag && <i className="lb-mktag">{marketTag}</i>}</span>
      <span className={`lb-prem${isLive ? ' lb-prem-live' : ''}`} style={{ color: tint.pv }}>
        {pending ? '待' : fmtPrem(cell.premium)}
      </span>
    </div>,
  );
}

function LadderGantt({ preview = false }) {
  const [days, setDays] = useState(10);
  const [data, setData] = useState(preview ? PREVIEW : null);
  const [loading, setLoading] = useState(!preview);
  const pollRef = useRef(null);
  const scrollRef = useRef(null);

  const fetchData = useCallback(async (options = {}) => {
    const { silent = false, live = false } = options;
    if (preview) return;
    if (!silent) setLoading(true);
    try {
      const qs = live ? '&live=1' : '';
      const res = await apiRequest(`/api/v1/limit-up-ladder?days=${days}${qs}`);
      if (res?.data) setData(res.data);
    } catch (err) {
      console.error('Failed to fetch ladder data:', err);
      if (!silent) setData({ days, dates: [], stocks: [] });
    } finally {
      if (!silent) setLoading(false);
    }
  }, [days, preview]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (preview || !data?.is_newest_today || !data?.market_hours) return undefined;

    pollRef.current = setInterval(() => {
      fetchData({ silent: true, live: true });
    }, LIVE_POLL_SEC * 1000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [preview, data?.is_newest_today, data?.market_hours, fetchData]);

  const dates = useMemo(() => data?.dates || [], [data]);
  const stocks = useMemo(() => data?.stocks || [], [data]);

  // 只保留 >=2板 或断板的格子
  const cleanStocks = useMemo(() => stocks
    .map((s) => ({
      ...s,
      cells: s.cells.filter((c) => c.boards >= MIN_BOARD || c.status === 'broken'),
    }))
    .filter((s) => s.cells.some((c) => c.boards >= MIN_BOARD)), [stocks]);

  // 板位（从高到低）：2板..最高板
  const boardsDesc = useMemo(() => {
    let hi = MIN_BOARD;
    cleanStocks.forEach((s) => s.cells.forEach((c) => {
      if (c.boards >= MIN_BOARD) hi = Math.max(hi, c.boards);
    }));
    dates.forEach((d) => { if ((d.max_boards || 0) >= MIN_BOARD) hi = Math.max(hi, d.max_boards); });
    const list = [];
    for (let b = hi; b >= MIN_BOARD; b -= 1) list.push(b);
    return list;
  }, [cleanStocks, dates]);

  // 行序（上→下）：高板..2板..首板；首板行数 = boardsDesc.length
  const nLevelRows = boardsDesc.length + 1; // + 首板 行
  const firstRowIdx = boardsDesc.length;
  const levelRowIndex = useCallback((boards) => {
    if (!boards || boards <= 1) return firstRowIdx;
    const i = boardsDesc.indexOf(boards);
    return i >= 0 ? i : 0;
  }, [boardsDesc, firstRowIdx]);

  // 索引：`${dt}_${board}` -> 该格个股列表
  const grid = useMemo(() => {
    const map = {};
    cleanStocks.forEach((s) => s.cells.forEach((c) => {
      if (c.boards < MIN_BOARD && c.status !== 'broken') return;
      const key = `${c.dt}_${c.boards}`;
      (map[key] || (map[key] = [])).push({ code: s.code, name: s.name, market: s.market, cell: c });
    }));
    const rank = (item) => {
      const { cell } = item;
      if (cell.status === 'broken') return -1e6;
      if (cell.status === 'limit_down') return -1e5;
      if (cell.status === 'pending' || cell.premium == null) return -1e4;
      if (cell.live) return cell.premium + 1e3;
      return cell.premium;
    };
    Object.values(map).forEach((arr) => arr.sort((a, b) => rank(b) - rank(a)));
    return map;
  }, [cleanStocks]);

  // 每日龙头 chip（当日最高板格子内排名第一的票）加紫色 glow
  const peakSet = useMemo(() => {
    const set = new Set();
    dates.forEach((d) => {
      const top = grid[`${d.dt}_${d.max_boards}`];
      if (top && top.length) set.add(`${d.dt}-${top[0].code}`);
    });
    return set;
  }, [dates, grid]);

  // 峰值出现过的板位（axis 高亮）
  const peakLevels = useMemo(() => new Set(dates.map((d) => d.max_boards)), [dates]);

  // 能量线路径 + 节点
  const thread = useMemo(() => {
    if (!dates.length || !nLevelRows) return null;
    const pts = dates.map((d, i) => ({
      x: AXIS_W + i * COL_W + COL_W / 2,
      y: levelRowIndex(d.max_boards) * ROWH + ROWH / 2,
    }));
    let path = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 1; i < pts.length; i += 1) {
      const prev = pts[i - 1];
      const cur = pts[i];
      const midX = (prev.x + cur.x) / 2;
      path += ` C ${midX} ${prev.y}, ${midX} ${cur.y}, ${cur.x} ${cur.y}`;
    }
    return {
      path,
      pts,
      width: AXIS_W + dates.length * COL_W,
      height: nLevelRows * ROWH,
    };
  }, [dates, nLevelRows, levelRowIndex]);

  const renderReady = !loading && dates.length > 0 && boardsDesc.length > 0;

  // 数据就绪后滚动到最新（最右）
  useEffect(() => {
    if (!renderReady || !scrollRef.current) return;
    scrollRef.current.scrollTo({ left: scrollRef.current.scrollWidth, behavior: 'auto' });
  }, [renderReady, dates.length]);

  const scrollBy = (dir) => {
    if (scrollRef.current) scrollRef.current.scrollBy({ left: dir * COL_W * 2, behavior: 'smooth' });
  };
  const jumpLatest = () => {
    if (scrollRef.current) scrollRef.current.scrollTo({ left: scrollRef.current.scrollWidth, behavior: 'smooth' });
  };

  // 首板数（涨停总数 - 连板数）
  const firstBoardCount = (dt) => {
    if (dt.limit_up_count == null || dt.consec_count == null) return null;
    return Math.max(0, dt.limit_up_count - dt.consec_count);
  };

  const gridStyle = {
    gridTemplateColumns: `${AXIS_W}px repeat(${dates.length}, ${COL_W}px)`,
    '--lb-rowh': `${ROWH}px`,
  };
  const bandAlpha = 0.16;
  const cellTint = (stage) => hexToRgba(stageBaseColor(stage), bandAlpha);

  return (
    <div className="ladder-gantt">
      <div className="ladder-head">
        <span className="ladder-title">连板情绪溢价表</span>
        <span className="ladder-badge">情绪周期 · 连板天梯 — 龙头能量线</span>
        {!preview && (
          <span className="ladder-switch">
            {[10, 30].map((d) => (
              <span key={d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>
                近{d}日
              </span>
            ))}
          </span>
        )}
        {!preview && data?.is_newest_today && data?.market_hours && (
          <span className="ladder-live-hint">盘中实时 · {LIVE_POLL_SEC}s</span>
        )}
      </div>

      <div className="ladder-legend">
        <span><i className="lg-dot" style={{ background: '#cf3636' }} />次日上涨（赚钱效应）</span>
        <span><i className="lg-dot" style={{ background: '#1f9e57' }} />次日下跌（亏钱效应）</span>
        <span><i className="lg-dot lg-thread" />当日龙头 · 能量线节点</span>
        <span><i className="lg-dot" style={{ background: '#1f2937' }} />炸板（触板未封）</span>
        <span><i className="lg-dot" style={{ background: '#2f5ced' }} />首板数 / 涨跌家数（仅计数）</span>
        <span style={{ color: '#fb923c' }}>橙＝创业板</span>
        <span style={{ color: '#c084fc' }}>紫＝科创板</span>
      </div>

      <div className="ladder-cycle-legend">
        <span className="lb-cyc-label">情绪周期：</span>
        {CYCLE_ORDER.map((name, i) => (
          <React.Fragment key={name}>
            <span className="lb-cyc-chip" style={{ color: STAGE_COLOR[name], background: hexToRgba(STAGE_COLOR[name], 0.14) }}>
              <i className="lg-dot" style={{ background: STAGE_COLOR[name] }} />{name}期
            </span>
            {i < CYCLE_ORDER.length - 1 && <span className="lb-cyc-arrow">→</span>}
          </React.Fragment>
        ))}
      </div>

      {loading && (
        <div className="ladder-loading"><Spin tip="加载中..." /></div>
      )}
      {!loading && dates.length === 0 && (
        <div className="ladder-empty">暂无梯队数据</div>
      )}

      {renderReady && (
        <div className="ladder-stage">
          <button className="lb-nav lb-nav-left" onClick={() => scrollBy(-1)} aria-label="向左">‹</button>
          <button className="lb-nav lb-nav-right" onClick={() => scrollBy(1)} aria-label="向右">›</button>
          <button className="lb-nav lb-jump" onClick={jumpLatest}>跳到最新 ›</button>
          <div className="lb-edge lb-edge-left" />
          <div className="lb-edge lb-edge-right" />

          <div className="ladder-scroll" ref={scrollRef}>
            <div className="lb-grid" style={gridStyle}>
              {thread && (
                <svg className="lb-thread" width={thread.width} height={thread.height}
                  style={{ width: thread.width, height: thread.height }}>
                  <defs>
                    <linearGradient id="lbThreadGrad" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#a78bfa" />
                      <stop offset="100%" stopColor="#6d28d9" />
                    </linearGradient>
                  </defs>
                  <path className="lb-thread-path" d={thread.path} />
                  {thread.pts.map((p, i) => {
                    const isLast = i === thread.pts.length - 1;
                    return (
                      <g key={dates[i].dt}>
                        {isLast && (
                          <circle cx={p.x} cy={p.y} r={6} className="lb-thread-node lb-thread-pulse">
                            <animate attributeName="r" values="6;13;6" dur="2.2s" repeatCount="indefinite" />
                            <animate attributeName="opacity" values="0.6;0;0.6" dur="2.2s" repeatCount="indefinite" />
                          </circle>
                        )}
                        <circle cx={p.x} cy={p.y} r={isLast ? 6 : 5}
                          className={`lb-thread-node${isLast ? ' today' : ''}`} />
                      </g>
                    );
                  })}
                </svg>
              )}

              {/* 板位行：高板 → 2板 */}
              {boardsDesc.map((b) => (
                <React.Fragment key={`row-${b}`}>
                  <div className={`lb-axis lb-axis-lvl${peakLevels.has(b) ? ' peak' : ''}`}>{b}板</div>
                  {dates.map((d) => {
                    const items = grid[`${d.dt}_${b}`] || [];
                    const shown = items.slice(0, 4);
                    const rest = items.length - shown.length;
                    return (
                      <div key={`${d.dt}-${b}`} className={`lb-cell lb-cell-lvl${items.length ? '' : ' empty'}`}
                        style={{ background: cellTint(d.stage) }}>
                        {shown.map((it, idx) => (
                          <LadderCard key={`${it.code}-${idx}`} code={it.code} name={it.name}
                            market={it.market} cell={it.cell} preview={preview}
                            peak={peakSet.has(`${d.dt}-${it.code}`)} />
                        ))}
                        {rest > 0 && <div className="lb-more">+{rest} 更多</div>}
                      </div>
                    );
                  })}
                </React.Fragment>
              ))}

              {/* 首板行（计数） */}
              <div className="lb-axis lb-axis-first">首板</div>
              {dates.map((d) => {
                const fb = firstBoardCount(d);
                return (
                  <div key={`first-${d.dt}`} className="lb-cell lb-cell-lvl" style={{ background: cellTint(d.stage) }}>
                    <div className="lb-count">首板 · {fb == null ? '—' : fb}</div>
                  </div>
                );
              })}

              {/* 日期脚注行 */}
              <div className="lb-axis lb-axis-corner">日期 / 周期</div>
              {dates.map((d, i) => {
                const col = stageBaseColor(d.stage);
                const isLast = i === dates.length - 1;
                return (
                  <div key={`foot-${d.dt}`} className={`lb-foot${isLast ? ' today' : ''}`}
                    style={{ borderTopColor: col, background: cellTint(d.stage) }}>
                    <div className="lb-foot-date">{d.display}</div>
                    <div className="lb-foot-wd">{d.weekday}</div>
                    <div className="lb-foot-cyc" style={{ color: col, background: hexToRgba(col, 0.16) }}>
                      {stageFull(d.stage) || '—'}
                    </div>
                    <div className="lb-foot-stats">
                      <span>涨停 <b>{d.limit_up_count ?? '—'}</b>　连板 <b>{d.consec_count ?? '—'}</b>　炸板 <b>{d.broken_board_count ?? '—'}</b></span>
                      {(d.rise_count != null && d.fall_count != null) && (
                        <span>
                          <b style={{ color: '#cf3636' }}>涨 {d.rise_count}</b>
                          {'　'}
                          <b style={{ color: '#1f9e57' }}>跌 {d.fall_count}</b>
                          {d.fall_count > 0 && `　比 ${(d.rise_count / d.fall_count).toFixed(2)}`}
                        </span>
                      )}
                      <span className="lb-foot-peak">最高 {d.max_boards}板 ▲</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default LadderGantt;
