import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../config/api'
import { ensureAuth } from '../../services/auth'
import './index.scss'

const MIN_BOARD = 2
const LIVE_POLL_SEC = 60
const MARKET_LABEL = { cyb: '创', kcb: '科', main: '' }

const STAGE_COLOR = {
  冰点: '#94a3b8', 修复: '#0d9488', 升温: '#7c3aed',
  高潮: '#e11d48', 退潮: '#d97706',
}
const CYCLE_ORDER = ['冰点', '修复', '升温', '高潮', '退潮']

const stageKey = (stage) => (stage ? String(stage).replace(/期$/, '') : '')
const stageFull = (stage) => { const k = stageKey(stage); return k ? `${k}期` : '—' }
const stageColor = (stage) => STAGE_COLOR[stageKey(stage)] || '#6b7280'

const fmtPrem = (prem) => {
  if (prem == null || Number.isNaN(Number(prem))) return '—'
  const n = Number(prem)
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}

const premiumColor = (prem) => {
  if (prem == null || Number.isNaN(Number(prem))) return 'var(--text-muted)'
  const n = Number(prem)
  if (n >= 4) return '#b91c1c'
  if (n >= 0) return '#dc2626'
  if (n >= -3) return '#15803d'
  return '#166534'
}

function LadderChip({ name, market, cell, peak }) {
  const marketTag = MARKET_LABEL[market] || ''
  const isLive = cell.live === true
  const pending = !isLive && (cell.status === 'pending' || cell.premium == null)

  if (cell.status === 'broken') {
    return (
      <View className={`lp-chip lp-broken${peak ? ' peak' : ''}`}>
        <Text className='lp-chip-name'>{name}</Text>
        <Text className='lp-chip-tag'>断板</Text>
        {cell.premium != null && (
          <Text className='lp-chip-prem' style={{ color: premiumColor(cell.premium) }}>
            {fmtPrem(cell.premium)}
          </Text>
        )}
      </View>
    )
  }
  if (cell.status === 'suspended') {
    return (
      <View className={`lp-chip lp-muted${peak ? ' peak' : ''}`}>
        <Text className='lp-chip-name'>{name}</Text>
        <Text className='lp-chip-tag'>停牌</Text>
      </View>
    )
  }
  if (cell.status === 'limit_down') {
    return (
      <View className={`lp-chip lp-limitdown${peak ? ' peak' : ''}`}>
        <Text className='lp-chip-name'>{name}</Text>
        <Text className='lp-chip-tag'>跌停</Text>
      </View>
    )
  }

  const premCls = pending ? 'lp-chip-pending' : (Number(cell.premium) >= 0 ? 'lp-chip-up' : 'lp-chip-down')
  return (
    <View className={`lp-chip ${premCls}${peak ? ' peak' : ''}${isLive ? ' live' : ''}`}>
      <Text className='lp-chip-name'>
        {name}
        {marketTag ? <Text className='lp-mktag'>{marketTag}</Text> : null}
      </Text>
      <Text className='lp-chip-prem' style={{ color: pending ? 'var(--text-muted)' : premiumColor(cell.premium) }}>
        {pending ? '待' : fmtPrem(cell.premium)}
      </Text>
    </View>
  )
}

