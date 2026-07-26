import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../config/api'
import { ensureAuth } from '../../services/auth'
import './index.scss'

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

const getChangeColor = (val) => {
  const num = parseFloat(val)
  if (num > 0) return 'var(--up)'
  if (num < 0) return 'var(--down)'
  return '#999'
}

const formatAmount = (val) => {
  const num = parseFloat(val)
  if (isNaN(num)) return '--'
  if (num >= 10000) return `${(num / 10000).toFixed(2)}亿`
  return `${num.toFixed(2)}万`
}

const formatPct = (val) => {
  const num = parseFloat(val)
  if (isNaN(num)) return '--'
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

export default function AuctionGrab() {
  const todayStr = useMemo(() => getLastTradingDayStr(), [])
  const [currentDate, setCurrentDate] = useState(getLastTradingDayStr)
  const [activeTab, setActiveTab] = useState('morning')
  const [hint, setHint] = useState({ stage: '', text: '' })
  const [screenData, setScreenData] = useState(null)
  const [screenLoading, setScreenLoading] = useState(false)
  const [analyzeData, setAnalyzeData] = useState(null)
  const [analyzeLoading, setAnalyzeLoading] = useState(false)
  const [backtestData, setBacktestData] = useState(null)
  const [backtestLoading, setBacktestLoading] = useState(false)
  const screenCache = useRef({})
  const analyzeCache = useRef({})
  const backtestCache = useRef({})
  const hintCache = useRef({})

  useDidShow(() => {
    ensureAuth()
  })

  const isTodayView = currentDate === todayStr

  const fetchHint = useCallback(async (dt, tab) => {
    const period = tab === 'tail' ? '1' : '0'
    const cacheKey = `${dt}_${period}`
    if (hintCache.current[cacheKey]) {
      setHint(hintCache.current[cacheKey])
      return
    }
    try {
      const res = await api.get(`/api/v1/auction-grab?dt=${dt}&period=${period}`, { timeout: 120000 })
      if (res?.data) {
        const h = { stage: res.data.emotion_stage || '', text: res.data.recommend_hint || '' }
        hintCache.current[cacheKey] = h
        setHint(h)
      }
    } catch (e) {
      setHint({ stage: '', text: '' })
    }
  }, [])

  const fetchScreenData = useCallback(async (dt, tab) => {
    const period = tab === 'tail' ? '1' : '0'
    const cacheKey = `${dt}_${period}`
    if (screenCache.current[cacheKey]) {
      setScreenData(screenCache.current[cacheKey])
      return
    }
    setScreenLoading(true)
    try {
      const res = await api.get(`/api/v1/auction-grab/screen?dt=${dt}&period=${period}`, { timeout: 120000 })
      if (res?.data) {
        screenCache.current[cacheKey] = res.data
        setScreenData(res.data)
      }
    } catch (err) {
      setScreenData(null)
    } finally {
      setScreenLoading(false)
    }
  }, [])

  const fetchAnalyzeData = useCallback(async (dt, tab) => {
    const period = tab === 'tail' ? '1' : '0'
    const cacheKey = `analyze_${dt}_${period}`
    if (analyzeCache.current[cacheKey]) {
      setAnalyzeData(analyzeCache.current[cacheKey])
      return
    }
    setAnalyzeLoading(true)
    try {
      const res = await api.get(`/api/v1/auction-grab/screen/analyze?dt=${dt}&period=${period}`, { timeout: 120000 })
      if (res?.data) {
        analyzeCache.current[cacheKey] = res.data
        setAnalyzeData(res.data)
      }
    } catch (err) {
      /* 静默 */
    } finally {
      setAnalyzeLoading(false)
    }
  }, [])

  const fetchBacktestData = useCallback(async (tab) => {
    const period = tab === 'tail' ? '1' : '0'
    const cacheKey = `backtest_${period}`
    if (backtestCache.current[cacheKey]) {
      setBacktestData(backtestCache.current[cacheKey])
      return
    }
    setBacktestLoading(true)
    setBacktestData(null)
    try {
      const res = await api.get(`/api/v1/auction-grab/screen/backtest?days=10&period=${period}`, { timeout: 300000 })
      if (res?.data) {
        backtestCache.current[cacheKey] = res.data
        setBacktestData(res.data)
      }
    } catch (err) {
      Taro.showToast({ title: '回测失败', icon: 'none' })
    } finally {
      setBacktestLoading(false)
    }
  }, [])

  useEffect(() => {
    setAnalyzeData(null)
    fetchHint(currentDate, activeTab)
    fetchScreenData(currentDate, activeTab)
  }, [fetchHint, fetchScreenData, currentDate, activeTab])

  useEffect(() => {
    if (screenData?.items?.length > 0 && !analyzeLoading) {
      fetchAnalyzeData(currentDate, activeTab)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screenData?.items?.length, currentDate, activeTab])

  const items = screenData?.items || []
  const limitUpByIndustry = screenData?.limit_up_by_industry || {}
  const marketSentiment = screenData?.market_sentiment || null

  const displayTodayChange = (item) => {
    if (isTodayView && item.today_change_pct != null) return item.today_change_pct
    return item.close_change_pct
  }

  return (
    <View className='ag-page'>
      <View className='ag-top'>
        <View className='date-nav'>
          <View className='date-nav-btn' onClick={() => setCurrentDate(offsetDate(currentDate, -1))}>
            {'< 前一天'}
          </View>
          <Text className='date-nav-label'>{formatDateDisplay(currentDate)}</Text>
          <View
            className={`date-nav-btn ${currentDate >= todayStr ? 'disabled' : ''}`}
            onClick={() => { if (currentDate < todayStr) setCurrentDate(offsetDate(currentDate, 1)) }}
          >
            {'后一天 >'}
          </View>
        </View>

        <View className='period-toggle'>
          <Text
            className={`period-btn ${activeTab === 'morning' ? 'active' : ''}`}
            onClick={() => setActiveTab('morning')}
          >
            早盘
          </Text>
          <Text
            className={`period-btn ${activeTab === 'tail' ? 'active' : ''}`}
            onClick={() => setActiveTab('tail')}
          >
            尾盘
          </Text>
        </View>
      </View>

      {(hint.stage || hint.text) && (
        <View className='ag-hint'>
          {hint.stage ? <Text className='ag-hint-stage'>情绪周期：{hint.stage}</Text> : null}
          {hint.text ? <Text className='ag-hint-text'>{hint.text}</Text> : null}
        </View>
      )}

      {marketSentiment && marketSentiment.risk_level !== 'unknown' && (
        <View className={`ag-market ag-market-${marketSentiment.risk_level}`}>
          <Text className='ag-market-label'>大盘指数</Text>
          {marketSentiment.indexes?.map((idx) => (
            <Text className='ag-market-index' key={idx.code} style={{ color: getChangeColor(idx.change_pct) }}>
              {idx.name} {idx.change_pct > 0 ? '+' : ''}{idx.change_pct.toFixed(2)}%
            </Text>
          ))}
          {marketSentiment.hint ? <Text className='ag-market-hint'>{marketSentiment.hint}</Text> : null}
        </View>
      )}

      {screenLoading ? (
        <View className='ag-loading'>筛选中，约需 15-30 秒…</View>
      ) : items.length === 0 ? (
        <View className='ag-empty'>无符合条件的股票</View>
      ) : (
        items.map((item) => {
          const volRatio = item.vol_ratio
          const volRatioStr = volRatio != null ? `${(volRatio * 100).toFixed(1)}%` : '--'
          return (
            <View className='ag-card' key={item.code}>
              <View className='ag-card-head'>
                <View className='ag-name-box'>
                  <Text className='ag-name'>{item.name}</Text>
                  <Text className='ag-code'>{item.code}</Text>
                </View>
                <Text className='ag-mktcap'>
                  {item.mktcap != null ? `${item.mktcap.toFixed(0)}亿` : '--'}
                  {item.limit_up_cnt != null ? ` · 年涨停${item.limit_up_cnt}` : ''}
                </Text>
              </View>

              {(item.industry || item.concepts) && (
                <View className='ag-tags'>
                  {item.industry ? (
                    <Text className='ag-tag industry'>
                      {item.industry}{limitUpByIndustry[item.industry] ? `(${limitUpByIndustry[item.industry]})` : ''}
                    </Text>
                  ) : null}
                  {item.concepts ? <Text className='ag-tag concept'>{item.concepts}</Text> : null}
                </View>
              )}

              <View className='ag-metrics'>
                <View className='ag-metric'>
                  <Text className='ag-m-label'>竞价涨幅</Text>
                  <Text className='ag-m-value' style={{ color: getChangeColor(item.auction_change_pct) }}>
                    {formatPct(item.auction_change_pct)}
                  </Text>
                </View>
                <View className='ag-metric'>
                  <Text className='ag-m-label'>竞价量比</Text>
                  <Text className='ag-m-value' style={{ color: volRatio != null && volRatio >= 0.03 ? 'var(--up)' : 'var(--text-muted)' }}>
                    {volRatioStr}
                  </Text>
                </View>
                <View className='ag-metric'>
                  <Text className='ag-m-label'>{isTodayView ? '今日涨幅' : '收盘涨幅'}</Text>
                  <Text className='ag-m-value' style={{ color: getChangeColor(displayTodayChange(item)) }}>
                    {formatPct(displayTodayChange(item))}
                  </Text>
                </View>
                <View className='ag-metric'>
                  <Text className='ag-m-label'>上一日</Text>
                  <Text className='ag-m-value' style={{ color: getChangeColor(item.prev_day_change_pct) }}>
                    {formatPct(item.prev_day_change_pct)}
                  </Text>
                </View>
                <View className='ag-metric'>
                  <Text className='ag-m-label'>后一日</Text>
                  <Text className='ag-m-value' style={{ color: getChangeColor(item.next_day_change_pct) }}>
                    {formatPct(item.next_day_change_pct)}
                  </Text>
                </View>
                <View className='ag-metric'>
                  <Text className='ag-m-label'>竞价到收盘</Text>
                  <Text className='ag-m-value' style={{ color: getChangeColor(item.auction_to_close_pct) }}>
                    {formatPct(item.auction_to_close_pct)}
                  </Text>
                </View>
                <View className='ag-metric'>
                  <Text className='ag-m-label'>成交额</Text>
                  <Text className='ag-m-value'>{formatAmount(item.auction_trade_amt)}</Text>
                </View>
                <View className='ag-metric'>
                  <Text className='ag-m-label'>委托金额</Text>
                  <Text className='ag-m-value'>{formatAmount(item.auction_order_amt)}</Text>
                </View>
              </View>
            </View>
          )
        })
      )}

      {(analyzeLoading || analyzeData) && (
        <View className='ag-analyze'>
          {analyzeLoading && !analyzeData && <Text className='ag-analyze-loading'>AI 复盘分析中…</Text>}
          {analyzeData?.pnl_summary && (
            <View className='ag-pnl'>
              <Text className='ag-pnl-title'>今日等权收益复盘</Text>
              <Text className='ag-pnl-avg' style={{ color: getChangeColor(analyzeData.pnl_summary.avg_pct) }}>
                平均 {analyzeData.pnl_summary.avg_pct > 0 ? '+' : ''}{analyzeData.pnl_summary.avg_pct}%
              </Text>
              <Text className='ag-pnl-stat'>
                胜率 {analyzeData.pnl_summary.win_rate}%（{analyzeData.pnl_summary.win_count} 盈 / {analyzeData.pnl_summary.loss_count} 亏）
              </Text>
              <Text className='ag-pnl-range'>
                最好 <Text style={{ color: 'var(--up)' }}>{analyzeData.pnl_summary.best > 0 ? '+' : ''}{analyzeData.pnl_summary.best}%</Text>
                {' / 最差 '}<Text style={{ color: 'var(--down)' }}>{analyzeData.pnl_summary.worst}%</Text>
              </Text>
            </View>
          )}
        </View>
      )}

      <View className='ag-backtest'>
        <View
          className={`ag-bt-btn ${backtestLoading ? 'active' : ''}`}
          onClick={() => { if (!backtestLoading) fetchBacktestData(activeTab) }}
        >
          {backtestLoading ? '回测计算中（约1分钟）…' : '参数回测（近10日）'}
        </View>

        {backtestData?.results?.length > 0 && (
          <View className='ag-bt-wrap'>
            <Text className='ag-bt-header'>
              参数组合回测（近 {backtestData.trade_dates?.length || 10} 个交易日，等权竞价→收盘）
            </Text>
            <View className='ag-bt-row ag-bt-head'>
              <Text className='ag-bt-col name'>参数组合</Text>
              <Text className='ag-bt-col'>天数</Text>
              <Text className='ag-bt-col'>日均</Text>
              <Text className='ag-bt-col'>胜率</Text>
            </View>
            {backtestData.results.map((row, idx) => {
              const isBest = idx === 0
              return (
                <View className={`ag-bt-row ${isBest ? 'best' : ''}`} key={row.params.name}>
                  <Text className='ag-bt-col name'>
                    {isBest ? '★ ' : ''}{row.params.name}
                  </Text>
                  <Text className='ag-bt-col'>{row.days}天</Text>
                  <Text className='ag-bt-col' style={{ color: getChangeColor(row.avg_pct) }}>
                    {row.avg_pct > 0 ? '+' : ''}{row.avg_pct}%
                  </Text>
                  <Text className='ag-bt-col'>{row.win_rate}%</Text>
                </View>
              )
            })}
          </View>
        )}
      </View>
    </View>
  )
}
