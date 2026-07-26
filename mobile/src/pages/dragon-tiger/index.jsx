import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../config/api'
import { ensureAuth } from '../../services/auth'
import './index.scss'

const MIN_DATE = '20260511'

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

const clampDate = (dateStr) => {
  if (!dateStr || dateStr.length !== 8) return dateStr
  if (dateStr < MIN_DATE) return MIN_DATE
  const today = getLastTradingDayStr()
  return dateStr > today ? today : dateStr
}

const formatDateDisplay = (s) =>
  s && s.length === 8 ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s

const fmtAmount = (val) => {
  const v = parseFloat(val || 0)
  if (isNaN(v)) return '--'
  const abs = Math.abs(v)
  if (abs >= 1e8) return `${(v / 1e8).toFixed(2)}亿`
  if (abs >= 1e4) return `${(v / 1e4).toFixed(0)}万`
  return `${v.toFixed(0)}`
}

const HOT_MONEY_KW = ['知春路', '成都', '宁波', '佛山', '拉萨', '乐清千帆', '温州', '绍兴', '华鑫', '财通', '游资']
const isHotMoney = (name) => HOT_MONEY_KW.some((kw) => name && name.includes(kw))

function SeatTable({ seats }) {
  if (!seats || seats.length === 0) {
    return <Text className='dt-seat-empty'>暂无数据</Text>
  }
  return (
    <View>
      <View className='dt-seat-row dt-seat-head'>
        <Text className='dt-seat-name'>席位名称</Text>
        <Text className='dt-seat-col'>买入</Text>
        <Text className='dt-seat-col'>卖出</Text>
        <Text className='dt-seat-col'>净额</Text>
      </View>
      {seats.map((seat, i) => {
        const hot = seat.is_hot_money || isHotMoney(seat.seat_name || '')
        const net = parseFloat(seat.net_amount || 0)
        return (
          <View className='dt-seat-row' key={i}>
            <Text className={`dt-seat-name ${hot ? 'hot' : ''}`}>{seat.seat_name || '--'}</Text>
            <Text className='dt-seat-col' style={{ color: 'var(--up)' }}>{fmtAmount(seat.buy_amount)}</Text>
            <Text className='dt-seat-col' style={{ color: 'var(--down)' }}>{fmtAmount(seat.sell_amount)}</Text>
            <Text className='dt-seat-col' style={{ color: net > 0 ? 'var(--up)' : net < 0 ? 'var(--down)' : 'var(--text-muted)' }}>
              {fmtAmount(seat.net_amount)}
            </Text>
          </View>
        )
      })}
    </View>
  )
}

