import React from 'react';
import { useNavigate } from 'react-router-dom';
import ThemeToggle, { useTheme } from '../ThemeToggle';
import './index.css';

const FEATURES = [
  { icon: '📊', label: '实时大单追踪', desc: '毫秒级资金流向' },
  { icon: '🔥', label: '涨停梯队分析', desc: '板块题材一目了然' },
  { icon: '📈', label: '情绪周期判断', desc: '把握市场节奏' },
  { icon: '🤖', label: 'AI 个股诊断', desc: '智能研判操作建议' },
];

function AuthLogo({ onClick }) {
  return (
    <div
      className="auth-logo"
      onClick={onClick}
      onKeyDown={e => e.key === 'Enter' && onClick()}
      role="button"
      tabIndex={0}
    >
      <svg width="32" height="32" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg" aria-hidden>
        <circle cx="18" cy="18" r="17" fill="var(--auth-gold-bg)" stroke="var(--auth-gold)" strokeWidth="1.5" />
        <path d="M18,10 L4,28 Q18,24 32,28 Z" fill="var(--auth-gold)" opacity="0.25" />
        <rect x="14" y="13" width="8" height="14" rx="2" fill="var(--auth-gold)" />
        <polygon points="11,13 25,13 23,7 13,7" fill="var(--auth-gold2)" />
        <circle cx="18" cy="10" r="3.5" fill="#fff" opacity="0.95" />
        <circle cx="18" cy="10" r="2" fill="var(--auth-gold2)" />
      </svg>
      <span className="auth-logo-name">AI炒股指南</span>
    </div>
  );
}

export default function AuthLayout({ title, subtitle, children, footer }) {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="auth-page">
      <div className="auth-bg" aria-hidden>
        <div className="auth-bg-glow auth-bg-glow--1" />
        <div className="auth-bg-glow auth-bg-glow--2" />
        <div className="auth-bg-grid" />
        <div className="auth-chart-deco">
          {[42, 58, 35, 72, 48, 65, 38, 80, 52, 68, 45, 75].map((h, i) => (
            <div
              key={i}
              className="auth-chart-bar"
              style={{ '--bar-h': `${h}%`, '--bar-delay': `${i * 0.06}s` }}
            />
          ))}
        </div>
      </div>

      <header className="auth-header">
        <AuthLogo onClick={() => navigate('/')} />
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
      </header>

      <main className="auth-main">
        <section className="auth-brand">
          <div className="auth-brand-inner">
            <div className="auth-eyebrow">
              <span className="auth-pulse" />
              AI 驱动的专业短线分析
            </div>
            <h1 className="auth-headline">
              让数据说话<br />
              <em>让 AI 助你决策</em>
            </h1>
            <p className="auth-tagline">
              专为 A 股打板党、短线交易者设计的智能分析工具
            </p>
            <ul className="auth-features">
              {FEATURES.map((f, i) => (
                <li key={f.label} className="auth-feature" style={{ '--feat-delay': `${0.15 + i * 0.08}s` }}>
                  <span className="auth-feature-icon">{f.icon}</span>
                  <span className="auth-feature-text">
                    <strong>{f.label}</strong>
                    <span>{f.desc}</span>
                  </span>
                </li>
              ))}
            </ul>
            <div className="auth-stats">
              <div className="auth-stat">
                <span className="auth-stat-num">10<sup>+</sup></span>
                <span className="auth-stat-label">分析维度</span>
              </div>
              <div className="auth-stat-divider" />
              <div className="auth-stat">
                <span className="auth-stat-num">实时</span>
                <span className="auth-stat-label">行情推送</span>
              </div>
              <div className="auth-stat-divider" />
              <div className="auth-stat">
                <span className="auth-stat-num">AI</span>
                <span className="auth-stat-label">智能诊股</span>
              </div>
            </div>
          </div>
        </section>

        <section className="auth-form-section">
          <div className="auth-card">
            <div className="auth-card-icon" aria-hidden>
              <svg width="48" height="48" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg">
                <circle cx="18" cy="18" r="17" fill="var(--auth-gold-bg)" stroke="var(--auth-gold)" strokeWidth="1.5" />
                <rect x="14" y="13" width="8" height="14" rx="2" fill="var(--auth-gold)" />
                <polygon points="11,13 25,13 23,7 13,7" fill="var(--auth-gold2)" />
                <circle cx="18" cy="10" r="3.5" fill="#fff" opacity="0.95" />
                <circle cx="18" cy="10" r="2" fill="var(--auth-gold2)" />
              </svg>
            </div>
            <h2 className="auth-card-title">{title}</h2>
            {subtitle && <p className="auth-card-subtitle">{subtitle}</p>}
            <div className="auth-card-body">{children}</div>
            {footer && <div className="auth-card-footer">{footer}</div>}
          </div>
        </section>
      </main>
    </div>
  );
}
