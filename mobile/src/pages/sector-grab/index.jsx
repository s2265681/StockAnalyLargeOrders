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

const formatDateDisplay = (s) =>
  s && s.length === 8 ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s

const BOARD_TABS = [
  { key: 'main', label: '主板' },
  { key: 'gem', label: '创业板' },
  { key: 'bond', label: '可转债' },
]

const isMaskedCode = (code) => String(code || '').includes('*')

const limitMaskedStocks = (stocks, limit = 8) => {
  if (!stocks?.length || !stocks.some((s) => isMaskedCode(s.code))) return stocks
  return [...stocks]
    .sort((a, b) => (parseFloat(b.change_pct) || 0) - (parseFloat(a.change_pct) || 0))
    .slice(0, limit)
}

const matchBoard = (code, board) => {
  const c = String(code || '').padStart(6, '0')
  if (board === 'gem') return c.startsWith('30')
  if (board === 'bond') return c.startsWith('11') || c.startsWith('12')
  return (c.startsWith('00') || c.startsWith('60')) && !c.startsWith('30') && !c.startsWith('68')
}

const fmtPct = (val) => {
  const num = parseFloat(val)
  if (!Number.isFinite(num)) return '--'
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const fmtTurnover = (val) => {
  const num = parseFloat(val)
  if (!Number.isFinite(num)) return '--'
  return `${num.toFixed(2)}%`
}

const fmtSpeed = (val) => {
  const num = parseFloat(val)
  if (!Number.isFinite(num)) return '--'
  const abs = Math.abs(num)
  if (abs >= 1e8) return `${(num / 1e8).toFixed(2)}亿`
  if (abs >= 1e4) return `${(num / 1e4).toFixed(0)}万`
  return num.toFixed(0)
}

const pctColor = (val) => {
  const n = parseFloat(val)
  return n > 0 ? 'var(--up)' : n < 0 ? 'var(--down)' : 'var(--text-muted)'
}

export default function SectorGrab() {
  const todayStr = useMemo(() => getLastTradingDayStr(), [])
  const [currentDate, setCurrentDate] = useState(getLastTradingDayStr)
  const [sectors, setSectors] = useState([])
  const [sectorsLoading, setSectorsLoading] = useState(true)
  const [selectedSector, setSelectedSector] = useState(null)
  const [stocks, setStocks] = useState([])
  const [stocksMeta, setStocksMeta] = useState({ maskedLimited: false, totalRaw: 0 })
  const [stocksLoading, setStocksLoading] = useState(false)
  const [activeBoard, setActiveBoard] = useState('main')
  const [refreshInterval, setRefreshInterval] = useState(null)
  const sectorsCache = useRef({})
  const stocksCache = useRef({})
  const fetchIdRef = useRef(0)
  const pollTimerRef = useRef(null)

  const isTodayView = currentDate === todayStr

  useDidShow(() => { ensureAuth() })

  const fetchSectors = useCallback(async (dt, { silent = false } = {}) => {
    const fetchId = ++fetchIdRef.current
    if (!silent) setSectorsLoading(true)
    try {
      const res = await api.get(`/api/v1/sector-grab/sectors?dt=${dt}`, { timeout: 60000 })
      if (fetchId !== fetchIdRef.current) return
      const payload = res?.data
      if (payload?.sectors) {
        sectorsCache.current[dt] = payload
        setSectors(payload.sectors)
        setRefreshInterval(payload.refresh_interval_sec || null)
        setSelectedSector((prev) => {
          if (prev) {
            const still = payload.sectors.find((s) => s.gn_code === prev.gn_code)
            return still || payload.sectors[0] || null
          }
          return payload.sectors[0] || null
        })
      }
    } catch (e) {
      /* ignore */
    } finally {
      if (fetchId === fetchIdRef.current && !silent) setSectorsLoading(false)
    }
  }, [])

  const fetchStocks = useCallback(async (dt, gnCode, { silent = false } = {}) => {
    if (!gnCode) return
    const cacheKey = `${dt}_${gnCode}`
    const fetchId = ++fetchIdRef.current
    if (!silent) setStocksLoading(true)
    try {
      const res = await api.get(`/api/v1/sector-grab/stocks?dt=${dt}&gnCode=${gnCode}`, { timeout: 60000 })
      if (fetchId !== fetchIdRef.current) return
      const payload = res?.data
      if (payload?.stocks) {
        const nextStocks = limitMaskedStocks(payload.stocks)
        stocksCache.current[cacheKey] = { ...payload, stocks: nextStocks }
        setStocks(nextStocks)
        setStocksMeta({
          maskedLimited: Boolean(payload.masked_limited) || nextStocks.length < (payload.stocks?.length || 0),
          totalRaw: payload.total_raw || payload.stocks?.length || nextStocks.length,
        })
      }
    } catch (e) {
      /* ignore */
    } finally {
      if (fetchId === fetchIdRef.current && !silent) setStocksLoading(false)
    }
  }, [])

  useEffect(() => {
    setSelectedSector(null)
    setStocks([])
    const cached = sectorsCache.current[currentDate]
    if (cached?.sectors && !isTodayView) {
      setSectors(cached.sectors)
      setSectorsLoading(false)
      if (cached.sectors.length) setSelectedSector(cached.sectors[0])
    } else {
      fetchSectors(currentDate)
    }
  }, [currentDate, fetchSectors, isTodayView])

  useEffect(() => {
    if (!selectedSector?.gn_code) return
    const cacheKey = `${currentDate}_${selectedSector.gn_code}`
    const cached = stocksCache.current[cacheKey]
    if (cached?.stocks && !isTodayView) {
      setStocks(cached.stocks)
      return
    }
    fetchStocks(currentDate, selectedSector.gn_code)
  }, [currentDate, selectedSector, fetchStocks, isTodayView])

  useEffect(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
    if (!isTodayView || !refreshInterval) return undefined
    pollTimerRef.current = setInterval(() => {
      fetchSectors(currentDate, { silent: true })
      if (selectedSector?.gn_code) fetchStocks(currentDate, selectedSector.gn_code, { silent: true })
    }, refreshInterval * 1000)
    return () => { if (pollTimerRef.current) clearInterval(pollTimerRef.current) }
  }, [isTodayView, refreshInterval, currentDate, selectedSector?.gn_code, fetchSectors, fetchStocks])

  const filteredStocks = useMemo(
    () => stocks.filter((s) => matchBoard(s.code, activeBoard)),
    [stocks, activeBoard]
  )

  const handleDateChange = (delta) => {
    const next = offsetDate(currentDate, delta)
    if (delta > 0 && next > todayStr) return
    setCurrentDate(next)
  }

  const handleSectorClick = (sector) => {
    setSelectedSector(sector)
    setActiveBoard('main')
  }

  return (
    <View className='sg-page'>
      <View className='sg-date-nav'>
        <Text className='sg-nav-btn' onClick={() => handleDateChange(-1)}>{'< 前一天'}</Text>
        <Text className='sg-nav-label'>{formatDateDisplay(currentDate)}</Text>
        <Text
          className={`sg-nav-btn ${currentDate >= todayStr ? 'disabled' : ''}`}
          onClick={() => { if (currentDate < todayStr) handleDateChange(1) }}
        >{'后一天 >'}</Text>
      </View>

      {isTodayView && refreshInterval ? (
        <Text className='sg-refresh-hint'>
          盘中自动刷新 · 每 {refreshInterval >= 60 ? `${refreshInterval / 60} 分钟` : `${refreshInterval} 秒`}
        </Text>
      ) : null}

      <ScrollView scrollX className='sg-sector-strip'>
        {sectorsLoading ? (
          <Text className='sg-loading'>加载中…</Text>
        ) : sectors.length === 0 ? (
          <Text className='sg-empty'>暂无板块数据</Text>
        ) : (
          sectors.map((sector) => (
            <View
              className={`sg-chip ${selectedSector?.gn_code === sector.gn_code ? 'on' : ''}`}
              key={sector.gn_code}
              onClick={() => handleSectorClick(sector)}
            >
              <Text className='sg-chip-name'>
                {sector.name}{sector.is_hot ? ' 🔥' : ''}
              </Text>
              <Text className='sg-chip-sub'>
                <Text style={{ color: pctColor(sector.change_pct) }}>{fmtPct(sector.change_pct)}</Text>
                <Text className='sg-chip-lu'>涨停{sector.limit_up_count || 0}</Text>
              </Text>
            </View>
          ))
        )}
      </ScrollView>

      <View className='sg-stocks'>
        <View className='sg-stocks-head'>
          <Text className='sg-stocks-title'>
            {selectedSector ? `${selectedSector.name} · 活跃个股` : '活跃个股'}
          </Text>
          <View className='sg-board-tabs'>
            {BOARD_TABS.map((tab) => (
              <Text
                key={tab.key}
                className={`sg-board-tab ${activeBoard === tab.key ? 'active' : ''}`}
                onClick={() => setActiveBoard(tab.key)}
              >{tab.label}</Text>
            ))}
          </View>
        </View>

        {stocksMeta.maskedLimited ? (
          <Text className='sg-masked-hint'>
            脱敏数据仅展示涨幅前 8 条{stocksMeta.totalRaw > 8 ? `（共 ${stocksMeta.totalRaw} 条）` : ''}
          </Text>
        ) : null}

        <View className='sg-stock-list'>
          <View className='sg-stock-row sg-stock-head'>
            <Text className='sg-col-name'>名称/代码</Text>
            <Text className='sg-col'>涨幅</Text>
            <Text className='sg-col'>换手</Text>
            <Text className='sg-col'>主力净流入</Text>
          </View>
          {!selectedSector ? (
            <Text className='sg-empty'>请选择上方板块</Text>
          ) : stocksLoading ? (
            <Text className='sg-loading'>加载中…</Text>
          ) : filteredStocks.length === 0 ? (
            <Text className='sg-empty'>该板块暂无个股</Text>
          ) : (
            filteredStocks.map((stock) => (
              <View
                className='sg-stock-row'
                key={stock.code}
                onClick={() => Taro.navigateTo({ url: `/pages/stock-dashboard/index?code=${stock.code}` })}
              >
                <View className='sg-col-name'>
                  <Text className='sg-stock-name'>
                    {stock.name}
                    {stock.board_label ? <Text className='sg-board-tag'>{stock.board_label}</Text> : null}
                  </Text>
                  <Text className='sg-stock-code'>{stock.code}</Text>
                </View>
                <Text className='sg-col' style={{ color: pctColor(stock.change_pct) }}>{fmtPct(stock.change_pct)}</Text>
                <Text className='sg-col'>{fmtTurnover(stock.turnover_pct)}</Text>
                <Text className='sg-col' style={{ color: parseFloat(stock.speed) >= 0 ? 'var(--up)' : 'var(--down)' }}>
                  {fmtSpeed(stock.speed)}
                </Text>
              </View>
            ))
          )}
        </View>
      </View>
    </View>
  )
}
