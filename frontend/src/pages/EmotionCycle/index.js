import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Button, Spin, Tag } from 'antd';
import { ThunderboltOutlined, LeftOutlined, RightOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  ToolboxComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { apiRequest } from '../../config/api';
import { useAuth } from '../../context/AuthContext';
import './index.css';


echarts.use([
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  ToolboxComponent,
  CanvasRenderer,
]);

const stageColorMap = {
  '冰点期': '#1677ff',
  '冰点': '#1677ff',
  '修复期': '#13c2c2',
  '修复': '#13c2c2',
  '升温期': '#fa8c16',
  '升温': '#fa8c16',
  '高潮期': '#f5222d',
  '高潮': '#f5222d',
  '退潮期': '#52c41a',
  '退潮': '#52c41a',
};

const seriesConfig = [
  { key: 'rise_pct', name: '上涨比例', color: '#faad14', yAxisIndex: 1 },
  { key: 'consec_limit', name: '连板家数', color: '#52c41a', yAxisIndex: 0, showLabel: true },
  { key: 'pressure_height', name: '压力高度', color: '#ff7a45', yAxisIndex: 0 },
  { key: 'latest_height', name: '最新高度', color: '#ff4d4f', yAxisIndex: 0 },
  { key: 'big_loss_mood', name: '大面情绪', color: '#597ef7', yAxisIndex: 0 },
  { key: 'big_profit_mood', name: '大肉情绪', color: '#9254de', yAxisIndex: 0 },
  { key: 'limit_up_count', name: '涨停家数', color: '#f759ab', yAxisIndex: 0 },
  { key: 'board_hit_rate', name: '打板成功率', color: '#36cfc9', yAxisIndex: 1 },
  { key: 'limit_down_count', name: '跌停家数', color: '#40a9ff', yAxisIndex: 0 },
];

const getLastTradingDayStr = () => {
  const d = new Date();
  const dow = d.getDay();
  if (dow === 6) d.setDate(d.getDate() - 1);
  if (dow === 0) d.setDate(d.getDate() - 2);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
};

const offsetDate = (dateStr, delta) => {
  const d = new Date(
    parseInt(dateStr.slice(0, 4), 10),
    parseInt(dateStr.slice(4, 6), 10) - 1,
    parseInt(dateStr.slice(6, 8), 10)
  );
  let count = 0;
  const step = delta > 0 ? 1 : -1;
  while (count !== delta) {
    d.setDate(d.getDate() + step);
    const dow = d.getDay();
    if (dow !== 0 && dow !== 6) count += step;
  }
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
};

const formatDateDisplay = (dateStr) => {
  if (!dateStr || dateStr.length !== 8) return dateStr;
  return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`;
};

const getLatestRecordDate = (items) => {
  if (!items || items.length === 0) return null;
  const sortedDates = items
    .map((item) => item.date?.replace(/-/g, ''))
    .filter(Boolean)
    .sort();
  return sortedDates[sortedDates.length - 1] || null;
};

function AnalysisBlock({ title, accent, result, loading, emptyHint }) {
  if (loading && !result) {
    return (
      <div className={`analysis-panel-block analysis-panel-${accent}`}>
        <div className="analysis-panel-title">{title}</div>
        <div className="loading-container" style={{ padding: '24px 0' }}>
          <Spin tip="加载中..." />
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className={`analysis-panel-block analysis-panel-${accent}`}>
        <div className="analysis-panel-title">{title}</div>
        <div className="analysis-empty compact">{emptyHint}</div>
      </div>
    );
  }

  const { stage, analysis, advice, recommendations, updated_at: updatedAt } = result;
  const stageColor = stageColorMap[stage]
    || Object.entries(stageColorMap).find(([k]) => stage?.includes(k))?.[1]
    || '#1890ff';

  return (
    <div className={`analysis-panel-block analysis-panel-${accent}`}>
      <div className="analysis-panel-title">
        {title}
        {updatedAt && (
          <span className="analysis-updated-at">更新 {String(updatedAt).slice(0, 16)}</span>
        )}
      </div>
      <div className="analysis-content">
        <Tag
          color={stageColor}
          style={{ fontSize: 14, padding: '2px 12px', marginBottom: 10, fontWeight: 'bold' }}
        >
          {stage}
        </Tag>

        {analysis && (
          <div style={{ marginBottom: 10 }}>
            <div className="analysis-section-title">分析</div>
            <div className="analysis-text">{analysis}</div>
          </div>
        )}

        {advice && (
          <div style={{ marginBottom: 10 }}>
            <div className="analysis-section-title">建议</div>
            <div className="advice-text">{advice}</div>
          </div>
        )}

        {recommendations && recommendations.length > 0 && (
          <div>
            <div className="analysis-section-title">备选标的</div>
            <div className="recommendations-list">
              {recommendations.map((rec, idx) => (
                <div key={idx} className="recommendation-item">
                  <div className="rec-header">
                    <span className="rec-stock">{rec.stock}</span>
                    {rec.position && <Tag color="blue" style={{ fontSize: 11 }}>{rec.position}</Tag>}
                  </div>
                  <div className="rec-reason">{rec.reason}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function EmotionCycle() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const todayStr = useMemo(() => getLastTradingDayStr(), []);

  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [batchLoading, setBatchLoading] = useState(false);
  const [intradayLoading, setIntradayLoading] = useState(false);
  const [cycleAnalysis, setCycleAnalysis] = useState(null);
  const [intradayAnalysis, setIntradayAnalysis] = useState(null);
  const [selectedDate, setSelectedDate] = useState(() => getLastTradingDayStr());

  const minDate = records.length > 0 ? records[0].date.replace(/-/g, '') : '20000101';
  const latestDate = getLatestRecordDate(records);
  const isTodaySelected = selectedDate === todayStr && selectedDate === latestDate;

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiRequest('/api/v1/emotion-cycle');
      if (res?.data?.records) {
        setRecords(res.data.records);
      }
    } catch (err) {
      console.error('Failed to fetch emotion cycle data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const loadCycleCache = async () => {
      setCycleAnalysis(null);
      try {
        const res = await apiRequest(`/api/v1/emotion-analysis-cache?date=${selectedDate}`);
        if (res?.data) setCycleAnalysis(res.data);
      } catch (_) { /* ignore */ }
    };
    if (records.length > 0) loadCycleCache();
  }, [selectedDate, records.length]);

  useEffect(() => {
    const loadIntradayCache = async () => {
      setIntradayAnalysis(null);
      if (!isTodaySelected) return;
      try {
        const res = await apiRequest(`/api/v1/emotion-intraday-cache?date=${selectedDate}`);
        if (res?.data) setIntradayAnalysis(res.data);
      } catch (_) { /* ignore */ }
    };
    if (records.length > 0) loadIntradayCache();
  }, [selectedDate, records.length, isTodaySelected]);

  const handleBatchAnalysis = async (force = false) => {
    if (!isAdmin || records.length === 0) return;
    setBatchLoading(true);
    try {
      let url = '/api/v1/emotion-analysis-with-storage';
      if (force) url += `?force=${force}`;
      await apiRequest(url, {
        method: 'POST',
        body: JSON.stringify({ records }),
        timeout: 600000,
      });
      const cacheRes = await apiRequest(`/api/v1/emotion-analysis-cache?date=${selectedDate}`);
      if (cacheRes?.data) setCycleAnalysis(cacheRes.data);
    } catch (err) {
      console.error('Failed to batch analyze:', err);
    } finally {
      setBatchLoading(false);
    }
  };

  const handleIntradayRefresh = async () => {
    if (!isTodaySelected) return;
    setIntradayLoading(true);
    setIntradayAnalysis(null);
    try {
      const res = await apiRequest('/api/v1/emotion-intraday-refresh', {
        method: 'POST',
        timeout: 240000,
      });
      if (res?.data?.intraday) setIntradayAnalysis(res.data.intraday);
      if (res?.data?.records) setRecords(res.data.records);
    } catch (err) {
      console.error('Failed to refresh intraday analysis:', err);
    } finally {
      setIntradayLoading(false);
    }
  };

  const getChartOption = () => {
    const isLightTheme =
      typeof document !== 'undefined' &&
      document.documentElement.getAttribute('data-theme') === 'light';
    const legendTextColor = isLightTheme ? '#595959' : '#ccc';
    const axisTextColor = isLightTheme ? '#666' : '#999';
    const axisLineColor = isLightTheme ? '#c9c9c9' : '#333';
    const splitLineColor = isLightTheme ? '#e6e6e6' : '#2a2a2a';

    const filteredRecords = records.filter((r) => r.date.replace(/-/g, '') <= selectedDate);
    const dates = filteredRecords.map((r) => r.date);

    const series = seriesConfig.map((cfg) => ({
      name: cfg.name,
      type: 'line',
      yAxisIndex: cfg.yAxisIndex,
      smooth: true,
      symbol: cfg.showLabel ? 'circle' : 'none',
      symbolSize: cfg.showLabel ? 6 : 4,
      lineStyle: { color: cfg.color, width: cfg.showLabel ? 3 : 2 },
      itemStyle: { color: cfg.color },
      label: cfg.showLabel
        ? { show: true, position: 'top', color: cfg.color, fontSize: 11, fontWeight: 'bold' }
        : { show: false },
      data: filteredRecords.map((r) => r[cfg.key]),
    }));

    return {
      title: {
        text: '情绪周期走势图',
        left: 'center',
        textStyle: { color: isLightTheme ? '#262626' : '#fff', fontSize: 16 },
      },
      backgroundColor: 'transparent',
      legend: {
        top: 35,
        left: 'center',
        type: 'scroll',
        textStyle: { color: legendTextColor, fontSize: 12, fontWeight: 500 },
        pageTextStyle: { color: legendTextColor },
        pageIconColor: isLightTheme ? '#8c8c8c' : '#aaa',
        pageIconInactiveColor: '#555',
        selected: seriesConfig.reduce((acc, cfg) => {
          acc[cfg.name] = true;
          return acc;
        }, {}),
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(30,29,30,0.95)',
        borderColor: '#444',
        textStyle: { color: '#eee', fontSize: 12 },
        formatter: (params) => {
          if (!params || params.length === 0) return '';
          let html = `<div style="font-weight:bold;margin-bottom:6px;">${params[0].axisValue}</div>`;
          params.forEach((p) => {
            const cfg = seriesConfig.find((s) => s.name === p.seriesName);
            const suffix = cfg && cfg.yAxisIndex === 1 ? '%' : '';
            html += `<div style="display:flex;justify-content:space-between;gap:16px;">
              <span>${p.marker} ${p.seriesName}</span>
              <span style="font-weight:bold;">${p.value != null ? p.value + suffix : '-'}</span>
            </div>`;
          });
          return html;
        },
      },
      grid: { left: 60, right: 60, bottom: 80, top: 80 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { color: axisTextColor, rotate: 45, fontSize: 11 },
        axisLine: { lineStyle: { color: axisLineColor } },
      },
      yAxis: [
        {
          type: 'value',
          name: '数值',
          nameTextStyle: { color: axisTextColor },
          axisLabel: { color: axisTextColor },
          splitLine: { lineStyle: { color: splitLineColor } },
          axisLine: { lineStyle: { color: axisLineColor } },
        },
        {
          type: 'value',
          name: '百分比',
          nameTextStyle: { color: axisTextColor },
          axisLabel: { color: axisTextColor, formatter: '{value}%' },
          splitLine: { show: false },
          axisLine: { lineStyle: { color: axisLineColor } },
        },
      ],
      dataZoom: [{ type: 'inside', start: 0, end: 100 }],
      series,
    };
  };

  return (
    <div className="emotion-cycle-container">
      <div className="emotion-date-nav">
        <button
          type="button"
          className="date-nav-btn"
          onClick={() => setSelectedDate(offsetDate(selectedDate, -1))}
          disabled={selectedDate <= minDate}
        >
          <LeftOutlined /> 前一天
        </button>
        <span className="date-nav-label">{formatDateDisplay(selectedDate)}</span>
        <button
          type="button"
          className="date-nav-btn"
          onClick={() => setSelectedDate(offsetDate(selectedDate, 1))}
          disabled={selectedDate >= todayStr}
        >
          后一天 <RightOutlined />
        </button>
        <button
          type="button"
          className="date-nav-btn date-nav-today"
          onClick={() => setSelectedDate(todayStr)}
        >
          今天
        </button>

        <div className="date-nav-ai-btns">
          {isAdmin && (
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={() => handleBatchAnalysis(false)}
              loading={batchLoading}
              disabled={records.length === 0}
              className="ai-analysis-btn admin-batch-btn"
            >
              全量生成
            </Button>
          )}
          <Button
            type={isAdmin ? 'default' : 'primary'}
            icon={<ReloadOutlined />}
            onClick={handleIntradayRefresh}
            loading={intradayLoading}
            disabled={records.length === 0 || !isTodaySelected}
            className="ai-refresh-btn"
          >
            盘中刷新
          </Button>
        </div>
      </div>

      <div className="emotion-main-layout">
        <div className="emotion-chart-card">
          {loading ? (
            <div className="loading-container">
              <Spin size="large" tip="加载中..." />
            </div>
          ) : (
            <ReactEChartsCore
              echarts={echarts}
              option={getChartOption()}
              style={{ height: 'calc(100vh - 160px)', minHeight: 400 }}
              notMerge
              lazyUpdate
              theme="dark"
            />
          )}
        </div>

        <div className="emotion-right-column">
          <AnalysisBlock
            title="周期研判"
            accent="cycle"
            result={cycleAnalysis}
            loading={batchLoading}
            emptyHint="暂无周期研判，请联系管理员生成"
          />
          <AnalysisBlock
            title="盘中研判"
            accent="intraday"
            result={isTodaySelected ? intradayAnalysis : null}
            loading={intradayLoading}
            emptyHint={
              isTodaySelected
                ? '点击「盘中刷新」生成当日研判'
                : '仅支持查看/刷新当日盘中研判'
            }
          />
        </div>
      </div>
    </div>
  );
}

export default EmotionCycle;
