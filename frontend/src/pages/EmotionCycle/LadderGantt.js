import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Spin } from 'antd';
import { apiRequest } from '../../config/api';
import './LadderGantt.css';

const NAME_COLOR = {
  dark: { main: '#e9edf5', cyb: '#fb923c', kcb: '#c084fc' },
  light: { main: '#1f2a3a', cyb: '#d97706', kcb: '#9333ea' },
};

const PALETTE = {
  dark: {
    text: '#e9edf5', textMuted: '#7b869c', axisFaint: '#5b6678',
    boardHead: '#c8d2e2', grid: '#1c2431', rowAlpha: 0.06,
    namePillFill: 'rgba(16,21,29,.92)',
    brokenFill: '#141a24', brokenStroke: '#3a4356',
  },
  light: {
    text: '#1f2a3a', textMuted: '#64748b', axisFaint: '#94a3b8',
    boardHead: '#334155', grid: '#e2e8f0', rowAlpha: 0.10,
    namePillFill: 'rgba(255,255,255,.96)',
    brokenFill: '#eef2f7', brokenStroke: '#c2ccd8',
  },
};

const readThemeMode = () =>
  (typeof document !== 'undefined' &&
    document.documentElement.getAttribute('data-theme') === 'light')
    ? 'light'
    : 'dark';

function useThemeMode() {
  const [mode, setMode] = useState(readThemeMode);
  useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => setMode(readThemeMode()));
    obs.observe(el, { attributes: true, attributeFilter: ['data-theme'] });
    setMode(readThemeMode());
    return () => obs.disconnect();
  }, []);
  return mode;
}

const BAND_COLORS = [
  '#ef4444', '#f97316', '#a855f7', '#c084fc', '#fb923c',
  '#eab308', '#3b82f6', '#ec4899', '#14b8a6', '#38bdf8',
  '#f43f5e', '#84cc16', '#22d3ee', '#e879f9', '#fbbf24',
];

const STAGE_COLOR = {
  '冰点': '#1677ff', '修复': '#13c2c2', '升温': '#fa8c16',
  '高潮': '#f5222d', '退潮': '#52c41a',
};

const stageBaseColor = (stage) => {
  if (!stage) return '#5b6678';
  const key = String(stage).replace(/期$/, '');
  return STAGE_COLOR[key] || '#5b6678';
};

const hexToRgba = (hex, a) => {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
};

const heat = (pm) => {
  if (pm >= 8) return { fill: '#0e7a3d', stroke: '#1fbf6b' };
  if (pm >= 4) return { fill: '#1f9e57', stroke: '#37d98a' };
  if (pm > 0) return { fill: 'rgba(46,199,122,.32)', stroke: '#37d98a' };
  if (pm > -3) return { fill: 'rgba(239,68,68,.40)', stroke: '#ff6b6b' };
  if (pm > -7) return { fill: '#a83b3b', stroke: '#ff6b6b' };
  return { fill: '#cf3636', stroke: '#ff8a8a' };
};

const PAD_L = 104;
const PAD_T = 72;
const PAD_R = 250;
const COL_W = 150;
const ROW_H = 118;
const NODE_R = 19;
const MIN_BOARD = 2;

