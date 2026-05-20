import React, { useState, useEffect } from 'react';
import { Modal } from 'antd';
import { apiRequest } from '../../config/api';
import './index.css';

const FLAG_MAP = {
  gb_dji: '🇺🇸', gb_ixic: '🇺🇸', gb_inx: '🇺🇸',
  rt_hkHSI: '🇭🇰', gb_nikkei: '🇯🇵', N225: '🇯🇵',
  b_INDEXDOW: '🇺🇸', b_INDEXNASDAQ: '🇺🇸', b_INDEXSP: '🇺🇸',
  b_INDEXHK: '🇭🇰', b_INDEXNK225: '🇯🇵',
};

export default function MarketBriefBar() {
  const [brief, setBrief]       = useState(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiRequest('/api/market-brief/today')
      .then(res => {
        if (!cancelled && res.success && res.data.available) setBrief(res.data);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  if (!brief) return null;
  if (!brief.overseas || !brief.ai_summary) return null;

  const preview = brief.ai_summary.length > 40
    ? brief.ai_summary.slice(0, 40) + '…'
    : brief.ai_summary;

  return (
    <>
      <div className="market-brief-bar">
        <span className="market-brief-label">盘前参考</span>

        {brief.overseas.map(idx => (
          <span key={idx.symbol} className="market-brief-index">
            {FLAG_MAP[idx.symbol] || ''} {idx.name}{' '}
            <b className={idx.change_pct >= 0 ? 'up' : 'down'}>
              {idx.change_pct >= 0 ? '+' : ''}{idx.change_pct}%
            </b>
          </span>
        ))}

        <span className="market-brief-divider">|</span>

        <span className="market-brief-summary" onClick={() => setModalOpen(true)}>
          📰 AI摘要：{preview} →
        </span>

        <span className="market-brief-time">
          {brief.generated_at.slice(11, 16)} 更新
        </span>
      </div>

      <Modal
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        title="今日盘前 AI 摘要"
        width={560}
      >
        <p style={{ fontSize: 12, color: '#aaa', marginTop: 0, marginBottom: 16 }}>
          {brief.brief_date} {brief.generated_at.slice(11, 16)} 生成
        </p>
        <div style={{ fontSize: 13, lineHeight: 2, color: '#333', whiteSpace: 'pre-wrap' }}>
          {brief.ai_summary}
        </div>
      </Modal>
    </>
  );
}
