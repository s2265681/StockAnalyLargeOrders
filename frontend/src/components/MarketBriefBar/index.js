import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Modal, Button, Spin, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { apiRequest } from '../../config/api';
import './index.css';

const FLAG_MAP = {
  gb_dji: '🇺🇸', gb_ixic: '🇺🇸', gb_inx: '🇺🇸',
  rt_hkHSI: '🇭🇰', gb_nikkei: '🇯🇵', N225: '🇯🇵',
  b_INDEXDOW: '🇺🇸', b_INDEXNASDAQ: '🇺🇸', b_INDEXSP: '🇺🇸',
  b_INDEXHK: '🇭🇰', b_INDEXNK225: '🇯🇵',
};

export default function MarketBriefBar() {
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const autoGenAttempted = useRef(false);

  const loadBrief = useCallback(async () => {
    const res = await apiRequest('/api/market-brief/today');
    if (res.success && res.data?.available) {
      setBrief(res.data);
      return true;
    }
    setBrief(null);
    return false;
  }, []);

  const generateBrief = useCallback(async (force = false) => {
    setGenerating(true);
    try {
      const res = await apiRequest('/api/market-brief/refresh', {
        method: 'POST',
        body: JSON.stringify({ force }),
      });
      if (res.success && res.data?.available) {
        setBrief(res.data);
        message.success('盘前资讯已生成');
        return true;
      }
      message.error(res.message || '生成失败');
    } catch (e) {
      message.error(e.message || '生成盘前资讯失败');
    } finally {
      setGenerating(false);
    }
    return false;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const ok = await loadBrief();
        if (cancelled) return;
        const hasToken = !!localStorage.getItem('niuniu_token');
        if (!ok && hasToken && !autoGenAttempted.current) {
          autoGenAttempted.current = true;
          await generateBrief(false);
        }
      } catch {
        /* 静默 */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [loadBrief, generateBrief]);

  if (loading || generating) {
    return (
      <div className="market-brief-bar market-brief-bar--loading">
        <Spin size="small" />
        <span>{generating ? '正在生成今日盘前资讯（约 30–90 秒）…' : '加载盘前资讯…'}</span>
      </div>
    );
  }

  if (!brief?.overseas?.length || !brief?.ai_summary) {
    const hasToken = !!localStorage.getItem('niuniu_token');
    return (
      <div className="market-brief-bar market-brief-bar--empty">
        <span className="market-brief-label">盘前参考</span>
        <span className="market-brief-empty-hint">今日尚未生成</span>
        {hasToken && (
          <Button
            type="link"
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => generateBrief(true)}
            loading={generating}
          >
            立即生成
          </Button>
        )}
      </div>
    );
  }

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
          {brief.generated_at?.slice(11, 16)} 更新
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
          {brief.brief_date} {brief.generated_at?.slice(11, 16)} 生成
        </p>
        <div style={{ fontSize: 13, lineHeight: 2, color: '#333', whiteSpace: 'pre-wrap' }}>
          {brief.ai_summary}
        </div>
      </Modal>
    </>
  );
}
