import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { api, getToken } from '../../config/api'
import { ensureAuth } from '../../services/auth'
import MarketBriefBar from '../../components/MarketBriefBar'
import EmotionChart from './EmotionChart'
import './index.scss'

const stageColorMap = {
  '冰点期': '#1677ff', '冰点': '#1677ff',
  '修复期': '#13c2c2', '修复': '#13c2c2',
  '升温期': '#fa8c16', '升温': '#fa8c16',
  '高潮期': '#f5222d', '高潮': '#f5222d',
  '退潮期': '#52c41a', '退潮': '#52c41a',
}

const getStageColor = (stage) =>
  stageColorMap[stage] ||
  Object.entries(stageColorMap).find(([k]) => stage?.includes(k))?.[1] ||
  '#1890ff'

const metricCols = [
  { key: 'rise_ratio', name: '上涨比例' },
  { key: 'consec_limit', name: '连板' },
  { key: 'limit_up_count', name: '涨停' },
  { key: 'limit_down_count', name: '跌停' },
  { key: 'latest_height', name: '最高' },
  { key: 'board_hit_rate', name: '打板%', pct: true },
]

const getLastTradingDayStr = () => {
  const d = new Date()
  const dow = d.getDay()
  if (dow === 6) d.setDate(d.getDate() - 1)
  if (dow === 0) d.setDate(d.getDate() - 2)
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
}

const offsetDate = (dateStr, delta) => {
  const d = new Date(
    parseInt(dateStr.slice(0, 4), 10),
    parseInt(dateStr.slice(4, 6), 10) - 1,
    parseInt(dateStr.slice(6, 8), 10)
  )
  let count = 0
  const step = delta > 0 ? 1 : -1
  while (count !== delta) {
    d.setDate(d.getDate() + step)
    const dow = d.getDay()
    if (dow !== 0 && dow !== 6) count += step
  }
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
}

