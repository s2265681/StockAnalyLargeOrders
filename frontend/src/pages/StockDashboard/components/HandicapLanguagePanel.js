import React, { useMemo } from 'react';
import { Card, Progress, Tag } from 'antd';
import { useAtom } from 'jotai';
import { largeOrdersDataAtom, timeshareDataAtom } from '../../../store/atoms';
import { buildHandicapLanguage } from '../utils/l2Analysis';

const toneColor = {
  positive: '#ff4d4f',
  negative: '#52c41a',
  neutral: '#ffa940',
};

const formatWan = (value) => `${(Number(value || 0) / 10000).toFixed(0)}万`;
const formatPrice = (value) => (Number(value || 0) ? Number(value).toFixed(2) : '--');

const HandicapLanguagePanel = () => {
  const [timeshareData] = useAtom(timeshareDataAtom);
  const [largeOrdersData] = useAtom(largeOrdersDataAtom);
  const signal = useMemo(() => buildHandicapLanguage({
    timeshareData,
    largeOrdersData,
  }), [timeshareData, largeOrdersData]);

  const color = toneColor[signal.tone] || toneColor.neutral;
  const orderBook = timeshareData?.order_book || {};
  const asks = orderBook.asks || [];
  const bids = orderBook.bids || [];

  return (
    <Card className="stock-card handicap-panel" title="盘口语言雷达">
      <div className="handicap-hero">
        <div>
          <div className="handicap-label" style={{ color }}>{signal.primaryLabel}</div>
          <div className="handicap-subtitle">基于分时位置、大单方向和买卖强弱推断</div>
        </div>
        <Progress
          type="circle"
          percent={signal.score}
          size={70}
          strokeColor={color}
          trailColor="rgba(255,255,255,0.08)"
          format={(value) => `${value}`}
        />
      </div>

      <div className="handicap-tags">
        {(signal.tags || []).map(tag => (
          <Tag key={tag} color={signal.tone === 'negative' ? 'green' : signal.tone === 'positive' ? 'red' : 'orange'}>
            {tag}
          </Tag>
        ))}
      </div>

      <div className="handicap-section">
        <div className="handicap-section-title">雷达数据层级</div>
        <div className="handicap-metrics">
          <div className="handicap-metric">
            <span>当前价</span>
            <div className='handicap-metric_change'>
            <strong>{formatPrice(signal.metrics?.currentPrice)}</strong>
            {signal.metrics?.changePercent != null && (
              <span style={{
                marginLeft: 4, fontSize: 12,
                color: signal.metrics.changePercent >= 0 ? '#ff4d4f' : '#52c41a',
              }}>
                {signal.metrics.changePercent >= 0 ? '+' : ''}{signal.metrics.changePercent}%
              </span>
            )}
            </div>
          </div>
          <div className="handicap-metric">
            <span>均线</span>
            <strong>{formatPrice(signal.metrics?.avgPrice)}</strong>
          </div>
          <div className="handicap-metric">
            <span>开盘价</span>
            <strong>{formatPrice(signal.metrics?.openPrice)}</strong>
          </div>
          <div className="handicap-metric">
            <span>五档</span>
            <strong className={signal.metrics?.bookAvailable ? 'buy-count' : 'sell-count'}>
              {signal.metrics?.bookAvailable ? '已接入' : '暂不可用'}
            </strong>
          </div>
        </div>
      </div>

      <div className="handicap-section">
        <div className="handicap-section-title">五档盘口</div>
        {asks.length > 0 || bids.length > 0 ? (
          <>
          <div className="orderbook-summary">
            <span className="sell-count">卖盘 {formatWan(orderBook.ask_amount)}</span>
            <span className="orderbook-spread">价差 {orderBook.spread || '--'}</span>
            <span className="buy-count">买盘 {formatWan(orderBook.bid_amount)}</span>
          </div>
          <div className="orderbook-levels">
            <div className="orderbook-side">
              {asks.slice().reverse().map(item => (
                <div className="orderbook-row ask" key={`ask-${item.level}`}>
                  <span>卖{item.level}</span>
                  <strong>{Number(item.price).toFixed(2)}</strong>
                  <em>{formatWan(item.amount)}</em>
                </div>
              ))}
            </div>
            <div className="orderbook-side">
              {bids.map(item => (
                <div className="orderbook-row bid" key={`bid-${item.level}`}>
                  <span>买{item.level}</span>
                  <strong>{Number(item.price).toFixed(2)}</strong>
                  <em>{formatWan(item.amount)}</em>
                </div>
              ))}
            </div>
          </div>
          </>
        ) : (
          <div className="orderbook-empty">
            实时五档盘口暂不可用，当前雷达已降级使用分时走势和大单成交判断。
          </div>
        )}
      </div>

      <div className="handicap-section">
        <div className="handicap-section-title">大单结构</div>
        <div className="handicap-metrics">
          <div className="handicap-metric">
            <span>买单</span>
            <strong className="buy-count">{formatWan(signal.metrics?.buyAmount)}</strong>
          </div>
          <div className="handicap-metric">
            <span>卖单</span>
            <strong className="sell-count">{formatWan(signal.metrics?.sellAmount)}</strong>
          </div>
          <div className="handicap-metric">
            <span>买占比(加权)</span>
            <strong>{Math.round((signal.metrics?.wBuyRatio || signal.metrics?.buyRatio || 0) * 100)}%</strong>
          </div>
          <div className="handicap-metric">
            <span>盘口买占比</span>
            <strong>{signal.metrics?.bookAvailable ? `${Math.round((signal.metrics?.bookBidRatio || 0) * 100)}%` : '--'}</strong>
          </div>
        </div>
      </div>

      <div className="handicap-section">
        <div className="handicap-section-title">判断依据</div>
        {(signal.reasons || []).map((reason, index) => (
          <div className="handicap-reason" key={`${reason}-${index}`}>{reason}</div>
        ))}
      </div>

      <div className="handicap-section">
        <div className="handicap-section-title">交易提示</div>
        <div className="handicap-advice">{signal.advice}</div>
      </div>

      <div className="handicap-disclaimer">
        仅做盘口观察辅助，不构成确定性买卖建议。
      </div>
    </Card>
  );
};

export default HandicapLanguagePanel;
