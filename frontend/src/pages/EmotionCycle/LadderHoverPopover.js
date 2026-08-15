import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Popover, Spin } from 'antd';
import { apiRequest } from '../../config/api';
import { alignTimeshareToTradingAxis } from '../StockDashboard/utils/l2Analysis';
import './LadderHoverPopover.css';

const CACHE = new Map();
const CACHE_TTL = 45_000;
const inflight = new Map();
const X_TICKS = ['09:30', '11:30', '13:00', '15:00'];

const fmtPrice = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : '—';
};

const fmtPct = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n) < 0.005) return '0.00%';
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
};

const chgColor = (pct) => {
  const n = Number(pct);
  if (!Number.isFinite(n) || Math.abs(n) < 0.005) return 'var(--lb-hover-muted)';
  return n > 0 ? '#ff4d4f' : '#52c41a';
};

function buildQuote(stockInfo, timeshare) {
  if (!stockInfo) return null;
  const price = Number(stockInfo.price ?? stockInfo.current_price);
  const prevClose = Number(stockInfo.yesterday_close ?? stockInfo.prev_close ?? stockInfo.prevClose);
  const open = Number(stockInfo.open);
  const high = Number(stockInfo.high);
  const low = Number(stockInfo.low);
  let changePct = Number(stockInfo.change_percent);
  if (!Number.isFinite(changePct) && Number.isFinite(price) && Number.isFinite(prevClose) && prevClose > 0) {
    changePct = ((price - prevClose) / prevClose) * 100;
  }
  const changeAmt = Number.isFinite(price) && Number.isFinite(prevClose) ? price - prevClose : null;

  // 行情字段缺失时从分时序列补
  const prices = (timeshare || [])
    .map((t) => Number(t.price))
    .filter((p) => Number.isFinite(p) && p > 0);
  const last = prices.length ? prices[prices.length - 1] : price;
  const seqHigh = prices.length ? Math.max(...prices) : null;
  const seqLow = prices.length ? Math.min(...prices) : null;

  return {
    name: stockInfo.name || '',
    price: Number.isFinite(last) ? last : price,
    yesterday_close: Number.isFinite(prevClose) ? prevClose : null,
    open: Number.isFinite(open) ? open : (prices[0] ?? null),
    high: Number.isFinite(high) && high > 0 ? high : seqHigh,
    low: Number.isFinite(low) && low > 0 ? low : seqLow,
    change_percent: changePct,
    change_amount: changeAmt,
  };
}

async function fetchStockPreview(code) {
  const cached = CACHE.get(code);
  if (cached && Date.now() - cached.at < CACHE_TTL && cached.data?.quote) {
    return cached.data;
  }

  if (inflight.has(code)) return inflight.get(code);

  const task = apiRequest(`/api/v1/l2_timeshare?code=${code}&chart_only=1`, { timeout: 20000 })
    .then((tsResp) => {
      const tsData = tsResp?.success && tsResp?.data ? tsResp.data : null;
      if (!tsData?.timeshare?.length) return null;

      const aligned = alignTimeshareToTradingAxis(tsData.timeshare);
      const quote = buildQuote(tsData.stock_info, tsData.timeshare);
      const preview = {
        quote,
        axis: aligned.axis || [],
        prices: aligned.fenshi || [],
        prevClose: quote?.yesterday_close ?? null,
      };
      CACHE.set(code, { at: Date.now(), data: preview });
      return preview;
    })
    .finally(() => {
      inflight.delete(code);
    });

  inflight.set(code, task);
  return task;
}

function trimSeries(axis, prices) {
  if (!axis.length) return { axis: [], prices: [] };
  let end = prices.length - 1;
  while (end >= 0 && (prices[end] == null || prices[end] === '')) end -= 1;
  if (end < 0) return { axis: [], prices: [] };
  return { axis: axis.slice(0, end + 1), prices: prices.slice(0, end + 1) };
}

function pickTickIndices(axis, ticks) {
  const map = new Map();
  axis.forEach((t, i) => {
    if (ticks.includes(t) && !map.has(t)) map.set(t, i);
  });
  return ticks.filter((t) => map.has(t)).map((t) => ({ time: t, index: map.get(t) }));
}

