import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Modal, Button, Spin, message } from 'antd';
import { ReloadOutlined, RightOutlined } from '@ant-design/icons';
import { apiRequest } from '../../config/api';
import './index.css';

const FLAG_MAP = {
  gb_dji: '🇺🇸', gb_ixic: '🇺🇸', gb_inx: '🇺🇸',
  rt_hkHSI: '🇭🇰', gb_nikkei: '🇯🇵', N225: '🇯🇵',
  b_INDEXDOW: '🇺🇸', b_INDEXNASDAQ: '🇺🇸', b_INDEXSP: '🇺🇸',
  b_INDEXHK: '🇭🇰', b_INDEXNK225: '🇯🇵',
};

function formatTime(iso) {
  if (!iso) return '';
  const s = String(iso);
  return s.length >= 16 ? s.slice(11, 16) : s;
}

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
      <div className="market-brief-wrap">
        <div className="market-brief-card market-brief-card--state">
          <Spin size="small" />
          <span className="market-brief-state-text">
            {generating ? '正在生成今日盘前资讯（约 30–90 秒）…' : '加载盘前资讯…'}
          </span>
        </div>
      </div>
    );
  }

  if (!brief?.overseas?.length || !brief?.ai_summary) {
    const hasToken = !!localStorage.getItem('niuniu_token');
    return (
      <div className="market-brief-wrap">
        <div className="market-brief-card market-brief-card--state market-brief-card--empty">
          <span className="market-brief-badge">盘前参考</span>
          <span className="market-brief-state-text">今日尚未生成</span>
          {hasToken && (
            <Button
              type="link"
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => generateBrief(true)}
              loading={generating}
              className="market-brief-gen-btn"
            >
              立即生成
            </Button>
          )}
        </div>
      </div>
    );
  }

  const preview = brief.ai_summary.length > 56
    ? `${brief.ai_summary.slice(0, 56)}…`
    : brief.ai_summary;

  return (
    <div className="market-brief-wrap">
      <div className="market-brief-card">
        <div className="market-brief-head">
          <span className="market-brief-badge">盘前参考</span>
          <span className="market-brief-time">{formatTime(brief.generated_at)} 更新</span>
        </div>

        <div className="market-brief-indices" role="list" aria-label="海外指数">
          {brief.overseas.map(idx => (
            <span key={idx.symbol} className="market-brief-chip" role="listitem">
              <span className="market-brief-chip-flag">{FLAG_MAP[idx.symbol] || '🌐'}</span>
              <span className="market-brief-chip-name">{idx.name}</span>
              <span className={`market-brief-chip-pct ${idx.change_pct >= 0 ? 'up' : 'down'}`}>
                {idx.change_pct >= 0 ? '+' : ''}{idx.change_pct}%
              </span>
            </span>
          ))}
        </div>

        <button
          type="button"
          className="market-brief-summary"
          onClick={() => setModalOpen(true)}
          aria-label="查看今日盘前 AI 摘要"
        >
          <span className="market-brief-summary-tag">AI 摘要</span>
          <span className="market-brief-summary-text">{preview}</span>
          <span className="market-brief-summary-action">
            查看全文 <RightOutlined />
          </span>
        </button>
      </div>

      <Modal
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        title="今日盘前 AI 摘要"
        width="min(560px, 92vw)"
        centered
        className="market-brief-modal"
        styles={{ body: { maxHeight: 'min(70vh, 520px)', overflow: 'auto' } }}
      >
        <p className="market-brief-modal-meta">
          {brief.brief_date} · {formatTime(brief.generated_at)} 生成
        </p>
        <div className="market-brief-modal-body">{brief.ai_summary}</div>
      </Modal>
    </div>
  );
}
