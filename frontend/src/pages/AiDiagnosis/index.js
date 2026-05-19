import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Input, Button, Spin, Tag, message, Alert } from 'antd';
import {
  RobotOutlined,
  SendOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  RiseOutlined,
  FallOutlined,
  AlertOutlined,
  FundOutlined,
  FireOutlined,
  StockOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { apiRequest } from '../../config/api';
import './index.css';

const { TextArea } = Input;

/** 诊股含数据聚合 + Claude，需长于默认 30s */
const DIAGNOSIS_TIMEOUT = 180000;
const CHAT_TIMEOUT = 60000;
const LS_CODE_KEY = 'ai_diagnosis_last_code';

const RATING_STYLE = {
  偏多: { color: '#cf1322', bg: 'rgba(255, 77, 79, 0.1)', border: '#ff4d4f' },
  中性: { color: '#d48806', bg: 'rgba(250, 173, 20, 0.12)', border: '#faad14' },
  偏空: { color: '#389e0d', bg: 'rgba(82, 196, 26, 0.1)', border: '#52c41a' },
};

function stripMarkdown(text) {
  if (!text) return '';
  return String(text)
    .replace(/```[\s\S]*?```/g, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^[-*]\s+/gm, '')
    .trim();
}

function formatAmount(val) {
  if (val == null || val === '') return '—';
  const n = Number(val);
  if (Number.isNaN(n)) return String(val);
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(2)}万`;
  return `${sign}${abs.toFixed(2)}`;
}

function SnapshotPanel({ snapshot }) {
  if (!snapshot) return null;
  const q = snapshot.quote || {};
  const basic = snapshot.basic || {};
  const l2 = snapshot.l2 || {};
  const lo = snapshot.large_orders || {};
  const em = snapshot.emotion || {};
  const au = snapshot.auction || {};
  const th = snapshot.theme || {};
  const lu = snapshot.limit_up || {};
  const ts = snapshot.timeshare || {};
  const eco = snapshot.market_ecology || {};
  const dt = snapshot.dragon_tiger || {};

  const name = q.name || basic.name || snapshot.code;
  const price = q.price ?? basic.current_price;
  const chg = q.change_percent ?? basic.change_percent;
  const sealLabel = l2.limit_up_status
    || (lu.in_pool ? `${lu.boards || 0}板` : null)
    || '非涨停';
  const mainNet = l2.large_order_net ?? lo.main_net;
  const themeName = th.theme || lu.theme;
  const themeExtra = themeName
    ? `${th.position || lu.position} · 同题材${th.theme_count || lu.theme_count || 0}家`
    : '';

  const rows = [
    em.available && {
      key: 'emotion',
      icon: <FundOutlined />,
      label: '情绪',
      value: em.stage || '—',
      sub: (em.advice || '').slice(0, 48),
      highlight: true,
    },
    eco.available && {
      key: 'eco',
      icon: <StockOutlined />,
      label: '生态',
      value: `涨停${eco.limit_up_total} · ${eco.max_boards}板高 · 首板${eco.first_board_count}`,
    },
    {
      key: 'flow',
      label: '资金',
      value: `大单净 ${mainNet != null ? formatAmount(mainNet) : '—'} · ${sealLabel}`,
    },
    ts.available && {
      key: 'ts',
      label: '分时',
      value: `上${ts.morning_trend}/下${ts.afternoon_trend} · ${ts.volume_pattern}`,
    },
    {
      key: 'theme',
      icon: <FireOutlined />,
      label: '题材',
      value: themeName || '无明确题材',
      sub: themeExtra,
    },
    {
      key: 'auction',
      label: '竞价',
      value: au.in_list ? `抢筹榜 ${au.grab_change_pct ?? '—'}%` : '未在抢筹榜',
    },
    dt.on_list && {
      key: 'dt',
      label: '龙虎',
      value: `${dt.date} 净买 ${formatAmount(dt.net_buy)}`,
      sub: (dt.reason || '').slice(0, 56),
      dt: true,
    },
  ].filter(Boolean);

  return (
    <div className="ai-snapshot-panel ai-snapshot-panel--compact">
      <div className="ai-snap-head">
        <span className="ai-snapshot-title">数据快照</span>
        <span className="ai-snap-stock">{name}</span>
        <span className="ai-snap-code">{snapshot.code}</span>
        {price != null && (
          <span className={`ai-snap-price ${chg >= 0 ? 'up' : 'down'}`}>
            {price}
            {chg != null && (
              <em>
                {chg >= 0 ? '+' : ''}
                {chg}%
              </em>
            )}
          </span>
        )}
        {snapshot.partial && (
          <Tag color="orange" className="ai-partial-tag">部分缺失</Tag>
        )}
      </div>
      <div className="ai-snapshot-grid">
        {rows.map((row) => (
          <div
            key={row.key}
            className={`ai-snap-card${row.highlight ? ' ai-snap-card--highlight' : ''}${row.dt ? ' ai-snap-card--dt' : ''}${row.sub ? ' ai-snap-card--tall' : ''}`}
          >
            <span className="label">
              {row.icon}
              {row.label}
            </span>
            <span className="value">{row.value}</span>
            {row.sub && <span className="ai-snap-sub">{row.sub}</span>}
          </div>
        ))}
      </div>
      <p className="ai-snap-time">{snapshot.assembled_at || '—'}</p>
    </div>
  );
}

function TradePointCard({ type, points }) {
  if (!points?.length) return null;
  const isBuy = type === 'buy';
  return (
    <div className={`ai-trade-col ai-trade-col--${type}`}>
      <h4 className="ai-trade-col-title">
        {isBuy ? <RiseOutlined /> : <FallOutlined />}
        {isBuy ? '买入点位' : '卖出点位'}
      </h4>
      <ul className="ai-trade-list">
        {points.map((pt, i) => (
          <li key={`${type}-${i}`} className="ai-trade-item">
            <span className="ai-trade-price">{pt.price || '—'}</span>
            <span className="ai-trade-reason">{stripMarkdown(pt.reason)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReportSections({ sections }) {
  if (!sections?.length) return null;
  return (
    <div className="ai-sections">
      {sections.map((sec, i) => (
        <article key={i} className="ai-section-card">
          <h4 className="ai-section-title">{sec.title}</h4>
          <p className="ai-section-body">{stripMarkdown(sec.content)}</p>
          {sec.highlights?.length > 0 && (
            <div className="ai-section-tags">
              {sec.highlights.map((h, j) => (
                <Tag key={j} className="ai-highlight-tag">
                  {h}
                </Tag>
              ))}
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

function ReportPanel({ report }) {
  if (!report) return null;
  const ratingStyle = RATING_STYLE[report.rating] || RATING_STYLE['中性'];

  return (
    <div className="ai-report-panel">
      <div className="ai-report-hero">
        <div
          className="ai-rating-badge"
          style={{
            color: ratingStyle.color,
            background: ratingStyle.bg,
            borderColor: ratingStyle.border,
          }}
        >
          {report.rating || '—'}
        </div>
        <div className="ai-report-meta">
          <Tag className="ai-meta-tag">{report.theme_position || '—'}</Tag>
          <Tag color="processing" className="ai-meta-tag">
            {report.position_advice || '—'}
          </Tag>
        </div>
      </div>

      <p className="ai-report-summary">{stripMarkdown(report.summary)}</p>

      <div className="ai-report-pills">
        {report.emotion_fit && (
          <div className="ai-pill">
            <span className="ai-pill-label">情绪</span>
            <span>{stripMarkdown(report.emotion_fit)}</span>
          </div>
        )}
        {report.market_env && (
          <div className="ai-pill">
            <span className="ai-pill-label">大盘</span>
            <span>{stripMarkdown(report.market_env)}</span>
          </div>
        )}
        {report.short_term_ecology && (
          <div className="ai-pill">
            <span className="ai-pill-label">生态</span>
            <span>{stripMarkdown(report.short_term_ecology)}</span>
          </div>
        )}
      </div>

      <div className="ai-report-trade-grid">
        <TradePointCard type="buy" points={report.buy_points} />
        <TradePointCard type="sell" points={report.sell_points} />
      </div>

      {(report.stop_loss || report.stop_loss_reason) && (
        <div className="ai-stop-box">
          <AlertOutlined />
          <div>
            <strong>止损参考：</strong>
            {stripMarkdown(report.stop_loss)}
            {report.stop_loss_reason && (
              <span className="ai-stop-reason"> — {stripMarkdown(report.stop_loss_reason)}</span>
            )}
          </div>
        </div>
      )}

      {(report.risk_warnings || []).length > 0 && (
        <div className="ai-risks">
          {(report.risk_warnings || []).map((r, i) => (
            <Tag key={i} color="volcano" className="ai-risk-tag">
              {stripMarkdown(r)}
            </Tag>
          ))}
        </div>
      )}

      <ReportSections sections={report.sections} />
    </div>
  );
}

function HotSearchTags({ onSearchedClick, onHotClick }) {
  const [hotData, setHotData] = useState({ searched: [], hot: [] });

  useEffect(() => {
    let cancelled = false;
    apiRequest('/api/v1/ai-diagnosis/hot-stocks', { timeout: 10000 })
      .then((res) => {
        if (!cancelled && res.success && res.data) setHotData(res.data);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const { searched, hot } = hotData;
  const hotVisible = hot.slice(0, Math.max(0, 10 - searched.length));

  if (!searched.length && !hotVisible.length) return null;

  return (
    <div className="ai-hot-tags">
      {searched.map((s) => (
        <Tag
          key={`s-${s.code}`}
          className="ai-hot-tag ai-hot-tag--searched"
          icon={<SearchOutlined />}
          onClick={() => onSearchedClick(s.code)}
        >
          {s.name || s.code}
        </Tag>
      ))}
      {searched.length > 0 && hotVisible.length > 0 && (
        <span className="ai-hot-divider" />
      )}
      {hotVisible.map((h) => (
        <Tag
          key={`h-${h.code}`}
          className="ai-hot-tag ai-hot-tag--hot"
          icon={<FireOutlined />}
          onClick={() => onHotClick(h.code)}
        >
          {h.name || h.code}
        </Tag>
      ))}
    </div>
  );
}

function AiDiagnosis() {
  const [searchParams] = useSearchParams();
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [report, setReport] = useState(null);
  const [cached, setCached] = useState(false);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const chatEndRef = useRef(null);
  const lastAutoCodeRef = useRef('');
  const cacheRetryTimerRef = useRef(null);

  // 页面 mount 时恢复上次输入的代码（不自动查询）
  useEffect(() => {
    const saved = localStorage.getItem(LS_CODE_KEY);
    if (saved && /^\d{1,6}$/.test(saved)) setCode(saved);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const contextRef = useRef({ snapshot: null, report: null });
  useEffect(() => {
    contextRef.current = { snapshot, report };
  }, [snapshot, report]);

  useEffect(() => {
    return () => {
      if (cacheRetryTimerRef.current) clearTimeout(cacheRetryTimerRef.current);
    };
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const applyDiagnosisResult = useCallback((data, fromCache = false) => {
    setCode(data.code || code);
    setSnapshot(data.snapshot);
    setReport(data.report);
    setCached(!!fromCache);
    setError(null);
    message.success(fromCache ? '已从缓存加载诊股' : '诊股完成');
  }, [code]);

  const tryLoadCache = useCallback(async (c, silent = false) => {
    try {
      const res = await apiRequest(`/api/v1/ai-diagnosis/cache?code=${c}`, { timeout: 15000 });
      if (res.success && res.data?.report) {
        applyDiagnosisResult(res.data, true);
        return true;
      }
    } catch (_) {
      /* ignore */
    }
    if (!silent) {
      message.info('缓存尚未就绪，请稍后再点「重新加载」');
    }
    return false;
  }, [applyDiagnosisResult]);

  const runDiagnosis = useCallback(async (targetCode, forceRefresh = false) => {
    const c = (targetCode || code).trim();
    if (!c) {
      message.warning('请输入股票代码');
      return;
    }
    if (!/^\d{6}$/.test(c)) {
      message.warning('请输入6位股票代码');
      return;
    }
    if (cacheRetryTimerRef.current) {
      clearTimeout(cacheRetryTimerRef.current);
      cacheRetryTimerRef.current = null;
    }
    setLoading(true);
    message.info('AI 分析较慢，可先去看其他模块，回来后可继续查看', 6);
    setError(null);
    setMessages([]);
    try {
      const res = await apiRequest('/api/v1/ai-diagnosis', {
        method: 'POST',
        body: JSON.stringify({ code: c, force_refresh: forceRefresh }),
        timeout: DIAGNOSIS_TIMEOUT,
      });
      if (!res.success) {
        const msg = res.message || '诊股失败';
        setError({ type: 'api', message: msg, code: c });
        message.error(msg);
        return;
      }
      setCode(c);
      applyDiagnosisResult(res.data, !!res.data.cached);
    } catch (e) {
      const isTimeout = e.message === '请求超时' || e.name === 'AbortError';
      if (isTimeout) {
        setError({
          type: 'timeout',
          message: '请求超时（已等待 2 分钟）',
          hint: '后端可能仍在分析中。约 10 秒后将自动尝试读取缓存；也可手动点击「重新加载」。',
          code: c,
        });
        message.warning('诊股耗时较长，页面已自动尝试从缓存加载…', 5);
        cacheRetryTimerRef.current = setTimeout(() => tryLoadCache(c, true), 10000);
      } else {
        const msg = e.message || '请求失败';
        setError({ type: 'error', message: msg, code: c });
        message.error(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [code, applyDiagnosisResult, tryLoadCache]);

  useEffect(() => {
    const urlCode = searchParams.get('code')?.trim();
    if (!urlCode) return;
    setCode(urlCode);
    if (/^\d{6}$/.test(urlCode) && urlCode !== lastAutoCodeRef.current) {
      lastAutoCodeRef.current = urlCode;
      runDiagnosis(urlCode, false);
    }
  }, [searchParams, runDiagnosis]);

  const sendChat = useCallback(async () => {
    const text = chatInput.trim();
    if (!text) return;
    if (!report) {
      message.warning('请先完成诊股');
      return;
    }
    const userMsg = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setChatInput('');
    setChatLoading(true);
    try {
      const res = await apiRequest('/api/v1/ai-diagnosis/chat', {
        method: 'POST',
        body: JSON.stringify({
          code: code.trim(),
          message: text,
          context: contextRef.current,
        }),
        timeout: CHAT_TIMEOUT,
      });
      if (!res.success) {
        message.error(res.message || '追问失败');
        return;
      }
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: stripMarkdown(res.data.reply) },
      ]);
    } catch (e) {
      message.error(e.message || '请求失败');
    } finally {
      setChatLoading(false);
    }
  }, [chatInput, code, report]);

  return (
    <div className="ai-diagnosis-page">
      <header className="ai-page-header">
        <div className="ai-page-title">
          <RobotOutlined />
          <span>AI 诊股</span>
        </div>
        <p className="ai-page-desc">
          综合情绪周期、大盘环境、短线生态、龙虎榜、板块热点、分时与大单资金，给出买卖点研判
        </p>
      </header>

      <div className="ai-toolbar">
        <Input
          className="ai-code-input"
          placeholder="股票代码，如 000001"
          value={code}
          onChange={(e) => {
            setCode(e.target.value);
            if (e.target.value) {
              localStorage.setItem(LS_CODE_KEY, e.target.value);
            } else {
              localStorage.removeItem(LS_CODE_KEY);
            }
          }}
          onPressEnter={() => runDiagnosis(code, false)}
          maxLength={12}
        />
        <div className="ai-toolbar-actions">
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={loading}
            onClick={() => runDiagnosis(code, false)}
          >
            开始诊股
          </Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => runDiagnosis(code, true)}>
            强制刷新
          </Button>
          {cached && <Tag color="cyan" className="ai-cache-tag">缓存</Tag>}
        </div>
      </div>

      <HotSearchTags
        onSearchedClick={(c) => {
          setCode(c);
          tryLoadCache(c);
        }}
        onHotClick={(c) => {
          setCode(c);
          runDiagnosis(c, false);
        }}
      />

      {error && (
        <Alert
          className="ai-error-alert"
          type={error.type === 'timeout' ? 'warning' : 'error'}
          showIcon
          message={error.message}
          description={error.hint}
          action={
            <Button
              size="small"
              type="primary"
              onClick={() => {
                if (error.type === 'timeout') {
                  tryLoadCache(error.code || code);
                } else {
                  runDiagnosis(error.code || code, false);
                }
              }}
            >
              重新加载
            </Button>
          }
          closable
          onClose={() => setError(null)}
        />
      )}

      <Spin
        spinning={loading}
        tip="正在聚合行情并调用 AI 分析，首次约 40–90 秒，请勿关闭页面…"
      >
        <div className="ai-main-grid">
          <SnapshotPanel snapshot={snapshot} />
          <ReportPanel report={report} />
        </div>
      </Spin>

      <section className="ai-chat-section">
        <h3 className="ai-chat-title">追问（不保存历史）</h3>
        <div className="ai-chat-messages">
          {messages.length === 0 && (
            <p className="ai-chat-empty">诊股完成后，可在此追问具体操作与风控</p>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`ai-chat-bubble ${m.role === 'user' ? 'user' : 'assistant'}`}
            >
              {m.content}
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
        <div className="ai-chat-input-row">
          <TextArea
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            placeholder="例如：尾盘跌破5日线该怎么处理？"
            autoSize={{ minRows: 1, maxRows: 4 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                sendChat();
              }
            }}
            disabled={!report || chatLoading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={chatLoading}
            onClick={sendChat}
            disabled={!report}
          >
            发送
          </Button>
        </div>
      </section>
    </div>
  );
}

export default AiDiagnosis;