export default function DragonTiger() {
  const todayStr = useMemo(() => getLastTradingDayStr(), [])
  const [currentDate, setCurrentDate] = useState(() => clampDate(getLastTradingDayStr()))
  const [loading, setLoading] = useState(false)
  const [stocks, setStocks] = useState([])
  const [selectedCode, setSelectedCode] = useState(null)
  const [aiResults, setAiResults] = useState({})
  const [aiLoading, setAiLoading] = useState({})
  const dataCache = useRef({})

  useDidShow(() => { ensureAuth() })

  const fetchData = useCallback(async (date) => {
    if (dataCache.current[date]) {
      const cached = dataCache.current[date]
      setStocks(cached)
      setSelectedCode(cached.length ? cached[0].code : null)
      return
    }
    setLoading(true)
    setStocks([])
    setSelectedCode(null)
    try {
      const res = await api.get(`/api/v1/dragon-tiger?date=${date}`, { timeout: 60000 })
      if (res?.data?.stocks) {
        dataCache.current[date] = res.data.stocks
        setStocks(res.data.stocks)
        if (res.data.stocks.length) setSelectedCode(res.data.stocks[0].code)
      }
    } catch (e) {
      setStocks([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData(currentDate) }, [currentDate, fetchData])

  const handleDateChange = (delta) => {
    const next = clampDate(offsetDate(currentDate, delta > 0 ? 1 : -1))
    if (next === currentDate) return
    setCurrentDate(next)
    setAiResults({})
  }

  const handleAi = async (code) => {
    if (aiLoading[code]) return
    setAiLoading((p) => ({ ...p, [code]: true }))
    try {
      const res = await api.get(`/api/v1/dragon-tiger/ai-analysis-cache?date=${currentDate}&code=${code}`, { timeout: 60000 })
      if (res?.data?.analysis) {
        setAiResults((p) => ({ ...p, [code]: res.data.analysis }))
      } else {
        const hint = res?.message || '还未生成，由每日定时任务生成'
        Taro.showToast({ title: hint, icon: 'none' })
      }
    } catch (e) {
      Taro.showToast({ title: '加载 AI 解读失败', icon: 'none' })
    } finally {
      setAiLoading((p) => ({ ...p, [code]: false }))
    }
  }

  const selectedStock = stocks.find((s) => s.code === selectedCode) || null

  return (
    <View className='dt-page'>
      <View className='dt-date-nav'>
        <Text
          className={`dt-nav-btn ${currentDate <= MIN_DATE ? 'disabled' : ''}`}
          onClick={() => { if (currentDate > MIN_DATE) handleDateChange(-1) }}
        >{'< 前一天'}</Text>
        <Text className='dt-nav-label'>{formatDateDisplay(currentDate)}</Text>
        <Text
          className={`dt-nav-btn ${currentDate >= todayStr ? 'disabled' : ''}`}
          onClick={() => { if (currentDate < todayStr) handleDateChange(1) }}
        >{'后一天 >'}</Text>
      </View>

      <ScrollView scrollX className='dt-stock-strip'>
        {loading ? (
          <Text className='dt-loading'>加载中…</Text>
        ) : stocks.length === 0 ? (
          <Text className='dt-empty'>暂无龙虎榜数据</Text>
        ) : (
          stocks.map((stock) => {
            const pct = parseFloat(stock.change_pct || 0)
            return (
              <View
                className={`dt-chip ${selectedCode === stock.code ? 'on' : ''}`}
                key={stock.code}
                onClick={() => setSelectedCode(stock.code)}
              >
                <Text className='dt-chip-name'>{stock.name}</Text>
                <Text className='dt-chip-pct' style={{ color: pct > 0 ? 'var(--up)' : pct < 0 ? 'var(--down)' : 'var(--text-muted)' }}>
                  {pct > 0 ? '+' : ''}{pct.toFixed(2)}%
                </Text>
              </View>
            )
          })
        )}
      </ScrollView>

      {selectedStock && (
        <View className='dt-detail'>
          <View className='dt-detail-head'>
            <View className='dt-detail-title'>
              <Text className='dt-detail-name'>{selectedStock.name}</Text>
              <Text className='dt-detail-code'>{selectedStock.code}</Text>
            </View>
            <Text
              className='dt-detail-net'
              style={{ color: parseFloat(selectedStock.net_buy) > 0 ? 'var(--up)' : 'var(--down)' }}
            >
              净额 {fmtAmount(selectedStock.net_buy)}
            </Text>
          </View>
          <Text className='dt-detail-reason'>上榜原因：{selectedStock.reason || '--'}</Text>

          <View className='dt-detail-actions'>
            <Text
              className='dt-action-btn'
              onClick={() => Taro.navigateTo({ url: `/pages/stock-dashboard/index?code=${selectedStock.code}` })}
            >查看分时</Text>
            <Text
              className='dt-action-btn ai'
              onClick={() => handleAi(selectedStock.code)}
            >{aiLoading[selectedStock.code] ? '加载中…' : 'AI分析'}</Text>
          </View>

          {aiResults[selectedStock.code] && (
            <View className='dt-ai'>
              <Text className='dt-ai-title'>AI 资金意图解读</Text>
              <Text className='dt-ai-text'>{aiResults[selectedStock.code]}</Text>
            </View>
          )}

          <View className='dt-seats'>
            <View className='dt-seats-panel'>
              <Text className='dt-seats-title buy'>买入席位</Text>
              <SeatTable seats={selectedStock.buy_seats} />
            </View>
            <View className='dt-seats-panel'>
              <Text className='dt-seats-title sell'>卖出席位</Text>
              <SeatTable seats={selectedStock.sell_seats} />
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
