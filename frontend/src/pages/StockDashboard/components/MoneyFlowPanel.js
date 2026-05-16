import React, { useMemo } from 'react';
import { Card } from 'antd';
import { useAtom } from 'jotai';
import { moneyflowAtom } from '../../../store/atoms';

const formatWan = (v) => {
  const n = Number(v || 0);
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}亿`;
  return `${n.toFixed(0)}万`;
};

const FlowRow = ({ label, inVal, outVal }) => {
  const net = inVal - outVal;
  const total = inVal + outVal;
  const inPct = total > 0 ? (inVal / total) * 100 : 50;

  return (
    <div className="mf-row">
      <span className="mf-label">{label}</span>
      <div className="mf-bar-wrap">
        <div className="mf-bar-in" style={{ width: `${inPct}%` }} />
        <div className="mf-bar-out" style={{ width: `${100 - inPct}%` }} />
      </div>
      <div className="mf-values">
        <span className="buy-count">{formatWan(inVal / 10000)}</span>
        <span className="sell-count">{formatWan(outVal / 10000)}</span>
        <span style={{ color: net >= 0 ? '#ff4d4f' : '#52c41a', fontWeight: 600 }}>
          {net >= 0 ? '+' : ''}{formatWan(net / 10000)}
        </span>
      </div>
    </div>
  );
};

const MoneyFlowPanel = () => {
  const [moneyflowData] = useAtom(moneyflowAtom);

  const { rows, summary, lastTime } = useMemo(() => {
    if (!moneyflowData?.success || !moneyflowData?.items?.length) {
      return { rows: [], summary: null, lastTime: null };
    }

    const last = moneyflowData.items[moneyflowData.items.length - 1];

    const rows = [
      { label: '超大单', inVal: last.super_big_in, outVal: last.super_big_out },
      { label: '大单', inVal: last.big_in, outVal: last.big_out },
      { label: '小单', inVal: last.small_in, outVal: last.small_out },
    ];

    return {
      rows,
      summary: moneyflowData.summary,
      lastTime: last.time,
    };
  }, [moneyflowData]);

  if (!summary) {
    return (
      <Card className="stock-card moneyflow-panel" title="资金流向">
        <div className="mf-empty">资金分时数据暂不可用（非交易时间或数据源异常）</div>
      </Card>
    );
  }

  const mainNet = summary.main_net_wan || 0;
  const mainColor = mainNet >= 0 ? '#ff4d4f' : '#52c41a';

  return (
    <Card className="stock-card moneyflow-panel" title="资金流向" extra={
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        同花顺 {lastTime && `${lastTime.slice(0,2)}:${lastTime.slice(2)}`}
      </span>
    }>
      <div className="mf-hero">
        <div className="mf-hero-label">主力净额</div>
        <div className="mf-hero-value" style={{ color: mainColor }}>
          {mainNet >= 0 ? '+' : ''}{formatWan(mainNet)}
        </div>
        <div className="mf-hero-sub">
          超大单+大单（超大单 {formatWan(summary.super_big_net_wan)}，大单 {formatWan(summary.big_net_wan)}）
        </div>
      </div>

      <div className="mf-header">
        <span />
        <span className="buy-count">流入</span>
        <span className="sell-count">流出</span>
        <span>净额</span>
      </div>

      {rows.map((r) => (
        <FlowRow key={r.label} {...r} />
      ))}

      <div className="mf-footer">
        数据来源：同花顺免费资金分时接口
      </div>
    </Card>
  );
};

export default MoneyFlowPanel;
