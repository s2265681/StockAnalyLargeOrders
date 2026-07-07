import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../config/api'
import { ensureAuth } from '../../services/auth'
import './index.scss'

const boardColorMap = {
  1: { tag: '#3b82f6', label: '首板' },
  2: { tag: '#10b981', label: '2板' },
  3: { tag: '#f59e0b', label: '3板' },
  4: { tag: '#f97316', label: '4板' },
  5: { tag: '#ef4444', label: '5板' },
  6: { tag: '#ec4899', label: '6板' },
  7: { tag: '#a855f7', label: '7板' },
}

const getBoardColor = (boards) => {
  if (boards >= 7) return boardColorMap[7]
  return boardColorMap[boards] || boardColorMap[1]
}

const formatTime = (t) => {
  if (!t || t.length < 6) return t || '--'
  return `${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4, 6)}`
}

const getSealQuality = (stock) => {
  const { seal_ratio, first_time, break_count } = stock
  let score = 0
  if (seal_ratio >= 10) score += 3
  else if (seal_ratio >= 3) score += 2
  else if (seal_ratio >= 1) score += 1
  const timeNum = parseInt(first_time || '150000', 10)
  if (timeNum <= 93000) score += 3
  else if (timeNum <= 103000) score += 2
  else if (timeNum <= 130000) score += 1
  if (break_count === 0) score += 2
  else if (break_count <= 1) score += 1
  if (score >= 7) return { label: 'S', color: '#ff4d4f' }
  if (score >= 5) return { label: 'A', color: '#faad14' }
  if (score >= 3) return { label: 'B', color: '#1890ff' }
  return { label: 'C', color: '#666' }
}

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

const formatRatePct = (value) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) return '--'
  return `${Number(value).toFixed(2)}%`
}

const getRiseCountClass = (value) => {
  if (value == null || Number.isNaN(Number(value))) return ''
  const n = Number(value)
  if (n >= 2800) return 'green'
  if (n < 2300) return 'down'
  return ''
}

const getBoardHitRateClass = (value) => {
  if (value == null || Number.isNaN(Number(value))) return ''
  const n = Number(value)
  if (n >= 65) return 'green'
  if (n < 40) return 'down'
  return 'orange'
}

const MIN_ECHELON_DATE = '20260511'

const clampEchelonDate = (dateStr) => {
  if (!dateStr || dateStr.length !== 8) return dateStr
  if (dateStr < MIN_ECHELON_DATE) return MIN_ECHELON_DATE
  const today = getLastTradingDayStr()
  return dateStr > today ? today : dateStr
}