export default function LadderPremium() {
  const [days, setDays] = useState(10)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [scrollLeft, setScrollLeft] = useState(0)
  const pollRef = useRef(null)

  useDidShow(() => {
    ensureAuth()
  })

  const fetchData = useCallback(async (options = {}) => {
    const { silent = false, live = false } = options
    if (!silent) setLoading(true)
    try {
      const qs = live ? '&live=1' : ''
      const res = await api.get(`/api/v1/limit-up-ladder?days=${days}${qs}`, { timeout: 60000 })
      if (res?.success && res.data) setData(res.data)
      else if (!silent) setData({ days, dates: [], stocks: [] })
    } catch (e) {
      if (!silent) {
        setData({ days, dates: [], stocks: [] })
        Taro.showToast({ title: '加载失败', icon: 'none' })
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [days])

  useEffect(() => { fetchData() }, [fetchData])

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (!data?.is_newest_today || !data?.market_hours) return undefined
    pollRef.current = setInterval(() => fetchData({ silent: true, live: true }), LIVE_POLL_SEC * 1000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [data?.is_newest_today, data?.market_hours, fetchData])

  const dates = useMemo(() => data?.dates || [], [data])
  const stocks = useMemo(() => data?.stocks || [], [data])

  const cleanStocks = useMemo(() => stocks
    .map((s) => ({
      ...s,
      cells: s.cells.filter((c) => c.boards >= MIN_BOARD || c.status === 'broken' || c.status === 'suspended'),
    }))
    .filter((s) => s.cells.some((c) => c.boards >= MIN_BOARD)), [stocks])

  const boardsDesc = useMemo(() => {
    let hi = MIN_BOARD
    cleanStocks.forEach((s) => s.cells.forEach((c) => {
      if (c.boards >= MIN_BOARD) hi = Math.max(hi, c.boards)
    }))
    dates.forEach((d) => { if ((d.max_boards || 0) >= MIN_BOARD) hi = Math.max(hi, d.max_boards) })
    const list = []
    for (let b = hi; b >= MIN_BOARD; b -= 1) list.push(b)
    return list
  }, [cleanStocks, dates])

  const grid = useMemo(() => {
    const map = {}
    cleanStocks.forEach((s) => s.cells.forEach((c) => {
      if (c.boards < MIN_BOARD && c.status !== 'broken' && c.status !== 'suspended') return
      const key = `${c.dt}_${c.boards}`
      ;(map[key] || (map[key] = [])).push({ code: s.code, name: s.name, market: s.market, cell: c })
    }))
    const rank = (item) => {
      const { cell } = item
      if (cell.status === 'broken' || cell.status === 'suspended') return -1e6
      if (cell.status === 'limit_down') return -1e5
      if (cell.status === 'pending' || cell.premium == null) return -1e4
      if (cell.live) return cell.premium + 1e3
      return cell.premium
    }
    Object.values(map).forEach((arr) => arr.sort((a, b) => rank(b) - rank(a)))
    return map
  }, [cleanStocks])

  const peakSet = useMemo(() => {
    const set = new Set()
    dates.forEach((d) => {
      const top = grid[`${d.dt}_${d.max_boards}`]
      if (top?.length) set.add(`${d.dt}-${top[0].code}`)
    })
    return set
  }, [dates, grid])

  const firstBoardCount = (dt) => {
    if (dt.limit_up_count == null || dt.consec_count == null) return null
    return Math.max(0, dt.limit_up_count - dt.consec_count)
  }

  const colWidth = 280
  const axisWidth = 88
  const gridWidth = axisWidth + dates.length * colWidth

  useEffect(() => {
    if (!dates.length) return
    setScrollLeft(Math.max(0, gridWidth - 620))
  }, [dates.length, gridWidth])

  return (
    <View className='lp-page'>
      <View className='lp-head'>
        <Text className='lp-title'>连板情绪溢价表</Text>
        <Text className='lp-sub'>龙头能量线 · 次日溢价</Text>
      </View>

      <View className='lp-toolbar'>
        <View className='lp-days'>
          {[10, 30].map((d) => (
            <Text
              key={d}
              className={`lp-day-btn${days === d ? ' on' : ''}`}
              onClick={() => setDays(d)}
            >
              近{d}日
            </Text>
          ))}
        </View>
        {data?.is_newest_today && data?.market_hours && (
          <Text className='lp-live'>盘中 · {LIVE_POLL_SEC}s</Text>
        )}
      </View>

      <View className='lp-legend'>
        <Text className='lp-leg up'>● 次日涨</Text>
        <Text className='lp-leg down'>● 次日跌</Text>
        <Text className='lp-leg broken'>● 断板</Text>
      </View>

      <ScrollView scrollX className='lp-cycle-scroll' showScrollbar={false}>
        <View className='lp-cycle-row'>
          {CYCLE_ORDER.map((name) => (
            <Text
              key={name}
              className='lp-cycle-chip'
              style={{ color: STAGE_COLOR[name], borderColor: STAGE_COLOR[name] }}
            >
              {name}期
            </Text>
          ))}
        </View>
      </ScrollView>

      {loading && (
        <View className='lp-state'><Text>加载中…</Text></View>
      )}

      {!loading && dates.length === 0 && (
        <View className='lp-state'><Text>暂无梯队数据</Text></View>
      )}

      {!loading && dates.length > 0 && (
        <ScrollView
          scrollX
          className='lp-scroll'
          scrollLeft={scrollLeft}
          showScrollbar={false}
        >
          <View className='lp-grid' style={{ width: `${gridWidth}rpx` }}>
            {boardsDesc.map((b) => (
              <View className='lp-row' key={`row-${b}`}>
                <View className='lp-axis'>
                  <Text className='lp-axis-txt'>{b}板</Text>
                </View>
                {dates.map((d) => {
                  const items = grid[`${d.dt}_${b}`] || []
                  const tint = stageColor(d.stage)
                  return (
                    <View
                      key={`${d.dt}-${b}`}
                      className='lp-cell'
                      style={{ borderTopColor: tint }}
                    >
                      {items.length === 0 ? (
                        <Text className='lp-empty'>—</Text>
                      ) : items.slice(0, 6).map((it, idx) => (
                        <LadderChip
                          key={`${it.code}-${idx}`}
                          {...it}
                          peak={peakSet.has(`${d.dt}-${it.code}`)}
                        />
                      ))}
                      {items.length > 6 && (
                        <Text className='lp-more'>+{items.length - 6}</Text>
                      )}
                    </View>
                  )
                })}
              </View>
            ))}

            <View className='lp-row lp-row-first'>
              <View className='lp-axis'><Text className='lp-axis-txt'>首板</Text></View>
              {dates.map((d) => {
                const fb = firstBoardCount(d)
                const tint = stageColor(d.stage)
                return (
                  <View key={`fb-${d.dt}`} className='lp-cell lp-cell-count' style={{ borderTopColor: tint }}>
                    <Text className='lp-count'>{fb == null ? '—' : fb}</Text>
                  </View>
                )
              })}
            </View>

            <View className='lp-row lp-row-foot'>
              <View className='lp-axis'><Text className='lp-axis-txt foot'>日期</Text></View>
              {dates.map((d, i) => {
                const col = stageColor(d.stage)
                const isLast = i === dates.length - 1
                return (
                  <View
                    key={`foot-${d.dt}`}
                    className={`lp-foot${isLast ? ' today' : ''}`}
                    style={{ borderTopColor: col }}
                  >
                    <Text className='lp-foot-date'>{d.display}</Text>
                    <Text className='lp-foot-wd'>{d.weekday}</Text>
                    <Text className='lp-foot-stage' style={{ color: col }}>{stageFull(d.stage)}</Text>
                    <Text className='lp-foot-stat'>
                      涨停 {d.limit_up_count ?? '—'} · 连板 {d.consec_count ?? '—'}
                    </Text>
                    <Text className='lp-foot-stat'>
                      最高 {d.max_boards ?? '—'}板 · 炸板 {d.broken_board_count ?? '—'}
                    </Text>
                    {(d.rise_count != null && d.fall_count != null) && (
                      <Text className='lp-foot-stat'>
                        <Text className='up'>涨{d.rise_count}</Text>
                        {' '}
                        <Text className='down'>跌{d.fall_count}</Text>
                      </Text>
                    )}
                  </View>
                )
              })}
            </View>
          </View>
        </ScrollView>
      )}

      <Text className='lp-hint'>左右滑动查看历史数据</Text>
    </View>
  )
}
