import React, { useState, useEffect, useCallback } from 'react';
import { Table, Button, Select, Input, InputNumber, Popconfirm, message, Tooltip, Space, Modal, Checkbox } from 'antd';
import { PlusOutlined, DeleteOutlined, ReloadOutlined, BellOutlined, PauseOutlined, EditOutlined } from '@ant-design/icons';
import { apiRequest, apiRequestWithRetry } from '../../config/api';
import { useAuth } from '../../context/AuthContext';
import { stockWS } from '../../services/websocket';
import './index.css';

const { Option } = Select;

const MOBILE_QUERY = '(max-width: 768px)';

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia(MOBILE_QUERY).matches
  );
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY);
    const onChange = (e) => setIsMobile(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isMobile;
}

const ALERT_TYPE_OPTIONS = [
  { value: 'limit_up',   label: '涨停' },
  { value: 'limit_down', label: '跌停' },
  { value: 'change_pct', label: '涨跌幅' },
  { value: 'seal_order', label: '涨停封单' },
];

const TYPE_LABELS   = { limit_up: '涨停', limit_down: '跌停', change_pct: '涨跌幅', seal_order: '涨停封单' };
const STATUS_LABELS = { active: '监控中', triggered: '已触发', disabled: '已停用' };
const RULES_POLL_MS = 5000;

const MONITOR_LABELS = {
  running:  { color: '#52c41a', text: '监控正常' },
  sleeping: { color: '#8c8c8c', text: '非交易时段' },
  error:    { color: '#ff4d4f', text: '监控异常' },
  stopped:  { color: '#ff4d4f', text: '监控未启动' },
};

function MonitorBadge({ status }) {
  const cfg = MONITOR_LABELS[status] || MONITOR_LABELS.stopped;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: cfg.color }}>
      <span style={{
        width: 8, height: 8, borderRadius: '50%', background: cfg.color,
        boxShadow: status === 'running' ? `0 0 0 2px ${cfg.color}33` : 'none',
        display: 'inline-block',
      }} />
      {cfg.text}
    </span>
  );
}

