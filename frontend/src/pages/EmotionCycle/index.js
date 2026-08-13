import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Button, Spin, Tag } from 'antd';
import { LeftOutlined, RightOutlined, ReloadOutlined } from '@ant-design/icons';
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
import MarketBriefBar from '../../components/MarketBriefBar';
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
  { key: 'rise_ratio', name: '上涨比例', color: '#faad14', yAxisIndex: 0 },
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

/** 登录用户可见「生成/刷新」；进入页面时缓存缺失会自动补生成 */
const SHOW_PANEL_REFRESH_BTN = true;

const buildMockRecords = () => {
  const base = getLastTradingDayStr();
  const stages = ['冰点期', '修复期', '升温期', '高潮期', '退潮期'];
  const rows = [];
  for (let i = 19; i >= 0; i -= 1) {
    const d = offsetDate(base, -i);
    const phase = (19 - i) / 19;
    const wave = Math.sin(phase * Math.PI);
    rows.push({
      date: formatDateDisplay(d),
      stage: stages[Math.min(stages.length - 1, Math.floor(phase * stages.length))],
      rise_ratio: Math.round(30 + wave * 45),
      consec_limit: Math.round(2 + wave * 6),
      pressure_height: Math.round(3 + wave * 5),
      latest_height: Math.round(2 + wave * 6),
      big_loss_mood: Math.round(20 + (1 - wave) * 40),
      big_profit_mood: Math.round(25 + wave * 50),
      limit_up_count: Math.round(20 + wave * 60),
      board_hit_rate: Math.round(35 + wave * 40),
      limit_down_count: Math.round(15 - wave * 10),
    });
  }
  return rows;
};

const MOCK_CYCLE_ANALYSIS = {
  stage: '升温期',
  updated_at: '2026-01-01 09:30',
  analysis: '市场情绪逐步回暖，连板高度抬升，赚钱效应扩散，资金开始向强势主线集中。上涨比例回升至中枢上方，短线情绪进入良性循环。',
  advice: '可逢低参与主线龙头及首板卡位，控制仓位，注意分歧转一致的节奏，避免追高低位补涨股。',
  trade_plans: [
    {
      stock: '示例龙头 000000',
      technique: '低吸',
      position: '3成',
      entry: '分时回踩均价线企稳',
      exit: '尾盘冲高或次日高开兑现',
      timing: '早盘弱转强',
      reason: '主线人气标的，承接情绪扩散。数据为演示样例。',
    },
  ],
  recommendations: [
    { stock: '示例标的 000001', position: '2成', reason: '板块补涨候选，演示数据。' },
    { stock: '示例标的 000002', position: '1成', reason: '低位首板卡位，演示数据。' },
  ],
};

const MOCK_INTRADAY_ANALYSIS = {
  stage: '升温期',
  updated_at: '2026-01-01 13:00',
  analysis: '盘中量能温和放大，热点轮动加快，指数震荡上行。打板成功率维持在中性偏强区间。',
  prev_day_review: '昨日高潮标的分歧后修复，验证情绪仍在升温通道，节奏未破坏。',
  advice: '盘中可等回踩低吸主线，急拉不追，尾盘视情绪强弱决定是否加仓。以上为演示样例。',
};

const getLatestRecordDate = (items) => {
  if (!items || items.length === 0) return null;
  const sortedDates = items
    .map((item) => item.date?.replace(/-/g, ''))
    .filter(Boolean)
    .sort();
  return sortedDates[sortedDates.length - 1] || null;
};

