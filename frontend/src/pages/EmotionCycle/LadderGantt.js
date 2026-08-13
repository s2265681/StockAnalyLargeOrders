import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Spin } from 'antd';
import { apiRequest } from '../../config/api';
import './LadderGantt.css';

const MARKET_LABEL = { cyb: '创', kcb: '科', main: '' };

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

// 卡片底色/描边/溢价文字色，按次日溢价强弱分档
const premiumTint = (pm) => {
  if (pm >= 8) return { bg: 'rgba(31,158,87,.34)', bd: '#37d98a', pv: '#4ade80' };
  if (pm >= 4) return { bg: 'rgba(31,158,87,.22)', bd: 'rgba(55,217,138,.6)', pv: '#37d98a' };
  if (pm > 0) return { bg: 'rgba(46,199,122,.13)', bd: 'rgba(55,217,138,.42)', pv: '#37d98a' };
  if (pm > -3) return { bg: 'rgba(239,68,68,.13)', bd: 'rgba(255,107,107,.42)', pv: '#ff8080' };
  if (pm > -7) return { bg: 'rgba(207,54,54,.24)', bd: 'rgba(255,107,107,.6)', pv: '#ff6b6b' };
  return { bg: 'rgba(207,54,54,.34)', bd: '#ff6b6b', pv: '#ff8a8a' };
};

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

// 单只票在某天某板位的卡片
function LadderCard({ name, market, cell }) {
  const marketTag = MARKET_LABEL[market] || '';
  const nameCls = `lb-name lb-mk-${market || 'main'}`;

  if (cell.status === 'broken') {
    return (
      <div className="lb-card lb-broken" title={`${name} 断板`}>
        <div className={nameCls}>{name}</div>
        <div className="lb-meta"><span className="lb-brk">断板</span></div>
      </div>
    );
  }
  if (cell.status === 'limit_down') {
    return (
      <div className="lb-card lb-limitdown" title={`${name} 跌停`}>
        <div className={nameCls}>{name}</div>
        <div className="lb-meta">
          <span className="lb-b">{cell.boards}板</span>
          <span className="lb-ld">跌停</span>
        </div>
      </div>
    );
  }
  const pending = cell.status === 'pending' || cell.premium == null;
  const tint = pending ? { bg: 'transparent', bd: 'var(--lb-pending-bd)', pv: 'var(--lb-muted)' } : premiumTint(cell.premium);
  return (
    <div className="lb-card" style={{ background: tint.bg, borderColor: tint.bd }}
      title={`${name} ${cell.boards}板 ${pending ? '待揭晓' : (cell.premium > 0 ? '+' : '') + cell.premium + '%'}`}>
      <div className={nameCls}>{name}{marketTag && <i className="lb-mktag">{marketTag}</i>}</div>
      <div className="lb-meta">
        <span className="lb-b">{cell.boards}板</span>
        <span className="lb-prem" style={{ color: tint.pv }}>
          {pending ? '待' : (cell.premium > 0 ? '+' : '') + cell.premium}
        </span>
      </div>
    </div>
  );
}