export default function StockAlert() {
  const { user, loading: authLoading } = useAuth();
  const [rules, setRules]         = useState([]);
  const [loading, setLoading]     = useState(false);
  const [showAdd, setShowAdd]     = useState(false);
  const [addRows, setAddRows]     = useState([]);
  const [saving, setSaving]       = useState(false);
  const [monitorStatus, setMonitorStatus] = useState(null);
  const [editingRule, setEditingRule] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [editReactivate, setEditReactivate] = useState(false);
  const [editSaving, setEditSaving] = useState(false);

  const defaultEmail = user?.default_email || '';

  const makeEmptyRow = useCallback((email = defaultEmail) => ({
    _key: Date.now() + Math.random(),
    code: '',
    alert_type: 'limit_up',
    threshold: null,
    direction: 'above',
    email,
  }), [defaultEmail]);

  const notifyNewlyTriggered = useCallback((prev, next) => {
    if (!prev?.length || !next?.length) return;
    next.forEach((item) => {
      const old = prev.find(r => r.id === item.id);
      if (old?.status === 'active' && item.status === 'triggered') {
        const label = TYPE_LABELS[item.alert_type] || item.alert_type;
        message.info(`${item.code} ${label}预警已触发`);
      }
    });
  }, []);

  const fetchRules = useCallback(async (silent = false) => {
    if (!localStorage.getItem('niuniu_token')) return;
    if (!silent) setLoading(true);
    try {
      const res = await apiRequestWithRetry('/api/alert-rules');
      if (res.success) {
        const items = res.data.items || [];
        setRules(prev => {
          if (silent) notifyNewlyTriggered(prev, items);
          return items;
        });
      } else if (!silent) {
        message.error(res.message || '加载失败');
      }
    } catch {
      if (!silent) message.error('加载失败');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [notifyNewlyTriggered]);

  const fetchMonitorStatus = useCallback(async () => {
    if (!localStorage.getItem('niuniu_token')) return;
    try {
      const res = await apiRequestWithRetry('/api/alert-rules/monitor-status');
      if (res.success) setMonitorStatus(res.data.display);
    } catch { /* 静默失败，不影响主流程 */ }
  }, []);

  useEffect(() => {
    if (authLoading || !user) return;
    fetchRules();
  }, [authLoading, user, fetchRules]);

  useEffect(() => {
    if (authLoading || !user) return;
    fetchMonitorStatus();
    const timer = setInterval(fetchMonitorStatus, 30000);
    return () => clearInterval(timer);
  }, [authLoading, user, fetchMonitorStatus]);

  // WebSocket 实时推送 + 静默轮询兜底
  useEffect(() => {
    if (authLoading || !user) return;

    stockWS.connect();
    const offWs = stockWS.onAlertTriggered(() => {
      fetchRules(true);
    });

    const poll = () => {
      if (document.visibilityState === 'visible') fetchRules(true);
    };
    const pollTimer = setInterval(poll, RULES_POLL_MS);

    return () => {
      offWs();
      clearInterval(pollTimer);
    };
  }, [authLoading, user, fetchRules]);

  const handleAction = async (url, method = 'POST', successMsg = '操作成功') => {
    try {
      const res = await apiRequest(url, { method });
      if (res.success) { message.success(successMsg); fetchRules(); }
      else message.error(res.message || '操作失败');
    } catch { message.error('操作失败'); }
  };

  const updateRow = (idx, field, value) =>
    setAddRows(rows => rows.map((r, i) => i === idx ? { ...r, [field]: value } : r));

  const updateEditForm = (field, value) =>
    setEditForm(prev => ({ ...prev, [field]: value }));

  const openEdit = (rule) => {
    setEditingRule(rule);
    setEditForm({
      code: rule.code,
      alert_type: rule.alert_type,
      threshold: rule.threshold,
      direction: rule.direction || (rule.alert_type === 'seal_order' ? 'below' : 'above'),
      email: rule.email,
    });
    setEditReactivate(rule.status !== 'active');
  };

  const closeEdit = () => {
    setEditingRule(null);
    setEditForm(null);
    setEditReactivate(false);
  };

  const handleEditSave = async () => {
    if (!editForm || !editingRule) return;
    if (!editForm.code.trim()) { message.warning('请填写股票代码'); return; }
    if (!editForm.email.trim()) { message.warning('请填写收件邮箱'); return; }
    if (['change_pct', 'seal_order'].includes(editForm.alert_type) && editForm.threshold === null) {
      message.warning('请填写阈值'); return;
    }
    setEditSaving(true);
    try {
      const res = await apiRequest(`/api/alert-rules/${editingRule.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          code: editForm.code.trim(),
          alert_type: editForm.alert_type,
          threshold: editForm.threshold,
          direction: editForm.direction,
          email: editForm.email.trim(),
          reactivate: editReactivate,
        }),
      });
      if (res.success) {
        message.success(res.message || '更新成功');
        closeEdit();
        fetchRules();
      } else {
        message.error(res.message || '更新失败');
      }
    } catch {
      message.error('更新失败');
    } finally {
      setEditSaving(false);
    }
  };

  const handleSave = async () => {
    for (const row of addRows) {
      if (!row.code.trim())  { message.warning('请填写股票代码'); return; }
      if (!row.email.trim()) { message.warning('请填写收件邮箱'); return; }
      if (['change_pct', 'seal_order'].includes(row.alert_type) && row.threshold === null) {
        message.warning('请填写阈值'); return;
      }
    }
    setSaving(true);
    try {
      const res = await apiRequest('/api/alert-rules/batch', {
        method: 'POST',
        body: JSON.stringify({ rules: addRows }),
      });
      if (res.success) {
        message.success(res.message || '保存成功');
        setAddRows([makeEmptyRow()]);
        setShowAdd(false);
        fetchRules();
      } else {
        message.error(res.message || '保存失败');
      }
    } catch { message.error('保存失败'); }
    finally { setSaving(false); }
  };

  const thresholdField = (row, onChange) => {
    if (row.alert_type === 'change_pct') return (
      <div className="alert-threshold-field">
        <Space.Compact className="alert-threshold-compact">
          <Select value={row.direction} onChange={v => onChange('direction', v)} className="alert-threshold-dir">
            <Option value="above">涨超</Option>
            <Option value="below">跌超</Option>
          </Select>
          <InputNumber value={row.threshold} onChange={v => onChange('threshold', v)}
            min={0.1} max={20} step={0.5} placeholder="%" addonAfter="%" className="alert-threshold-num" />
        </Space.Compact>
      </div>
    );
    if (row.alert_type === 'seal_order') return (
      <div className="alert-threshold-field">
        <Space.Compact className="alert-threshold-compact">
          <Select value={row.direction} onChange={v => onChange('direction', v)} className="alert-threshold-dir">
            <Option value="above">超过</Option>
            <Option value="below">低于</Option>
          </Select>
          <InputNumber value={row.threshold} onChange={v => onChange('threshold', v)}
            min={1} step={100} placeholder="手" addonAfter="手" className="alert-threshold-num seal" />
        </Space.Compact>
      </div>
    );
    return <span className="alert-threshold-none">无需设置</span>;
  };

  const thresholdCell = (row, idx) =>
    thresholdField(row, (field, value) => updateRow(idx, field, value));

  const thresholdText = (r) => {
    if (r.alert_type === 'change_pct')
      return `${r.direction === 'above' ? '涨超' : '跌超'}${r.threshold ?? '?'}%`;
    if (r.alert_type === 'seal_order')
      return `${r.direction === 'above' ? '超过' : '低于'} ${r.threshold ?? '?'} 手`;
    return '—';
  };

  const renderRuleActions = (r) => (
    <Space size={4} className="alert-rule-actions">
      <Tooltip title="重新编辑">
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
      </Tooltip>
      {r.status === 'triggered' && (
        <Tooltip title="重新激活">
          <Button size="small" icon={<ReloadOutlined />}
            onClick={() => handleAction(`/api/alert-rules/${r.id}/reactivate`, 'POST', '已激活')} />
        </Tooltip>
      )}
      {r.status === 'active' && (
        <Tooltip title="停用">
          <Button size="small" icon={<PauseOutlined />}
            onClick={() => handleAction(`/api/alert-rules/${r.id}/disable`, 'POST', '已停用')} />
        </Tooltip>
      )}
      <Popconfirm title="确认删除此预警规则？" onConfirm={() => handleAction(`/api/alert-rules/${r.id}`, 'DELETE', '已删除')}
        okText="删除" cancelText="取消">
        <Button size="small" icon={<DeleteOutlined />} danger />
      </Popconfirm>
    </Space>
  );

  const isMobile = useIsMobile();

  const columns = [
    { title: '股票', dataIndex: 'code', width: 90,
      render: (code, r) => <><span style={{ fontWeight: 600 }}>{code}</span><br />
        <span style={{ fontSize: 11, color: '#888' }}>{r.stock_name}</span></> },
    { title: '类型', dataIndex: 'alert_type', width: 90,
      render: t => <span className={`alert-type-tag ${t}`}>{TYPE_LABELS[t] || t}</span> },
    { title: '阈值', width: 130, render: (_, r) => thresholdText(r) },
    { title: '收件邮箱', dataIndex: 'email', ellipsis: true },
    { title: '状态', dataIndex: 'status', width: 85,
      render: s => <span className={`alert-status-tag ${s}`}>{STATUS_LABELS[s] || s}</span> },
    { title: '触发时间', dataIndex: 'triggered_at', width: 145,
      render: t => t || <span style={{ color: '#bbb' }}>—</span> },
    { title: '操作', width: 140, render: (_, r) => renderRuleActions(r) },
  ];

  const renderMobileRuleCard = (r) => (
    <div className="alert-rule-card" key={r.id}>
      <div className="alert-rule-card-head">
        <div className="alert-rule-card-stock">
          <span className="alert-rule-code">{r.code}</span>
          {r.stock_name && <span className="alert-rule-name">{r.stock_name}</span>}
        </div>
        <span className={`alert-status-tag ${r.status}`}>{STATUS_LABELS[r.status] || r.status}</span>
      </div>
      <div className="alert-rule-card-body">
        <div className="alert-rule-card-row">
          <span className="alert-rule-label">类型</span>
          <span className={`alert-type-tag ${r.alert_type}`}>{TYPE_LABELS[r.alert_type] || r.alert_type}</span>
        </div>
        <div className="alert-rule-card-row">
          <span className="alert-rule-label">阈值</span>
          <span className="alert-rule-value">{thresholdText(r)}</span>
        </div>
        <div className="alert-rule-card-row">
          <span className="alert-rule-label">邮箱</span>
          <span className="alert-rule-value alert-rule-email">{r.email}</span>
        </div>
        {r.triggered_at && (
          <div className="alert-rule-card-row">
            <span className="alert-rule-label">触发</span>
            <span className="alert-rule-value">{r.triggered_at}</span>
          </div>
        )}
      </div>
      <div className="alert-rule-card-foot">{renderRuleActions(r)}</div>
    </div>
  );

  return (
    <div className="alert-page">
      <div className="alert-page-header">
        <h1 className="alert-page-title">
          <BellOutlined style={{ marginRight: 8 }} />条件预警
          {monitorStatus && (
            <span style={{ marginLeft: 12, fontWeight: 400 }}>
              <MonitorBadge status={monitorStatus} />
            </span>
          )}
        </h1>
        <Button type="primary" icon={<PlusOutlined />}
          onClick={() => setShowAdd(v => {
            if (!v) setAddRows([makeEmptyRow()]);
            return !v;
          })}
          className="alert-add-btn">
          {showAdd ? '收起' : '新增预警'}
        </Button>
      </div>

      <div className="alert-table-wrap">
        {!loading && rules.length === 0 ? (
          <div className="alert-empty">暂无预警规则，点击「新增预警」开始设置</div>
        ) : isMobile ? (
          <div className="alert-card-list">
            {loading ? <div className="alert-loading">加载中…</div> : rules.map(renderMobileRuleCard)}
          </div>
        ) : (
          <Table rowKey="id" columns={columns} dataSource={rules}
            loading={loading} pagination={false} size="small" />
        )}
      </div>

      <Modal
        title={`编辑预警 · ${editingRule?.code || ''}`}
        open={!!editingRule}
        onCancel={closeEdit}
        onOk={handleEditSave}
        confirmLoading={editSaving}
        okText="保存"
        cancelText="取消"
        destroyOnClose
        className="alert-edit-modal"
      >
        {editForm && (
          <div className="alert-edit-form">
            <div className="alert-edit-field">
              <label className="alert-edit-label">股票代码</label>
              <Input value={editForm.code} maxLength={6}
                onChange={e => updateEditForm('code', e.target.value.trim())} />
            </div>
            <div className="alert-edit-field">
              <label className="alert-edit-label">预警类型</label>
              <Select value={editForm.alert_type} onChange={v => updateEditForm('alert_type', v)}>
                {ALERT_TYPE_OPTIONS.map(o => <Option key={o.value} value={o.value}>{o.label}</Option>)}
              </Select>
            </div>
            <div className="alert-edit-field">
              <label className="alert-edit-label">阈值</label>
              {thresholdField(editForm, updateEditForm)}
            </div>
            <div className="alert-edit-field">
              <label className="alert-edit-label">收件邮箱</label>
              <Input value={editForm.email}
                onChange={e => updateEditForm('email', e.target.value.trim())} />
            </div>
            {editingRule?.status !== 'active' && (
              <Checkbox checked={editReactivate} onChange={e => setEditReactivate(e.target.checked)}>
                保存后重新激活监控
              </Checkbox>
            )}
          </div>
        )}
      </Modal>

      {showAdd && (
        <div className="alert-add-area">
          <div className="alert-add-title">新增预警规则（最多同时添加 3 条）</div>
          <div className="alert-add-rows">
            {addRows.map((row, idx) => (
              <div className="alert-add-row" key={row._key}>
                <div className="alert-field">
                  <label className="alert-field-label">股票代码</label>
                  <Input placeholder="如 600519" value={row.code} maxLength={6}
                    onChange={e => updateRow(idx, 'code', e.target.value.trim())} />
                </div>
                <div className="alert-field">
                  <label className="alert-field-label">预警类型</label>
                  <Select value={row.alert_type} onChange={v => updateRow(idx, 'alert_type', v)}>
                    {ALERT_TYPE_OPTIONS.map(o => <Option key={o.value} value={o.value}>{o.label}</Option>)}
                  </Select>
                </div>
                <div className="alert-field alert-field-threshold">
                  <label className="alert-field-label">阈值</label>
                  {thresholdCell(row, idx)}
                </div>
                <div className="alert-field">
                  <label className="alert-field-label">收件邮箱</label>
                  <Input placeholder="your@email.com" value={row.email}
                    onChange={e => updateRow(idx, 'email', e.target.value.trim())} />
                </div>
                <Button className="alert-row-delete" size="small" danger icon={<DeleteOutlined />}
                  disabled={addRows.length === 1} onClick={() => setAddRows(rows => rows.filter((_, i) => i !== idx))} />
              </div>
            ))}
          </div>
          <div className="alert-add-actions">
            {addRows.length < 3 && (
              <Button icon={<PlusOutlined />} onClick={() => setAddRows(rows => [...rows, makeEmptyRow()])}>
                再加一条
              </Button>
            )}
            <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
          </div>
        </div>
      )}
    </div>
  );
}
