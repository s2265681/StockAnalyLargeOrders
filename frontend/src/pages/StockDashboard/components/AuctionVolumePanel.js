import React from 'react';
import { Card } from 'antd';
import { useAtom } from 'jotai';
import { timeshareDataAtom } from '../../../store/atoms';

const fmtWanHands = (hands) => {
  if (hands == null || Number.isNaN(Number(hands))) return '--';
  return `${(Number(hands) / 10000).toFixed(2)}万手`;
};

const fmtSealVsTurnover = (pct) => {
  if (pct == null || Number.isNaN(Number(pct))) return '--';
  return `${Number(pct).toFixed(2)}%`;
};

/**
 * 右侧：成交量 / 占昨日、封成比、五档卖单合计等（集合竞价区块已隐藏）
 */
const AuctionVolumePanel = () => {
  const [timeshareData] = useAtom(timeshareDataAtom);
  const snap = timeshareData?.session_snapshot || {};

  return (
    <Card className="stock-card auction-volume-panel" title="量能">
      <div className="auction-block auction-block--volume">
        <div className="auction-block-title">成交量</div>
        <div className="auction-row">
          <span className="auction-label">今日累计</span>
          <span className="auction-value">{fmtWanHands(snap.today_volume_hands)}</span>
        </div>
        <div className="auction-row">
          <span className="auction-label">昨日全日</span>
          <span className="auction-value">{fmtWanHands(snap.yesterday_volume_hands)}</span>
        </div>
        <div className="auction-row">
          <span className="auction-label">占昨日</span>
          <span
            className="auction-value"
            style={{
              color: (snap.volume_vs_yesterday_percent || 0) >= 100 ? '#ff7875' : 'rgba(255,255,255,0.85)',
            }}
          >
            {snap.volume_vs_yesterday_percent != null
              ? `${Number(snap.volume_vs_yesterday_percent).toFixed(1)}%`
              : '--'}
          </span>
        </div>
        <div className="auction-row">
          <span className="auction-label">封成比</span>
          <span className="auction-value">{fmtSealVsTurnover(snap.seal_to_turnover_percent)}</span>
        </div>
        <div className="auction-row">
          <span className="auction-label">总卖单量</span>
          <span className="auction-value">{fmtWanHands(snap.total_ask_volume_hands)}</span>
        </div>
        <div className="auction-hint">
          占昨日为当日累计成交量 ÷ 上一交易日全日成交量。盘中会随时间上升。
        </div>
        <div className="auction-hint">
          封成比为涨停时买一封单金额 ÷ 当日累计成交额（非涨停无封单则为空）。总卖单量为五档卖单量合计。
        </div>
      </div>
    </Card>
  );
};

export default AuctionVolumePanel;