const PREVIEW = {
  days: 5,
  dates: [
    { dt: '20260806', display: '08-06', weekday: '周三', stage: '修复期', max_boards: 3, advance_count: 3, consec_count: 20, limit_up_count: 68 },
    { dt: '20260807', display: '08-07', weekday: '周四', stage: '升温期', max_boards: 4, advance_count: 2, consec_count: 18, limit_up_count: 67 },
    { dt: '20260808', display: '08-08', weekday: '周五', stage: '升温期', max_boards: 5, advance_count: 3, consec_count: 22, limit_up_count: 69 },
    { dt: '20260811', display: '08-11', weekday: '周一', stage: '高潮期', max_boards: 6, advance_count: 4, consec_count: 25, limit_up_count: 67 },
    { dt: '20260812', display: '08-12', weekday: '周二', stage: '高潮期', max_boards: 7, advance_count: 4, consec_count: 23, limit_up_count: 66 },
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

function LadderGantt({ preview = false }) {
  const mode = useThemeMode();
  const pal = PALETTE[mode];
  const nameColor = NAME_COLOR[mode];
  const [days, setDays] = useState(5);
  const [data, setData] = useState(preview ? PREVIEW : null);
  const [loading, setLoading] = useState(!preview);

  const fetchData = useCallback(async () => {
    if (preview) return;
    setLoading(true);
    try {
      const res = await apiRequest(`/api/v1/limit-up-ladder?days=${days}`);
      if (res?.data) setData(res.data);
    } catch (err) {
      console.error('Failed to fetch ladder data:', err);
      setData({ days, dates: [], stocks: [] });
    } finally {
      setLoading(false);
    }
  }, [days, preview]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const dates = data?.dates || [];
  const stocks = data?.stocks || [];

  const ganttStocks = useMemo(() => stocks
    .map((s) => ({
      ...s,
      cells: s.cells.filter((c) => c.boards >= MIN_BOARD || c.status === 'broken'),
    }))
    .filter((s) => s.cells.some((c) => c.boards >= MIN_BOARD)), [stocks]);

  const boards = useMemo(() => {
    let lo = MIN_BOARD;
    let hi = MIN_BOARD;
    ganttStocks.forEach((s) => s.cells.forEach((c) => {
      if (c.boards >= MIN_BOARD) {
        lo = Math.min(lo, c.boards);
        hi = Math.max(hi, c.boards);
      }
    }));
    if (hi < lo) hi = lo;
    const list = [];
    for (let b = lo; b <= hi; b += 1) list.push(b);
    return list;
  }, [ganttStocks]);

  const loBoard = boards[0] || MIN_BOARD;

  const dtIndex = useMemo(() => {
    const map = {};
    dates.forEach((d, i) => { map[d.dt] = i; });
    return map;
  }, [dates]);

  const plotW = boards.length * COL_W;
  const plotH = dates.length * ROW_H;
  const W = PAD_L + plotW + PAD_R;
  const H = PAD_T + plotH + 34;

  const xc = (b) => PAD_L + (b - loBoard) * COL_W + COL_W / 2;
  const yc = (r) => PAD_T + r * ROW_H + ROW_H / 2;

  const groupCount = {};
  const groupSeen = {};
  ganttStocks.forEach((s) => s.cells.forEach((c) => {
    if (c.boards < MIN_BOARD && c.status !== 'broken') return;
    const r = dtIndex[c.dt];
    if (r == null) return;
    const k = `${r}_${c.boards}`;
    groupCount[k] = (groupCount[k] || 0) + 1;
  }));

  const nodeDx = (r, b) => {
    const k = `${r}_${b}`;
    const n = groupCount[k] || 1;
    if (n <= 1) return 0;
    const idx = groupSeen[k] || 0;
    groupSeen[k] = idx + 1;
    return (idx - (n - 1) / 2) * 42;
  };

  const renderReady = !loading && dates.length > 0;

  return (
    <div className="ladder-gantt">
      <div className="ladder-head">
        <span className="ladder-title">连板情绪溢价表</span>
        <span className="ladder-badge">情绪周期 · 天梯甘特</span>
        {!preview && (
          <span className="ladder-switch">
            {[5, 10].map((d) => (
              <span
                key={d}
                className={days === d ? 'on' : ''}
                onClick={() => setDays(d)}
              >近{d}日</span>
            ))}
          </span>
        )}
      </div>
      <div className="ladder-sub">
        纵轴＝时间（上旧下新，带周期）· 横轴＝连板板数（2板起，左低→右越高）· 一只票一条斜带 ·
        节点色＝次日溢价（绿赚 红亏 黑跌停）· 名字色：白主板 橙创业板 紫科创板
      </div>

      {loading && (
        <div className="ladder-loading"><Spin tip="加载中..." /></div>
      )}
      {!loading && dates.length === 0 && (
        <div className="ladder-empty">暂无梯队数据</div>
      )}

      {renderReady && (
        <div className="ladder-scroll">
          <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
            {dates.map((dt, r) => (
              <rect key={`bg${r}`} x={PAD_L} y={PAD_T + r * ROW_H} width={plotW} height={ROW_H}
                fill={hexToRgba(stageBaseColor(dt.stage), pal.rowAlpha)} />
            ))}

            {boards.map((b, i) => (
              <line key={`v${i}`} x1={PAD_L + i * COL_W} y1={PAD_T} x2={PAD_L + i * COL_W}
                y2={PAD_T + plotH} stroke={pal.grid} strokeWidth={1} />
            ))}
            <line x1={PAD_L + plotW} y1={PAD_T} x2={PAD_L + plotW} y2={PAD_T + plotH}
              stroke={pal.grid} strokeWidth={1} />
            {dates.map((dt, r) => (
              <line key={`h${r}`} x1={PAD_L} y1={PAD_T + r * ROW_H} x2={PAD_L + plotW}
                y2={PAD_T + r * ROW_H} stroke={pal.grid} strokeWidth={1} />
            ))}
            <line x1={PAD_L} y1={PAD_T + plotH} x2={PAD_L + plotW} y2={PAD_T + plotH}
              stroke={pal.grid} strokeWidth={1} />

            {boards.map((b) => (
              <text key={`bh${b}`} x={xc(b)} y={PAD_T - 26} fill={pal.boardHead} fontSize={14}
                fontWeight={700} textAnchor="middle">{b}板</text>
            ))}
            <text x={PAD_L + plotW - 4} y={PAD_T - 46} fill={pal.axisFaint} fontSize={11}
              textAnchor="end">板数越高 →</text>
            <text x={20} y={PAD_T - 46} fill={pal.axisFaint} fontSize={11}>时间</text>

            {dates.map((dt, r) => {
              const y = yc(r);
              const col = stageBaseColor(dt.stage);
              const label = (dt.stage || '').replace(/期$/, '') || '—';
              const pillW = label.length * 11 + 12;
              return (
                <g key={`dl${r}`}>
                  <text x={52} y={y - 14} fill={pal.text} fontSize={14} fontWeight={700}
                    textAnchor="middle">{dt.display}</text>
                  <text x={52} y={y + 2} fill={pal.textMuted} fontSize={10.5}
                    textAnchor="middle">{dt.weekday}</text>
                  <rect x={52 - pillW / 2} y={y + 11} width={pillW} height={16} rx={8}
                    fill={hexToRgba(col, 0.14)} />
                  <text x={52} y={y + 22} fill={col} fontSize={10.5} fontWeight={600}
                    textAnchor="middle">{label}</text>
                </g>
              );
            })}

            {dates.map((dt, r) => {
              const y = yc(r);
              const sx = PAD_L + plotW + 18;
              return (
                <g key={`st${r}`}>
                  <text x={sx} y={y - 16} fill="#c084fc" fontSize={12.5} fontWeight={700}>
                    最高 {dt.max_boards}板
                  </text>
                  <text x={sx} y={y + 4} fill="#38e07b" fontSize={11.5}>
                    晋级 {dt.advance_count == null ? '—' : dt.advance_count} 家
                  </text>
                  <text x={sx + 92} y={y + 4} fill="#fa9f3c" fontSize={11.5}>
                    连板 {dt.consec_count}
                  </text>
                  <text x={sx} y={y + 22} fill="#ff5a63" fontSize={11.5}>
                    涨停 {dt.limit_up_count} 家
                  </text>
                </g>
              );
            })}

            {ganttStocks.map((s, si) => {
              const color = BAND_COLORS[si % BAND_COLORS.length];
              const pts = s.cells
                .map((c) => {
                  const r = dtIndex[c.dt];
                  if (r == null) return null;
                  if (c.boards < MIN_BOARD && c.status !== 'broken') return null;
                  return { c, r, x: xc(c.boards) + nodeDx(r, c.boards), y: yc(r) };
                })
                .filter(Boolean);
              if (!pts.length) return null;
              const polyStr = pts.map((p) => `${p.x},${p.y}`).join(' ');
              const last = pts[pts.length - 1];
              const topBoard = (s.cells.filter((c) => c.status !== 'broken').slice(-1)[0] || {}).boards || s.max_boards;
              const lastBroken = last.c.status === 'broken';
              const label = `${s.name} 【${lastBroken ? '断板' : `${topBoard}板`}】`;
              const pillW = label.length * 12.6 + 16;
              const nameY = last.y - 34;
              return (
                <g key={s.code}>
                  <polyline points={polyStr} fill="none" stroke={color} strokeWidth={4}
                    strokeLinejoin="round" strokeLinecap="round" opacity={0.4} />
                  {pts.map((p, pi) => {
                    const { c, x, y } = p;
                    if (c.status === 'broken') {
                      return (
                        <g key={pi}>
                          <circle cx={x} cy={y} r={17} fill={pal.brokenFill} stroke={pal.brokenStroke}
                            strokeWidth={1.5} strokeDasharray="3 3" />
                          <text x={x} y={y + 4} fill="#ff8a5b" fontSize={12} fontWeight={700}
                            textAnchor="middle">断</text>
                        </g>
                      );
                    }
                    if (c.status === 'limit_down') {
                      return (
                        <g key={pi}>
                          <circle cx={x} cy={y} r={NODE_R} fill="#0a0a0a" stroke="#ff4d4f"
                            strokeWidth={2} />
                          <text x={x} y={y + 4} fill="#ff6b6b" fontSize={10} fontWeight={800}
                            textAnchor="middle">跌停</text>
                        </g>
                      );
                    }
                    const pending = c.status === 'pending' || c.premium == null;
                    const h = pending
                      ? { fill: 'rgba(120,130,150,.22)', stroke: '#6b7688' }
                      : heat(c.premium);
                    return (
                      <g key={pi}>
                        <circle cx={x} cy={y} r={NODE_R} fill={h.fill} stroke={h.stroke}
                          strokeWidth={2} />
                        <text x={x} y={y - 1} fill="#fff" fontSize={15} fontWeight={800}
                          textAnchor="middle">{c.boards}</text>
                        <text x={x} y={y + 11} fill="#dbe4f0" fontSize={8}
                          textAnchor="middle">板</text>
                        {!pending && (
                          <text x={x + 22} y={y + 3} fill={c.premium > 0 ? '#7CFFB0' : '#ffb3b3'}
                            fontSize={10} fontWeight={700}>
                            {(c.premium > 0 ? '+' : '') + c.premium}
                          </text>
                        )}
                      </g>
                    );
                  })}
                  <rect x={last.x - pillW / 2} y={nameY - 14} width={pillW} height={20} rx={9}
                    fill={pal.namePillFill} stroke={color} strokeWidth={1.2} />
                  <text x={last.x} y={nameY} fill={nameColor[s.market] || nameColor.main}
                    fontSize={12.5} fontWeight={700} textAnchor="middle">{label}</text>
                </g>
              );
            })}
          </svg>
        </div>
      )}

      <div className="ladder-legend">
        <span><i className="lg-sw" style={{ background: '#1f9e57' }} />赚钱效应（次日上涨）</span>
        <span><i className="lg-sw" style={{ background: '#a83b3b' }} />亏钱效应（次日下跌）</span>
        <span><i className="lg-sw" style={{ background: '#0a0a0a', border: '1px solid #ff4d4f' }} />跌停·吹哨</span>
        <span style={{ color: '#fb923c' }}>橙＝创业板</span>
        <span style={{ color: '#c084fc' }}>紫＝科创板</span>
        <span>斜带越长＝连板越高</span>
      </div>
    </div>
  );
}

export default LadderGantt;