function MiniTimeshareChart({ axis, prices, prevClose, changePct }) {
  const { axis: xs, prices: ys } = useMemo(() => trimSeries(axis, prices), [axis, prices]);

  const chart = useMemo(() => {
    const W = 284;
    const H = 118;
    const pad = { t: 10, r: 8, b: 20, l: 38 };
    const innerW = W - pad.l - pad.r;
    const innerH = H - pad.t - pad.b;

    const valid = ys
      .map((p, i) => ({ p: Number(p), i }))
      .filter(({ p }) => Number.isFinite(p) && p > 0);

    if (valid.length < 2) return null;

    const ref = Number(prevClose);
    const hasRef = Number.isFinite(ref) && ref > 0;
    const priceVals = valid.map(({ p }) => p);
    const min = Math.min(...priceVals, hasRef ? ref : Infinity);
    const max = Math.max(...priceVals, hasRef ? ref : -Infinity);
    const span = max - min || 0.01;
    const padY = span * 0.08;
    const yMin = min - padY;
    const yMax = max + padY;
    const ySpan = yMax - yMin;

    const xAt = (i) => pad.l + (i / Math.max(1, xs.length - 1)) * innerW;
    const yAt = (p) => pad.t + (1 - (p - yMin) / ySpan) * innerH;

    const points = valid.map(({ p, i }) => `${xAt(i).toFixed(1)},${yAt(p).toFixed(1)}`).join(' ');
    const refY = hasRef ? yAt(ref) : null;
    const lineColor = chgColor(changePct);

    const yTicks = [
      { label: fmtPrice(yMax), y: pad.t },
      { label: hasRef ? fmtPrice(ref) : fmtPrice((yMax + yMin) / 2), y: hasRef ? refY : pad.t + innerH / 2 },
      { label: fmtPrice(yMin), y: pad.t + innerH },
    ];

    const xTickItems = pickTickIndices(xs, X_TICKS);

    return {
      W, H, pad, innerW, innerH, points, refY, lineColor, yTicks, xTickItems, xAt,
    };
  }, [xs, ys, prevClose, changePct]);

  if (!chart) {
    return <div className="lb-hover-nochart">暂无分时数据</div>;
  }

  const { W, H, pad, innerW, innerH, points, refY, lineColor, yTicks, xTickItems, xAt } = chart;

  return (
    <svg className="lb-hover-chart" viewBox={`0 0 ${W} ${H}`} aria-hidden>
      {yTicks.map((tick) => (
        <g key={tick.label}>
          <line
            x1={pad.l}
            y1={tick.y}
            x2={W - pad.r}
            y2={tick.y}
            className="lb-hover-grid"
          />
          <text x={pad.l - 4} y={tick.y + 3} textAnchor="end" className="lb-hover-yaxis">
            {tick.label}
          </text>
        </g>
      ))}

      {refY != null && (
        <line
          x1={pad.l}
          y1={refY}
          x2={W - pad.r}
          y2={refY}
          className="lb-hover-ref"
        />
      )}

      <polyline points={points} fill="none" stroke={lineColor} strokeWidth="1.6" />

      {xTickItems.map(({ time, index }) => (
        <text
          key={time}
          x={xAt(index)}
          y={H - 4}
          textAnchor="middle"
          className="lb-hover-xaxis"
        >
          {time}
        </text>
      ))}

      <line x1={pad.l} y1={pad.t} x2={pad.l} y2={pad.t + innerH} className="lb-hover-axis-line" />
      <line x1={pad.l} y1={pad.t + innerH} x2={pad.l + innerW} y2={pad.t + innerH} className="lb-hover-axis-line" />
    </svg>
  );
}

function HoverContent({ code, name, loading, preview }) {
  const quote = preview?.quote;
  const pct = quote?.change_percent;
  const amount = quote?.change_amount;

  return (
    <div className="lb-hover-pop">
      <div className="lb-hover-head">
        <span className="lb-hover-name">{quote?.name || name}</span>
        <span className="lb-hover-code">{code}</span>
      </div>

      {loading && !preview && (
        <div className="lb-hover-loading"><Spin size="small" /></div>
      )}

      {preview && (
        <>
          <div className="lb-hover-quote">
            <span className="lb-hover-price">{fmtPrice(quote?.price)}</span>
            <span className="lb-hover-chg" style={{ color: chgColor(pct) }}>{fmtPct(pct)}</span>
            <span className="lb-hover-amt" style={{ color: chgColor(amount) }}>
              {Number.isFinite(Number(amount)) ? `${Number(amount) > 0 ? '+' : ''}${fmtPrice(amount)}` : '—'}
            </span>
          </div>
          <MiniTimeshareChart
            axis={preview.axis}
            prices={preview.prices}
            prevClose={preview.prevClose}
            changePct={pct}
          />
          <div className="lb-hover-meta">
            <span>开 {fmtPrice(quote?.open)}</span>
            <span>高 {fmtPrice(quote?.high)}</span>
            <span>低 {fmtPrice(quote?.low)}</span>
            <span>昨收 {fmtPrice(quote?.yesterday_close)}</span>
          </div>
        </>
      )}

      {!loading && !preview && (
        <div className="lb-hover-nochart">行情加载失败</div>
      )}
    </div>
  );
}

export function LadderHoverPopover({ code, name, children, disabled = false }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState(null);

  const load = useCallback(async () => {
    if (!code || disabled) return;
    setLoading(true);
    try {
      const data = await fetchStockPreview(code);
      setPreview(data);
    } catch {
      setPreview(null);
    } finally {
      setLoading(false);
    }
  }, [code, disabled]);

  useEffect(() => {
    if (!open || !code || disabled) return;
    const cached = CACHE.get(code);
    if (cached && Date.now() - cached.at < CACHE_TTL && cached.data?.quote) {
      setPreview(cached.data);
      setLoading(false);
      return;
    }
    setPreview(null);
    load();
  }, [open, code, disabled, load]);

  if (!code || disabled) return children;

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="hover"
      mouseEnterDelay={0.25}
      mouseLeaveDelay={0.12}
      placement="rightTop"
      overlayClassName="lb-hover-overlay"
      destroyTooltipOnHide
      content={(
        <HoverContent
          code={code}
          name={name}
          loading={loading}
          preview={preview}
        />
      )}
    >
      <span className="lb-hover-trigger">{children}</span>
    </Popover>
  );
}

export default LadderHoverPopover;
