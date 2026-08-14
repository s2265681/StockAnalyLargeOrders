import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Popover, Spin } from 'antd';
import { apiRequest } from '../../config/api';
import { alignTimeshareToTradingAxis } from '../StockDashboard/utils/l2Analysis';
import './LadderHoverPopover.css';

const CACHE = new Map();
const CACHE_TTL = 45_000;
const inflight = new Map();

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

async function fetchStockPreview(code) {
  const cached = CACHE.get(code);
  if (cached && Date.now() - cached.at < CACHE_TTL) return cached.data;

  if (inflight.has(code)) return inflight.get(code);

  const task = Promise.allSettled([
    apiRequest(`/api/stock/basic?code=${code}`, { timeout: 12000 }),
    apiRequest(`/api/v1/l2_timeshare?code=${code}&chart_only=1`, { timeout: 20000 }),
  ]).then((results) => {
    const basicResp = results[0].status === 'fulfilled' ? results[0].value : null;
    const tsResp = results[1].status === 'fulfilled' ? results[1].value : null;
    const basic = basicResp?.data ?? null;
    const tsData = tsResp?.success && tsResp?.data ? tsResp.data : null;
    const aligned = tsData?.timeshare?.length
      ? alignTimeshareToTradingAxis(tsData.timeshare)
      : null;
    const preview = {
      basic,
      axis: aligned?.axis || [],
      prices: aligned?.fenshi || [],
      prevClose: basic?.yesterday_close
        ?? tsData?.stock_info?.prev_close
        ?? tsData?.stock_info?.prevClose
        ?? null,
    };
    if (basic || (aligned?.fenshi || []).some((p) => p != null)) {
      CACHE.set(code, { at: Date.now(), data: preview });
    }
    return preview;
  }).finally(() => {
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

function MiniTimeshareChart({ axis, prices, prevClose, changePct }) {
  const { axis: xs, prices: ys } = useMemo(() => trimSeries(axis, prices), [axis, prices]);
  const W = 268;
  const H = 96;
  const pad = { t: 8, r: 6, b: 16, l: 6 };
  const innerW = W - pad.l - pad.r;
  const innerH = H - pad.t - pad.b;

  const valid = ys.filter((p) => p != null && p !== '' && Number.isFinite(Number(p))).map(Number);
  if (valid.length < 2) {
    return <div className="lb-hover-nochart">暂无分时数据</div>;
  }

  const ref = Number(prevClose);
  const hasRef = Number.isFinite(ref) && ref > 0;
  const all = hasRef ? [...valid, ref] : valid;
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;

  const xAt = (i) => pad.l + (i / Math.max(1, xs.length - 1)) * innerW;
  const yAt = (p) => pad.t + (1 - (p - min) / span) * innerH;

  const points = [];
  ys.forEach((raw, i) => {
    const p = Number(raw);
    if (!Number.isFinite(p)) return;
    points.push(`${xAt(i).toFixed(1)},${yAt(p).toFixed(1)}`);
  });

  const lineColor = chgColor(changePct);
  const refY = hasRef ? yAt(ref) : null;

  return (
    <svg className="lb-hover-chart" viewBox={`0 0 ${W} ${H}`} aria-hidden>
      {hasRef && (
        <line
          x1={pad.l}
          y1={refY}
          x2={W - pad.r}
          y2={refY}
          className="lb-hover-ref"
        />
      )}
      <polyline points={points.join(' ')} fill="none" stroke={lineColor} strokeWidth="1.6" />
      <text x={pad.l} y={H - 3} className="lb-hover-axis">{xs[0] || '09:30'}</text>
      <text x={W - pad.r} y={H - 3} textAnchor="end" className="lb-hover-axis">{xs[xs.length - 1] || '15:00'}</text>
    </svg>
  );
}

function HoverContent({ code, name, loading, preview }) {
  const basic = preview?.basic;
  const pct = basic?.change_percent;
  const amount = basic?.change_amount;

  return (
    <div className="lb-hover-pop">
      <div className="lb-hover-head">
        <span className="lb-hover-name">{basic?.name || name}</span>
        <span className="lb-hover-code">{code}</span>
      </div>

      {loading && !preview && (
        <div className="lb-hover-loading"><Spin size="small" /></div>
      )}

      {preview && (
        <>
          <div className="lb-hover-quote">
            <span className="lb-hover-price">{fmtPrice(basic?.current_price)}</span>
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
            <span>开 {fmtPrice(basic?.open)}</span>
            <span>高 {fmtPrice(basic?.high)}</span>
            <span>低 {fmtPrice(basic?.low)}</span>
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
    if (cached && Date.now() - cached.at < CACHE_TTL) {
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