function AnalysisBlock({ title, accent, result, loading, emptyHint, extra, children }) {
  const content = (() => {
    if (loading && !result) {
      return (
        <>
          <div className="analysis-panel-title">
            <span>{title}</span>
            {extra && <span className="analysis-panel-extra">{extra}</span>}
          </div>
          <div className="loading-container" style={{ padding: '24px 0' }}>
            <Spin tip="加载中..." />
          </div>
        </>
      );
    }

    if (!result) {
      return (
        <>
          <div className="analysis-panel-title">
            <span>{title}</span>
            {extra && <span className="analysis-panel-extra">{extra}</span>}
          </div>
          <div className="analysis-empty compact">{emptyHint}</div>
        </>
      );
    }

    const {
      stage,
      analysis,
      advice,
      prev_day_review: prevDayReview,
      recommendations,
      trade_plans: tradePlans,
      updated_at: updatedAt,
    } = result;
    const stageColor = stageColorMap[stage]
      || Object.entries(stageColorMap).find(([k]) => stage?.includes(k))?.[1]
      || '#1890ff';

    return (
      <>
        <div className="analysis-panel-title">
          <span>{title}</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {updatedAt && (
              <span className="analysis-updated-at">更新 {String(updatedAt).slice(0, 16)}</span>
            )}
            {extra && <span className="analysis-panel-extra">{extra}</span>}
          </span>
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

          {prevDayReview && (
            <div style={{ marginBottom: 10 }}>
              <div className="analysis-section-title">昨日复盘修正</div>
              <div className="analysis-text prev-review-text">{prevDayReview}</div>
            </div>
          )}

          {advice && (
            <div style={{ marginBottom: 10 }}>
              <div className="analysis-section-title">操作建议</div>
              <div className="advice-text">{advice}</div>
            </div>
          )}

          {tradePlans && tradePlans.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div className="analysis-section-title">买卖点与进出场</div>
              <div className="trade-plans-list">
                {tradePlans.map((plan, idx) => (
                  <div key={idx} className="trade-plan-item">
                    <div className="rec-header">
                      <span className="rec-stock">{plan.stock}</span>
                      {plan.technique && (
                        <Tag color="volcano" style={{ fontSize: 11 }}>{plan.technique}</Tag>
                      )}
                      {plan.position && (
                        <Tag color="blue" style={{ fontSize: 11 }}>{plan.position}</Tag>
                      )}
                    </div>
                    {plan.entry && (
                      <div className="trade-plan-row">
                        <span className="trade-plan-label">买点</span>
                        <span>{plan.entry}</span>
                      </div>
                    )}
                    {plan.exit && (
                      <div className="trade-plan-row">
                        <span className="trade-plan-label">卖点</span>
                        <span>{plan.exit}</span>
                      </div>
                    )}
                    {plan.timing && (
                      <div className="trade-plan-row">
                        <span className="trade-plan-label">时机</span>
                        <span>{plan.timing}</span>
                      </div>
                    )}
                    {plan.reason && <div className="rec-reason">{plan.reason}</div>}
                  </div>
                ))}
              </div>
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
      </>
    );
  })();

  return (
    <div className={`analysis-panel-block analysis-panel-${accent}`}>
      {content}
      {children && (
        <div className="analysis-panel-children">{children}</div>
      )}
    </div>
  );
}

function EmotionCycle({ preview = false }) {
  const todayStr = useMemo(() => getLastTradingDayStr(), []);

  const [records, setRecords] = useState(() => (preview ? buildMockRecords() : []));
  const [loading, setLoading] = useState(!preview);
  const [panelRefreshing, setPanelRefreshing] = useState(false);
  const [cacheChecked, setCacheChecked] = useState(preview);
  const [cycleAnalysis, setCycleAnalysis] = useState(preview ? MOCK_CYCLE_ANALYSIS : null);
  const [intradayAnalysis, setIntradayAnalysis] = useState(preview ? MOCK_INTRADAY_ANALYSIS : null);
  const [selectedDate, setSelectedDate] = useState(() => getLastTradingDayStr());
  const autoRefreshAttemptedRef = useRef(new Set());

  const minDate = records.length > 0 ? records[0].date.replace(/-/g, '') : '20000101';
  const latestDate = getLatestRecordDate(records);
  const navMaxDate = latestDate && latestDate < todayStr ? latestDate : todayStr;
  const hasSelectedRecord = records.some(
    (r) => r.date?.replace(/-/g, '') === selectedDate
  );

  // 默认日期用日历「最近工作日」，但行情/分析可能仍停在上一交易日；对齐到有数据的最新日
  useEffect(() => {
    if (!latestDate) return;
    const hasCurrent = records.some((r) => r.date?.replace(/-/g, '') === selectedDate);
    if (!hasCurrent) {
      setSelectedDate(latestDate);
    }
  }, [records, latestDate, selectedDate]);

  const fetchData = useCallback(async () => {
    if (preview) return;
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
  }, [preview]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (preview) return;
    const loadCaches = async () => {
      setCacheChecked(false);
      setCycleAnalysis(null);
      setIntradayAnalysis(null);
      if (records.length === 0) {
        setCacheChecked(true);
        return;
      }
      try {
        const [cycleRes, intradayRes] = await Promise.all([
          apiRequest(`/api/v1/emotion-analysis-cache?date=${selectedDate}`),
          hasSelectedRecord
            ? apiRequest(`/api/v1/emotion-intraday-cache?date=${selectedDate}`)
            : Promise.resolve(null),
        ]);
        if (cycleRes?.data) setCycleAnalysis(cycleRes.data);
        if (intradayRes?.data) setIntradayAnalysis(intradayRes.data);
      } catch (_) { /* ignore */ } finally {
        setCacheChecked(true);
      }
    };
    loadCaches();
  }, [selectedDate, records.length, hasSelectedRecord, preview]);

  const handlePanelRefresh = useCallback(async (options = {}) => {
    const { force = true, silent = false } = options;
    if (!hasSelectedRecord) return;
    if (!localStorage.getItem('niuniu_token')) return;

    if (!silent) setPanelRefreshing(true);
    if (force) {
      setCycleAnalysis(null);
      setIntradayAnalysis(null);
    }
    try {
      let res = null;
      try {
        res = await apiRequest('/api/v1/emotion-cycle-refresh', {
          method: 'POST',
          body: JSON.stringify({ date: selectedDate, force }),
          timeout: 300000,
        });
      } catch (err) {
        if (err?.status !== 404) throw err;
        res = await apiRequest('/api/v1/emotion-intraday-refresh', {
          method: 'POST',
          body: JSON.stringify({ date: selectedDate, force }),
          timeout: 300000,
        });
      }
      if (res?.data?.cycle) setCycleAnalysis(res.data.cycle);
      if (res?.data?.daily || res?.data?.intraday) {
        setIntradayAnalysis(res.data.daily || res.data.intraday);
      }
      if (res?.data?.records) setRecords(res.data.records);

      if (!res?.data?.cycle) {
        const cycleRes = await apiRequest(`/api/v1/emotion-analysis-cache?date=${selectedDate}`);
        if (cycleRes?.data) setCycleAnalysis(cycleRes.data);
      }
    } catch (err) {
      console.error('Failed to refresh emotion cycle panels:', err);
    } finally {
      if (!silent) setPanelRefreshing(false);
    }
  }, [hasSelectedRecord, selectedDate]);

  useEffect(() => {
    if (preview) return;
    if (loading || !cacheChecked || !hasSelectedRecord || panelRefreshing) return;
    if (!localStorage.getItem('niuniu_token')) return;
    if (autoRefreshAttemptedRef.current.has(selectedDate)) return;
    if (cycleAnalysis && intradayAnalysis) return;

    autoRefreshAttemptedRef.current.add(selectedDate);
    handlePanelRefresh({ force: !cycleAnalysis || !intradayAnalysis, silent: false });
  }, [
    loading,
    cacheChecked,
    hasSelectedRecord,
    selectedDate,
    cycleAnalysis,
    intradayAnalysis,
    panelRefreshing,
    handlePanelRefresh,
    preview,
  ]);

  useEffect(() => {
    autoRefreshAttemptedRef.current.delete(selectedDate);
  }, [selectedDate]);

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
            const suffix = cfg && cfg.key === 'board_hit_rate' ? '%' : '';
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
      <MarketBriefBar />
      <div className="page-date-nav">
        <button
          type="button"
          className="date-nav-btn"
          onClick={() => setSelectedDate(offsetDate(selectedDate, -1))}
          disabled={selectedDate <= minDate}
        >
          <LeftOutlined /> 前一天
        </button>
        <div className="page-date-nav-end">
          <button
            type="button"
            className="date-nav-btn"
            onClick={() => setSelectedDate(offsetDate(selectedDate, 1))}
            disabled={selectedDate >= navMaxDate}
          >
            后一天 <RightOutlined />
          </button>
          <span className="date-nav-label">{formatDateDisplay(selectedDate)}</span>
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
              style={{ height: '100%', minHeight: 300 }}
              notMerge
              lazyUpdate
              theme="dark"
            />
          )}
        </div>

        <div className="emotion-right-column">
          {SHOW_PANEL_REFRESH_BTN && !preview && hasSelectedRecord && (
            <div className="emotion-panel-actions">
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => handlePanelRefresh({ force: true })}
                loading={panelRefreshing}
                disabled={records.length === 0 || !localStorage.getItem('niuniu_token')}
                className="ai-refresh-btn"
              >
                生成/刷新分析
              </Button>
            </div>
          )}
          <AnalysisBlock
            title="周期研判"
            accent="cycle"
            result={cycleAnalysis}
            loading={panelRefreshing}
            emptyHint={
              panelRefreshing
                ? '分析生成中，请稍候…'
                : (localStorage.getItem('niuniu_token')
                  ? '暂无分析，点击上方「生成/刷新分析」'
                  : '请登录后查看，或由每日定时任务生成')
            }
          />
          <AnalysisBlock
            title="盘中买卖指导"
            accent="intraday"
            result={hasSelectedRecord ? intradayAnalysis : null}
            loading={panelRefreshing}
            emptyHint={
              !hasSelectedRecord
                ? '该日期暂无行情数据'
                : panelRefreshing
                  ? '分析生成中，请稍候…'
                  : (localStorage.getItem('niuniu_token')
                    ? '暂无分析，点击上方「生成/刷新分析」'
                    : '请登录后查看，或由定时任务生成（含买卖点与昨日复盘）')
            }
          />
        </div>
      </div>
    </div>
  );
}

export default EmotionCycle;
