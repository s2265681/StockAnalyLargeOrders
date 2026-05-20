import React, { useState, useEffect, useCallback } from 'react';
import { Table, Button, Select, Input, InputNumber, Popconfirm, message, Tooltip, Space } from 'antd';
import { PlusOutlined, DeleteOutlined, ReloadOutlined, BellOutlined, PauseOutlined } from '@ant-design/icons';
import { apiRequest } from '../../config/api';
import './index.css';

const { Option } = Select;

const ALERT_TYPE_OPTIONS = [
  { value: 'limit_up',   label: '涨停' },
  { value: 'limit_down', label: '跌停' },
  { value: 'change_pct', label: '涨跌幅' },
  { value: 'seal_order', label: '涨停封单' },
];

const TYPE_LABELS   = { limit_up: '涨停', limit_down: '跌停', change_pct: '涨跌幅', seal_order: '涨停封单' };
const STATUS_LABELS = { active: '监控中', triggered: '已触发', disabled: '已停用' };

const EMPTY_ROW = () => ({ code: '', alert_type: 'limit_up', threshold: null, direction: 'above', email: '' });

export default function StockAlert() {
  const [rules, setRules]     = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [addRows, setAddRows] = useState([EMPTY_ROW()]);
  const [saving, setSaving]   = useState(false);

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiRequest('/api/alert-rules');
      if (res.success) setRules(res.data.items || []);
    } catch { message.error('加载失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchRules(); }, [fetchRules]);

  const handleAction = async (url, method = 'POST', successMsg = '操作成功') => {
    try {
      const res = await apiRequest(url, { method });
      if (res.success) { message.success(successMsg); fetchRules(); }
      else message.error(res.message);
    } catch { message.error('操作失败'); }
  };

  const updateRow = (idx, field, value) =>
    setAddRows(rows => rows.map((r, i) => i === idx ? { ...r, [field]: value } : r));

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
        setAddRows([EMPTY_ROW()]);
        setShowAdd(false);
        fetchRules();
      } else {
        message.error(res.message || '保存失败');
      }
    } catch { message.error('保存失败'); }
    finally { setSaving(false); }
  };

  const thresholdCell = (row, idx) => {
    if (row.alert_type === 'change_pct') return (
      <Space.Compact style={{ width: '100%' }}>
        <Select value={row.direction} onChange={v => updateRow(idx, 'direction', v)} style={{ width: 80 }}>
          <Option value="above">涨超</Option>
          <Option value="below">跌超</Option>
        </Select>
        <InputNumber value={row.threshold} onChange={v => updateRow(idx, 'threshold', v)}
          min={0.1} max={20} step={0.5} placeholder="%" addonAfter="%" style={{ width: 100 }} />
      </Space.Compact>
    );
    if (row.alert_type === 'seal_order') return (
      <InputNumber value={row.threshold} onChange={v => updateRow(idx, 'threshold', v)}
        min={1} placeholder="封单万元" addonAfter="万元" style={{ width: '100%' }} />
    );
    return <span style={{ color: '#bbb', fontSize: 12, paddingLeft: 4 }}>无需设置</span>;
  };

  const thresholdText = (r) => {
    if (r.alert_type === 'change_pct')
      return `${r.direction === 'above' ? '涨超' : '跌超'}${r.threshold}%`;
    if (r.alert_type === 'seal_order') return `低于 ${r.threshold} 万元`;
    return '—';
  };

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
    { title: '操作', width: 110, render: (_, r) => (
      <Space size={4}>
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
    )},
  ];

  return (
    <div className="alert-page">
      <div className="alert-page-header">
        <h1 className="alert-page-title">
          <BellOutlined style={{ marginRight: 8 }} />条件预警
        </h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowAdd(v => !v)}>
          {showAdd ? '收起' : '新增预警'}
        </Button>
      </div>

      <div className="alert-table-wrap">
        {!loading && rules.length === 0
          ? <div className="alert-empty">暂无预警规则，点击「新增预警」开始设置</div>
          : <Table rowKey="id" columns={columns} dataSource={rules}
              loading={loading} pagination={false} size="small" />}
      </div>

      {showAdd && (
        <div className="alert-add-area">
          <div className="alert-add-title">新增预警规则（最多同时添加 3 条）</div>
          <div className="alert-add-rows">
            {addRows.map((row, idx) => (
              <div className="alert-add-row" key={idx}>
                <Input placeholder="股票代码" value={row.code} maxLength={6}
                  onChange={e => updateRow(idx, 'code', e.target.value.trim())} />
                <Select value={row.alert_type} onChange={v => updateRow(idx, 'alert_type', v)} style={{ width: '100%' }}>
                  {ALERT_TYPE_OPTIONS.map(o => <Option key={o.value} value={o.value}>{o.label}</Option>)}
                </Select>
                {thresholdCell(row, idx)}
                <Input placeholder="收件邮箱" value={row.email}
                  onChange={e => updateRow(idx, 'email', e.target.value.trim())} />
                <Button size="small" danger icon={<DeleteOutlined />}
                  disabled={addRows.length === 1} onClick={() => setAddRows(rows => rows.filter((_, i) => i !== idx))} />
              </div>
            ))}
          </div>
          <div className="alert-add-actions">
            {addRows.length < 3 && (
              <Button icon={<PlusOutlined />} onClick={() => setAddRows(rows => [...rows, EMPTY_ROW()])}>
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
