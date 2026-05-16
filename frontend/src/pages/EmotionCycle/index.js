import React, { useState, useEffect, useCallback } from 'react';
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

// 获取最近交易日（周末自动退到周五）
const getLastTradingDayStr = () => {
  const d = new Date();
  const dow = d.getDay();
  if (dow === 6) d.setDate(d.getDate() - 1); // 周六 -> 周五
  if (dow === 0) d.setDate(d.getDate() - 2); // 周日 -> 周五
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
};

// 日期偏移（跳过周末）
const offsetDate = (dateStr, delta) => {
  const d = new Date(
    parseInt(dateStr.slice(0, 4)),
    parseInt(dateStr.slice(4, 6)) - 1,
    parseInt(dateStr.slice(6, 8))
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

// 格式化日期显示（YYYYMMDD -> YYYY-MM-DD）
const formatDateDisplay = (dateStr) => {
  if (!dateStr || dateStr.length !== 8) return dateStr;
  return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`;
};

function EmotionCycle() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);

  // 新增：日期选择 state
  const [selectedDate, setSelectedDate] = useState(() => getLastTradingDayStr());
  const minDate = records.length > 0 ? records[0].date.replace(/-/g, '') : '20000101';

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

  // 切换日期时自动加载已有的分析结果
  useEffect(() => {
    const loadCachedAnalysis = async () => {
      setAnalysisResult(null);
      try {
        const res = await apiRequest(`/api/v1/emotion-analysis-cache?date=${selectedDate}`);
        if (res?.data) {
          setAnalysisResult(res.data);
        }
      } catch (err) {
        // 无缓存，忽略
      }
    };
    if (records.length > 0) {
      loadCachedAnalysis();
    }
  }, [selectedDate, records.length]);

  // 全量分析：把所有数据传给AI，为每天生成分析，批量存库
  // force: false=只分析新日期, '1'=刷新最近3天, 'all'=全部重刷
  const handleAnalysis = async (force = false) => {
    if (records.length === 0) return;

    setAnalysisLoading(true);
    setAnalysisResult(null);
    try {
      let url = '/api/v1/emotion-analysis-with-storage';
      if (force) url += `?force=${force}`;
      const res = await apiRequest(url, {
        method: 'POST',
        body: JSON.stringify({ records }),
        timeout: 600000,
      });
      if (res?.data) {
        // 分析完成后，加载当前选中日期的缓存
        try {
          const cacheRes = await apiRequest(`/api/v1/emotion-analysis-cache?date=${selectedDate}`);
          if (cacheRes?.data) {
            setAnalysisResult(cacheRes.data);
          }
        } catch (_) { /* ignore */ }
      }
    } catch (err) {
      console.error('Failed to batch analyze:', err);
    } finally {
      setAnalysisLoading(false);
    }
  };

  const getChartOption = () => {
    // 过滤到选中日期的数据
    const filteredRecords = records.filter(r => {
      const rDate = r.date.replace(/-/g, '');
      return rDate <= selectedDate;
    });

    const dates = filteredRecords.map((r) => r.date);

    const series = seriesConfig.map((cfg) => ({
      name: cfg.name,
      type: 'line',
      yAxisIndex: cfg.yAxisIndex,
      smooth: true,
      symbol: cfg.showLabel ? 'circle' : 'none',
      symbolSize: cfg.showLabel ? 6 : 4,
      lineStyle: {
        color: cfg.color,
        width: cfg.showLabel ? 3 : 2,
      },
      itemStyle: { color: cfg.color },
      label: cfg.showLabel
        ? {
            show: true,
            position: 'top',
            color: cfg.color,
            fontSize: 11,
            fontWeight: 'bold',
          }
        : { show: false },
      data: filteredRecords.map((r) => r[cfg.key]),
    }));

    return {
      title: {
        text: '情绪周期走势图',
        left: 'center',
        textStyle: { color: '#fff', fontSize: 16 },
      },
      backgroundColor: 'transparent',
      legend: {
        top: 35,
        left: 'center',
        type: 'scroll',
        textStyle: { color: '#ccc', fontSize: 12 },
        pageTextStyle: { color: '#ccc' },
        pageIconColor: '#aaa',
        pageIconInactiveColor: '#555',
        selected: seriesConfig.reduce((acc, cfg) => {
          acc[cfg.name] = cfg.key === 'consec_limit';
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
      grid: {
        left: 60,
        right: 60,
        bottom: 80,
        top: 80,
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: {
          color: '#999',
          rotate: 45,
          fontSize: 11,
        },
        axisLine: { lineStyle: { color: '#333' } },
      },
      yAxis: [
        {
          type: 'value',
          name: '数值',
          nameTextStyle: { color: '#999' },
          axisLabel: { color: '#999' },
          splitLine: { lineStyle: { color: '#2a2a2a' } },
          axisLine: { lineStyle: { color: '#333' } },
        },
        {
          type: 'value',
          name: '百分比',
          nameTextStyle: { color: '#999' },
          axisLabel: { color: '#999', formatter: '{value}%' },
          splitLine: { show: false },
          axisLine: { lineStyle: { color: '#333' } },
        },
      ],
      dataZoom: [
        {
          type: 'inside',
          start: 0,
          end: 100,
        },
      ],
      series,
    };
  };

  const renderAnalysis = () => {
    if (!analysisResult) return null;

    const { stage, analysis, advice, recommendations } = analysisResult;
    const stageColor = stageColorMap[stage]
      || Object.entries(stageColorMap).find(([k]) => stage?.includes(k))?.[1]
      || '#1890ff';

    return (
      <div className="analysis-content">
        <Tag
          color={stageColor}
          style={{ fontSize: 15, padding: '4px 14px', marginBottom: 12, fontWeight: 'bold' }}
        >
          {stage}
        </Tag>

        {analysis && (
          <div style={{ marginBottom: 12 }}>
            <div className="analysis-section-title">分析</div>
            <div className="analysis-text">{analysis}</div>
          </div>
        )}

        {advice && (
          <div style={{ marginBottom: 12 }}>
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
    );
  };

  return (
    <div className="emotion-cycle-container">
      {/* 日期导航栏 + AI分析按钮 */}
      <div className="emotion-date-nav">
        <Button
          type="text"
          icon={<LeftOutlined />}
          onClick={() => setSelectedDate(offsetDate(selectedDate, -1))}
          disabled={selectedDate <= minDate}
          className="date-nav-btn"
        />
        <span className="date-nav-label">{formatDateDisplay(selectedDate)}</span>
        <Button
          type="text"
          icon={<RightOutlined />}
          onClick={() => setSelectedDate(offsetDate(selectedDate, 1))}
          disabled={selectedDate >= getLastTradingDayStr()}
          className="date-nav-btn"
        />
        <Button
          type="text"
          onClick={() => setSelectedDate(getLastTradingDayStr())}
          className="date-nav-today-btn"
        >
          今日
        </Button>

        <div className="date-nav-ai-btns">
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={() => handleAnalysis(false)}
            loading={analysisLoading}
            disabled={records.length === 0}
            className="ai-analysis-btn"
          >
            AI 情绪分析
          </Button>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            onClick={() => handleAnalysis('1')}
            loading={analysisLoading}
            disabled={records.length === 0}
            className="ai-refresh-btn"
          >
            刷新
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
              notMerge={true}
              lazyUpdate={true}
              theme="dark"
            />
          )}
        </div>

        <div className="ai-analysis-panel">
          {analysisLoading && !analysisResult && (
            <div className="loading-container">
              <Spin size="large" tip="AI 正在分析中..." />
            </div>
          )}

          {analysisResult ? renderAnalysis() : (
            !analysisLoading && (
              <div className="analysis-empty">
                <ThunderboltOutlined style={{ fontSize: 32, color: '#444', marginBottom: 12 }} />
                <div>点击「AI 情绪分析」生成全部日期的分析</div>
                <div style={{ marginTop: 4, fontSize: 12 }}>切换日期可查看对应分析</div>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

export default EmotionCycle;