const formatDateDisplay = (dateStr) => {
  if (!dateStr || dateStr.length !== 8) return dateStr
  return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`
}

const getLatestRecordDate = (items) => {
  if (!items || items.length === 0) return null
  const sortedDates = items.map((item) => item.date?.replace(/-/g, '')).filter(Boolean).sort()
  return sortedDates[sortedDates.length - 1] || null
}

function AnalysisBlock({ title, result, loading, emptyHint }) {
  if (loading && !result) {
    return (
      <View className='analysis-block'>
        <Text className='analysis-title'>{title}</Text>
        <Text className='analysis-empty'>加载中…</Text>
      </View>
    )
  }
  if (!result) {
    return (
      <View className='analysis-block'>
        <Text className='analysis-title'>{title}</Text>
        <Text className='analysis-empty'>{emptyHint}</Text>
      </View>
    )
  }
  const {
    stage, analysis,
    prev_day_review: prevDayReview,
    updated_at: updatedAt,
  } = result
  return (
    <View className='analysis-block'>
      <View className='analysis-head'>
        <Text className='analysis-title'>{title}</Text>
        {updatedAt && <Text className='analysis-updated'>更新 {String(updatedAt).slice(0, 16)}</Text>}
      </View>
      {stage && (
        <Text className='stage-tag' style={{ background: getStageColor(stage) }}>{stage}</Text>
      )}
      {analysis && (
        <View className='analysis-section'>
          <Text className='section-title'>分析</Text>
          <Text className='section-text'>{analysis}</Text>
        </View>
      )}
      {prevDayReview && (
        <View className='analysis-section'>
          <Text className='section-title'>昨日复盘修正</Text>
          <Text className='section-text'>{prevDayReview}</Text>
        </View>
      )}
    </View>
  )
}

export default function EmotionCycle() {
  const todayStr = useMemo(() => getLastTradingDayStr(), [])
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [panelRefreshing, setPanelRefreshing] = useState(false)
  const [cacheChecked, setCacheChecked] = useState(false)
  const [cycleAnalysis, setCycleAnalysis] = useState(null)
  const [selectedDate, setSelectedDate] = useState(() => getLastTradingDayStr())
  const autoRefreshAttemptedRef = useRef(new Set())

  useDidShow(() => {
    ensureAuth()
  })

  const minDate = records.length > 0 ? records[0].date.replace(/-/g, '') : '20000101'
  const latestDate = getLatestRecordDate(records)
  const navMaxDate = latestDate && latestDate < todayStr ? latestDate : todayStr
  const hasSelectedRecord = records.some((r) => r.date?.replace(/-/g, '') === selectedDate)

  useEffect(() => {
    if (!latestDate) return
    const hasCurrent = records.some((r) => r.date?.replace(/-/g, '') === selectedDate)
    if (!hasCurrent) setSelectedDate(latestDate)
  }, [records, latestDate, selectedDate])

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get('/api/v1/emotion-cycle')
      if (res?.data?.records) setRecords(res.data.records)
    } catch (err) {
      /* 静默 */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    const loadCaches = async () => {
      setCacheChecked(false)
      setCycleAnalysis(null)
      if (records.length === 0) {
        setCacheChecked(true)
        return
      }
      try {
        const cycleRes = await api.get(`/api/v1/emotion-analysis-cache?date=${selectedDate}`)
        if (cycleRes?.data) setCycleAnalysis(cycleRes.data)
      } catch (e) {
        /* ignore */
      } finally {
        setCacheChecked(true)
      }
    }
    loadCaches()
  }, [selectedDate, records.length, hasSelectedRecord])

  const handlePanelRefresh = useCallback(async (options = {}) => {
    const { force = true, silent = false } = options
    if (!hasSelectedRecord) return
    if (!getToken()) return

    if (!silent) setPanelRefreshing(true)
    if (force) {
      setCycleAnalysis(null)
    }
    try {
      let res = null
      try {
        res = await api.post('/api/v1/emotion-cycle-refresh', { date: selectedDate, force }, { timeout: 300000 })
      } catch (err) {
        if (err?.status !== 404) throw err
        res = await api.post('/api/v1/emotion-intraday-refresh', { date: selectedDate, force }, { timeout: 300000 })
      }
      if (res?.data?.cycle) setCycleAnalysis(res.data.cycle)
      if (res?.data?.records) setRecords(res.data.records)
      if (!res?.data?.cycle) {
        const cycleRes = await api.get(`/api/v1/emotion-analysis-cache?date=${selectedDate}`)
        if (cycleRes?.data) setCycleAnalysis(cycleRes.data)
      }
    } catch (err) {
      Taro.showToast({ title: '刷新失败', icon: 'none' })
    } finally {
      if (!silent) setPanelRefreshing(false)
    }
  }, [hasSelectedRecord, selectedDate])

  useEffect(() => {
    if (loading || !cacheChecked || !hasSelectedRecord || panelRefreshing) return
    if (!getToken()) return
    if (autoRefreshAttemptedRef.current.has(selectedDate)) return
    if (cycleAnalysis) return
    autoRefreshAttemptedRef.current.add(selectedDate)
    handlePanelRefresh({ force: !cycleAnalysis, silent: false })
  }, [loading, cacheChecked, hasSelectedRecord, selectedDate, cycleAnalysis, panelRefreshing, handlePanelRefresh])

  useEffect(() => {
    autoRefreshAttemptedRef.current.delete(selectedDate)
  }, [selectedDate])

  const recentRecords = useMemo(() => {
    const filtered = records.filter((r) => r.date.replace(/-/g, '') <= selectedDate)
    return filtered.slice(-8).reverse()
  }, [records, selectedDate])

  const chartRecords = useMemo(() => {
    const filtered = records.filter((r) => r.date.replace(/-/g, '') <= selectedDate)
    return filtered.slice(-20)
  }, [records, selectedDate])

  const fmtMetric = (val, pct) => {
    if (val == null || val === '') return '--'
    return pct ? `${val}%` : val
  }

  return (
    <View className='emotion-page'>
      <MarketBriefBar />

      <View className='date-nav'>
        <View
          className={`date-nav-btn ${selectedDate <= minDate ? 'disabled' : ''}`}
          onClick={() => { if (selectedDate > minDate) setSelectedDate(offsetDate(selectedDate, -1)) }}
        >
          {'< 前一天'}
        </View>
        <Text className='date-nav-label'>{formatDateDisplay(selectedDate)}</Text>
        <View
          className={`date-nav-btn ${selectedDate >= navMaxDate ? 'disabled' : ''}`}
          onClick={() => { if (selectedDate < navMaxDate) setSelectedDate(offsetDate(selectedDate, 1)) }}
        >
          {'后一天 >'}
        </View>
      </View>

      <View className='metrics-card'>
        <Text className='card-title'>情绪趋势</Text>
        {loading ? (
          <Text className='metrics-empty'>加载中…</Text>
        ) : chartRecords.length === 0 ? (
          <Text className='metrics-empty'>暂无数据</Text>
        ) : (
          <EmotionChart records={chartRecords} />
        )}
      </View>

      <View className='metrics-card'>
        <Text className='card-title'>近期情绪指标</Text>
        {loading ? (
          <Text className='metrics-empty'>加载中…</Text>
        ) : recentRecords.length === 0 ? (
          <Text className='metrics-empty'>暂无数据</Text>
        ) : (
          <ScrollView scrollX className='metrics-scroll'>
            <View className='metrics-table'>
              <View className='metrics-tr metrics-th'>
                <Text className='metrics-td date-col'>日期</Text>
                {metricCols.map((c) => (
                  <Text className='metrics-td' key={c.key}>{c.name}</Text>
                ))}
              </View>
              {recentRecords.map((r) => (
                <View className='metrics-tr' key={r.date}>
                  <Text className='metrics-td date-col'>{r.date.slice(5)}</Text>
                  {metricCols.map((c) => (
                    <Text className='metrics-td' key={c.key}>{fmtMetric(r[c.key], c.pct)}</Text>
                  ))}
                </View>
              ))}
            </View>
          </ScrollView>
        )}
      </View>

      {hasSelectedRecord && getToken() && (
        <View
          className={`refresh-btn ${panelRefreshing ? 'loading' : ''}`}
          onClick={() => { if (!panelRefreshing) handlePanelRefresh({ force: true }) }}
        >
          {panelRefreshing ? '分析生成中…' : '生成/刷新分析'}
        </View>
      )}

      <AnalysisBlock
        title='周期研判'
        result={cycleAnalysis}
        loading={panelRefreshing}
        emptyHint={panelRefreshing ? '分析生成中，请稍候…' : (getToken() ? '暂无分析，点击上方「生成/刷新分析」' : '请登录后查看，或由每日定时任务生成')}
      />
    </View>
  )
}