function LadderGantt({ preview = false }) {
  const mode = useThemeMode();
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

  // 只保留 >=2板 或断板的格子
  const cleanStocks = useMemo(() => stocks
    .map((s) => ({
      ...s,
      cells: s.cells.filter((c) => c.boards >= MIN_BOARD || c.status === 'broken'),
    }))
    .filter((s) => s.cells.some((c) => c.boards >= MIN_BOARD)), [stocks]);

  // 板位列：从高到低（龙头梯队在左）
  const boardsDesc = useMemo(() => {
    let lo = MIN_BOARD;
    let hi = MIN_BOARD;
    cleanStocks.forEach((s) => s.cells.forEach((c) => {
      if (c.boards >= MIN_BOARD) {
        lo = Math.min(lo, c.boards);
        hi = Math.max(hi, c.boards);
      }
    }));
    if (hi < lo) hi = lo;
    const list = [];
    for (let b = hi; b >= lo; b -= 1) list.push(b);
    return list;
  }, [cleanStocks]);

  // 索引：`${dt}_${board}` -> 该格个股列表
  const grid = useMemo(() => {
    const map = {};
    cleanStocks.forEach((s) => s.cells.forEach((c) => {
      if (c.boards < MIN_BOARD && c.status !== 'broken') return;
      const key = `${c.dt}_${c.boards}`;
      (map[key] || (map[key] = [])).push({ name: s.name, market: s.market, cell: c });
    }));
    // 每格内排序：溢价高在上，断板/待揭晓沉底
    const rank = (item) => {
      const { cell } = item;
      if (cell.status === 'broken') return -1e6;
      if (cell.status === 'limit_down') return -1e5;
      if (cell.status === 'pending' || cell.premium == null) return -1e4;
      return cell.premium;
    };
    Object.values(map).forEach((arr) => arr.sort((a, b) => rank(b) - rank(a)));
    return map;
  }, [cleanStocks]);

  const renderReady = !loading && dates.length > 0 && boardsDesc.length > 0;

  return (
    <div className="ladder-gantt">
      <div className="ladder-head">
        <span className="ladder-title">连板情绪溢价表</span>
        <span className="ladder-badge">情绪周期 · 连板天梯</span>
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
        每行一天（上旧下新，底色＝情绪周期）· 每列一个板位（左高→右低，龙头梯队在左）·
        卡片＝个股次日溢价（绿赚 红亏 黑跌停 虚线断板）· 名字色：白主板 橙创业板 紫科创板
      </div>

      {loading && (
        <div className="ladder-loading"><Spin tip="加载中..." /></div>
      )}
      {!loading && dates.length === 0 && (
        <div className="ladder-empty">暂无梯队数据</div>
      )}

      {renderReady && (
        <div className="ladder-scroll">
          <div className="ladder-board">
            <div className="lb-colhead">
              <div className="lb-corner">
                <span className="lb-corner-x">板位 →</span>
                <span className="lb-corner-y">日期 ↓</span>
              </div>
              {boardsDesc.map((b, i) => (
                <div key={b} className={`lb-bh${i === 0 ? ' lb-bh-top' : ''}`}>
                  {i === 0 ? `${b}板 龙头` : `${b}板`}
                </div>
              ))}
              <div className="lb-rail lb-rail-head">当日盘口</div>
            </div>

            {dates.map((dt) => {
              const col = stageBaseColor(dt.stage);
              const stageLabel = (dt.stage || '').replace(/期$/, '') || '—';
              const bandAlpha = mode === 'light' ? 0.09 : 0.05;
              return (
                <div key={dt.dt} className="lb-row"
                  style={{ background: hexToRgba(col, bandAlpha) }}>
                  <div className="lb-daycol">
                    <div className="lb-date">{dt.display}</div>
                    <div className="lb-wd">{dt.weekday}</div>
                    <div className="lb-stage" style={{ color: col, background: hexToRgba(col, 0.16) }}>
                      {stageLabel}
                    </div>
                  </div>
                  {boardsDesc.map((b) => {
                    const items = grid[`${dt.dt}_${b}`] || [];
                    return (
                      <div key={b} className="lb-col">
                        {items.map((it, idx) => (
                          <LadderCard key={idx} name={it.name} market={it.market} cell={it.cell} />
                        ))}
                      </div>
                    );
                  })}
                  <div className="lb-rail">
                    <span className="lb-s lb-s-max">最高 {dt.max_boards}板</span>
                    <span className="lb-s lb-s-up">涨停 {dt.limit_up_count}</span>
                    <span className="lb-s lb-s-cs">连板 {dt.consec_count}</span>
                    <span className="lb-s lb-s-ad">晋级 {dt.advance_count == null ? '—' : dt.advance_count}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="ladder-legend">
        <span><i className="lg-sw" style={{ background: '#1f9e57' }} />赚钱效应（次日上涨）</span>
        <span><i className="lg-sw" style={{ background: '#cf3636' }} />亏钱效应（次日下跌）</span>
        <span><i className="lg-sw lg-ld" />跌停·吹哨</span>
        <span><i className="lg-sw lg-brk" />断板出局</span>
        <span style={{ color: '#fb923c' }}>橙＝创业板</span>
        <span style={{ color: '#c084fc' }}>紫＝科创板</span>
      </div>
    </div>
  );
}

export default LadderGantt;