export default function LimitUpEchelon() {
  const todayStr = useMemo(() => getLastTradingDayStr(), [])
  const [currentDate, setCurrentDate] = useState(() => clampEchelonDate(getLastTradingDayStr()))
  const dataCache = useRef({})
  const requestSeq = useRef(0)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useDidShow(() => {
    ensureAuth()
  })

  const fetchData = useCallback(async (targetDate) => {
    const requestId = requestSeq.current + 1
    requestSeq.current = requestId
    setLoading(true)

    if (dataCache.current[targetDate]) {
      if (requestSeq.current === requestId) {
        setData(dataCache.current[targetDate])
        setLoading(false)
      }
      return
    }

    try {
      const res = await api.get(`/api/v1/limit-up-echelon?dt=${formatDateDisplay(targetDate)}`)
      if (res?.data && requestSeq.current === requestId) {
        dataCache.current[targetDate] = res.data
        setData(res.data)
      } else if (requestSeq.current === requestId) {
        setData(null)
      }
    } catch (err) {
      if (requestSeq.current === requestId) setData(null)
    } finally {
      if (requestSeq.current === requestId) setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData(currentDate)
  }, [fetchData, currentDate])

  const echelons = useMemo(() => data?.echelons || [], [data])
  const summary = data?.summary || {}
  const themeRanking = useMemo(() => data?.theme_ranking || [], [data])

  const sortedThemeRanking = useMemo(() => {
    const others = []
    const normal = []
    for (const t of themeRanking) {
      if (t.theme === '其他概念' || t.theme === '其他') others.push(t)
      else normal.push(t)
    }
    return [...normal, ...others]
  }, [themeRanking])

  const summaryItems = [
    { label: '涨停', value: summary?.total || 0, cls: 'red' },
    { label: '首板', value: summary?.first_board_count || 0, cls: 'blue' },
    { label: '连板', value: summary?.consec_count || 0, cls: 'orange' },
    { label: '最高', value: `${summary?.max_boards || 0}板`, cls: 'purple' },
    { label: '跌停', value: summary?.limit_down_count ?? '--', cls: 'teal' },
    { label: '炸板', value: summary?.broken_board_count ?? '--', cls: 'amber' },
    { label: '炸板率', value: summary?.broken_board_rate != null ? `${summary.broken_board_rate}%` : '--', cls: 'amber' },
    { label: '上涨家数', value: summary?.rise_count != null ? summary.rise_count : '--', cls: getRiseCountClass(summary?.rise_count) },
    { label: '打板成功率', value: formatRatePct(summary?.board_hit_rate), cls: getBoardHitRateClass(summary?.board_hit_rate) },
  ]

  const dateNav = (
    <View className='date-nav'>
      <View
        className={`date-nav-btn ${currentDate <= MIN_ECHELON_DATE ? 'disabled' : ''}`}
        onClick={() => {
          if (currentDate > MIN_ECHELON_DATE) setCurrentDate(clampEchelonDate(offsetDate(currentDate, -1)))
        }}
      >
        {'< 前一天'}
      </View>
      <Text className='date-nav-label'>{formatDateDisplay(currentDate)}</Text>
      <View
        className={`date-nav-btn ${currentDate >= todayStr ? 'disabled' : ''}`}
        onClick={() => {
          if (currentDate < todayStr) setCurrentDate(clampEchelonDate(offsetDate(currentDate, 1)))
        }}
      >
        {'后一天 >'}
      </View>
    </View>
  )

  return (
    <View className='echelon-page'>
      {dateNav}

      {loading ? (
        <View className='echelon-loading'>加载涨停板梯队...</View>
      ) : !data || echelons.length === 0 ? (
        <View className='echelon-empty'>暂无涨停板数据（收盘后由系统离线生成，请稍后刷新）</View>
      ) : (
        <View>
          <ScrollView scrollX className='summary-scroll'>
            <View className='summary-row'>
              {summaryItems.map((it) => (
                <View className='summary-item' key={it.label}>
                  <Text className='summary-label'>{it.label}</Text>
                  <Text className={`summary-value ${it.cls}`}>{it.value}</Text>
                </View>
              ))}
            </View>
          </ScrollView>

          {sortedThemeRanking.length > 0 && (
            <ScrollView scrollX className='theme-scroll'>
              <View className='theme-row'>
                {sortedThemeRanking.map((t) => (
                  <View className='theme-chip' key={t.theme}>
                    <Text className='theme-chip-name'>{t.theme}</Text>
                    <Text className='theme-chip-count'>{t.count}</Text>
                  </View>
                ))}
              </View>
            </ScrollView>
          )}

          {echelons.map((echelon) => {
            const color = getBoardColor(echelon.boards)
            return (
              <View className='echelon-group' key={echelon.boards} style={{ borderLeftColor: color.tag }}>
                <View className='echelon-header'>
                  <Text className='echelon-tag' style={{ background: color.tag }}>
                    {echelon.boards >= 7 ? `${echelon.boards}板` : color.label}
                  </Text>
                  <Text className='echelon-count'>{echelon.count}只</Text>
                </View>

                {echelon.stocks.map((stock) => {
                  const quality = getSealQuality(stock)
                  const primary = stock.group_label || stock.theme || stock.industry
                  const themeCount = stock.theme_count || stock.group_count || 0
                  const hasTheme = !!(stock.group_label || stock.theme)
                  const thsTag = (stock.ths_hot_tag || '').trim()
                  const themeReason =
                    stock.ths_analyse_title ||
                    stock.theme_reason ||
                    sortedThemeRanking.find((t) => t.theme === primary)?.reason ||
                    ''
                  return (
                    <View className='stock-card' key={stock.code}>
                      <View className='stock-line1'>
                        <View className='stock-name-box'>
                          <Text className='stock-name'>{stock.name}</Text>
                          {stock.ths_rank > 0 && (
                            <Text className='ths-rank'>🔥{stock.ths_rank}</Text>
                          )}
                          <Text className='stock-code'>{stock.code}</Text>
                        </View>
                        <Text className='quality-badge' style={{ color: quality.color, borderColor: quality.color }}>
                          {quality.label}
                        </Text>
                      </View>

                      <View className='stock-tags'>
                        <Text className={`theme-tag ${hasTheme ? 'ai-theme' : ''}`}>
                          {primary}{hasTheme && themeCount > 1 ? ` ${themeCount}` : ''}
                        </Text>
                        {thsTag ? <Text className='theme-tag ths'>{thsTag}</Text> : null}
                      </View>

                      <View className='stock-metrics'>
                        <View className='metric'>
                          <Text className='metric-label'>封单额</Text>
                          <Text className='metric-value'>{stock.seal_amount_text}</Text>
                        </View>
                        <View className='metric'>
                          <Text className='metric-label'>封成比</Text>
                          <Text
                            className='metric-value'
                            style={{ color: stock.seal_ratio >= 10 ? '#ff4d4f' : stock.seal_ratio >= 3 ? '#faad14' : '#999' }}
                          >
                            {stock.seal_ratio}
                          </Text>
                        </View>
                        <View className='metric'>
                          <Text className='metric-label'>成交额</Text>
                          <Text className='metric-value'>{stock.turnover_text}</Text>
                        </View>
                        <View className='metric'>
                          <Text className='metric-label'>换手率</Text>
                          <Text className='metric-value'>{stock.turnover_rate}%</Text>
                        </View>
                        <View className='metric'>
                          <Text className='metric-label'>首封</Text>
                          <Text className='metric-value'>{formatTime(stock.first_time)}</Text>
                        </View>
                        <View className='metric'>
                          <Text className='metric-label'>炸板</Text>
                          <Text className='metric-value' style={{ color: stock.break_count > 0 ? '#faad14' : 'var(--down)' }}>
                            {stock.break_count > 0 ? `${stock.break_count}次` : '0'}
                          </Text>
                        </View>
                      </View>

                      {(themeReason || stock.ths_analyse_title) && (
                        <Text className='stock-reason'>{themeReason || stock.ths_analyse_title}</Text>
                      )}
                    </View>
                  )
                })}
              </View>
            )
          })}
        </View>
      )}
    </View>
  )
}
