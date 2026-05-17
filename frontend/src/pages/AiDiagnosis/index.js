import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Input, Button, Spin, Tag, message } from 'antd';
import {
  RobotOutlined,
  SendOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { apiRequest } from '../../config/api';
import './index.css';

const { TextArea } = Input;

const RATING_COLOR = {
  偏多: 'red',
  中性: 'gold',
  偏空: 'green',
};

function renderMarkdownText(text) {
  if (!text) return null;
  return text.split('\n').map((line, i) => {
    const chunks = line.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
    return (
      <p key={`line-${i}`} className="ai-md-line">
        {chunks.map((chunk, j) => {
          const m = chunk.match(/^\*\*([\s\S]+)\*\*$/);
          if (m) return <strong key={j}>{m[1]}</strong>;
          return <span key={j}>{chunk}</span>;
        })}
      </p>
    );
  });
}

function SnapshotPanel({ snapshot }) {
  if (!snapshot) return null;
  const q = snapshot.quote || {};
  const l2 = snapshot.l2 || {};
  const lo = snapshot.large_orders || {};
  const em = snapshot.emotion || {};
  const au = snapshot.auction || {};
  const th = snapshot.theme || {};

  return (
    <div className="ai-snapshot-panel">
      <div className="ai-snapshot-title">数据快照</div>
      {snapshot.partial && (
        <Tag color="orange" className="ai-partial-tag">部分数据缺失</Tag>
      )}
      <div className="ai-snapshot-grid">
        <div className="ai-snap-card">
          <span className="label">行情</span>
          <span className="value">
            {q.name || '--'} {q.price != null ? q.price : '--'}
            {q.change_percent != null && (
              <em className={q.change_percent >= 0 ? 'up' : 'down'}>
                {' '}
                {q.change_percent >= 0 ? '+' : ''}
                {q.change_percent}%
              </em>
            )}
          </span>
        </div>
        <div className="ai-snap-card">
          <span className="label">L2</span>
          <span className="value">
            大单净额 {l2.large_order_net ?? '--'} · 封板 {l2.limit_up_status || '--'}
          </span>
        </div>
        <div className="ai-snap-card">
          <span className="label">资金</span>
          <span className="value">主力净流入 {lo.main_net ?? l2.main_net_inflow ?? '--'}</span>
        </div>
        <div className="ai-snap-card">
          <span className="label">情绪周期</span>
          <span className="value">
            {em.available ? `${em.stage || '--'} · ${(em.advice || '').slice(0, 40)}` : '暂无缓存'}
          </span>
        </div>
        <div className="ai-snap-card">
          <span className="label">竞价抢筹</span>
          <span className="value">
            {au.in_list
              ? `在榜 · 抢筹涨幅 ${au.grab_change_pct ?? '--'}%`
              : '未在早盘抢筹榜'}
          </span>
        </div>
        <div className="ai-snap-card">
          <span className="label">题材</span>
          <span className="value">
            {th.theme || '无明确题材'}
            {th.theme ? ` · ${th.position} · 同题材${th.theme_count}家` : ''}
          </span>
        </div>
      </div>
      <p className="ai-snap-time">快照时间 {snapshot.assembled_at || '--'}</p>
    </div>
  );
}

function ReportPanel({ report }) {
  if (!report) return null;
  return (
    <div className="ai-report-panel">
      <div className="ai-report-header">
        <Tag color={RATING_COLOR[report.rating] || 'default'}>{report.rating || '—'}</Tag>
        <Tag>{report.theme_position || '—'}</Tag>
        <Tag color="blue">{report.position_advice || '—'}</Tag>
      </div>
      <p className="ai-report-summary">{report.summary}</p>
      <div className="ai-report-section">
        <h4>情绪适配</h4>
        <p>{report.emotion_fit}</p>
      </div>
      <div className="ai-report-columns">
        <div>
          <h4>买点</h4>
          <ul>
            {(report.buy_points || []).map((t, i) => (
              <li key={`b-${i}`}>{t}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>卖点</h4>
          <ul>
            {(report.sell_points || []).map((t, i) => (
              <li key={`s-${i}`}>{t}</li>
            ))}
          </ul>
        </div>
      </div>
      <p className="ai-stop-loss">
        <strong>止损：</strong>
        {report.stop_loss}
      </p>
      {(report.risk_warnings || []).length > 0 && (
        <div className="ai-risks">
          {(report.risk_warnings || []).map((r, i) => (
            <Tag key={i} color="volcano">
              {r}
            </Tag>
          ))}
        </div>
      )}
      <div className="ai-report-detail">{renderMarkdownText(report.detail_markdown)}</div>
    </div>
  );
}

function AiDiagnosis() {
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [report, setReport] = useState(null);
  const [cached, setCached] = useState(false);
  const [messages, setMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const chatEndRef = useRef(null);

  const contextRef = useRef({ snapshot: null, report: null });
  useEffect(() => {
    contextRef.current = { snapshot, report };
  }, [snapshot, report]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const runDiagnosis = useCallback(
    async (forceRefresh = false) => {
      const c = code.trim();
      if (!c) {
        message.warning('请输入股票代码');
        return;
      }
      setLoading(true);
      setMessages([]);
      try {
        const res = await apiRequest('/api/v1/ai-diagnosis', {
          method: 'POST',
          body: JSON.stringify({ code: c, force_refresh: forceRefresh }),
        });
        if (!res.success) {
          message.error(res.message || '诊股失败');
          return;
        }
        setSnapshot(res.data.snapshot);
        setReport(res.data.report);
        setCached(!!res.data.cached);
        message.success(res.data.cached ? '已加载缓存诊股' : '诊股完成');
      } catch (e) {
        message.error(e.message || '请求失败');
      } finally {
        setLoading(false);
      }
    },
    [code]
  );

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
      });
      if (!res.success) {
        message.error(res.message || '追问失败');
        return;
      }
      setMessages((prev) => [...prev, { role: 'assistant', content: res.data.reply }]);
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
        <p className="ai-page-desc">综合 L2、大单、情绪周期、竞价抢筹与当天题材，给出买卖点研判</p>
      </header>

      <div className="ai-toolbar">
        <Input
          className="ai-code-input"
          placeholder="股票代码，如 000001"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onPressEnter={() => runDiagnosis(false)}
          maxLength={12}
        />
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={loading}
          onClick={() => runDiagnosis(false)}
        >
          开始诊股
        </Button>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => runDiagnosis(true)}>
          强制刷新
        </Button>
        {cached && <Tag color="cyan">缓存</Tag>}
      </div>

      <Spin spinning={loading} tip="AI 分析中，约需 30–90 秒…">
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
              {m.role === 'assistant' ? renderMarkdownText(m.content) : m.content}
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
