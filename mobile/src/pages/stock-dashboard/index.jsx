import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, Input, ScrollView } from '@tarojs/components'
import { api } from '../../config/api'
import { ensureAuth } from '../../services/auth'
import TimeshareChart from './TimeshareChart'
import './index.scss'

const MARKET_HOLIDAYS = new Set(['2026-05-01'])
const MAX_TRADING_DAYS = 5
const POLL_INTERVAL = 10000

const fmtLocal = (d) => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
const isTradingDay = (d) => {
  const w = d.getDay()
  return w !== 0 && w !== 6 && !MARKET_HOLIDAYS.has(fmtLocal(d))
}
const getLatestTradingDay = () => {
  const d = new Date()
  const now = new Date()
  if (now.getHours() < 9 || (now.getHours() === 9 && now.getMinutes() < 30)) {
    d.setDate(d.getDate() - 1)
  }
  while (!isTradingDay(d)) d.setDate(d.getDate() - 1)
  return fmtLocal(d)
}
const offsetTradingDay = (dateStr, delta) => {
  const [y, m, d] = dateStr.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  let remaining = Math.abs(delta)
  const step = delta > 0 ? 1 : -1
  while (remaining > 0) {
    date.setDate(date.getDate() + step)
    if (isTradingDay(date)) remaining -= 1
  }
  return fmtLocal(date)
}
const getMinTradingDay = () => {
  let d = getLatestTradingDay()
  for (let i = 1; i < MAX_TRADING_DAYS; i++) d = offsetTradingDay(d, -1)
  return d
}

const fmtPrice = (v) => (v != null && Number.isFinite(Number(v)) ? Number(v).toFixed(2) : '--')
const fmtWan = (v) => (v != null && Number.isFinite(Number(v)) ? (Number(v) / 10000).toFixed(2) : '--')
const fmtYi = (v) => (v != null && Number.isFinite(Number(v)) ? (Number(v) / 100000000).toFixed(2) : '--')
const fmtMoneyWan = (v) => {
  const n = Number(v || 0)
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}亿`
  return `${n.toFixed(0)}万`
}

const isBuyDir = (d) => d === '主买' || d === '被买'

export default function StockDashboard() {
  const [code, setCode] = useState('000001')
  const [searchInput, setSearchInput] = useState('')
  const [dt, setDt] = useState(getLatestTradingDay)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [amountFilter, setAmountFilter] = useState(30)
  const pollTimer = useRef(null)
  const reqSeq = useRef(0)

  const latestDay = useMemo(() => getLatestTradingDay(), [])
  const minDay = useMemo(() => getMinTradingDay(), [])
  const isLatest = dt === latestDay
  const canPrev = dt > minDay
  const canNext = dt < latestDay

  useDidShow(() => {
    ensureAuth()
  })

  const fetchData = useCallback(async (theCode, theDt, silent) => {
    const seq = ++reqSeq.current
    if (!silent) {
      setLoading(true)
      setError('')
    }
    try {
      const res = await api.get(`/api/v1/l2_dashboard?code=${theCode}&dt=${theDt}`, { timeout: 45000 })
      if (seq !== reqSeq.current) return
      if (res?.success && res?.data) {
        setData(res.data)
      } else if (!silent) {
        setError(res?.message || '获取数据失败')
      }
    } catch (e) {
      if (seq === reqSeq.current && !silent) setError(`获取数据失败: ${e.message}`)
    } finally {
      if (seq === reqSeq.current && !silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    setData(null)
    fetchData(code, dt, false)
  }, [code, dt, fetchData])

  // 最新交易日轮询
  useEffect(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
    if (!isLatest) return
    pollTimer.current = setInterval(() => {
      fetchData(code, dt, true)
    }, POLL_INTERVAL)
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current)
    }
  }, [code, dt, isLatest, fetchData])

  const handleSearch = () => {
    const v = searchInput.trim()
    if (/^\d{6}$/.test(v)) {
      setCode(v)
      setSearchInput('')
    } else {
      Taro.showToast({ title: '请输入6位股票代码', icon: 'none' })
    }
  }

  const info = data?.stock_info || {}
  const changePct = info.change_percent
  const up = Number(changePct) >= 0
  const priceColor = up ? 'var(--up)' : 'var(--down)'
  const prevClose = info.yesterday_close ?? info.pre_close
  const monitor = data?.limit_up_monitor
  const orderBook = data?.order_book || {}
  const asks = orderBook.asks || []
  const bids = orderBook.bids || []
  const stats = data?.statistics || {}
  const orders = data?.large_orders || data?.orders || []
  const moneyflow = data?.moneyflow

  const levelRows = useMemo(() => {
    const map = { 300: 'above_300', 100: 'above_100', 50: 'above_50', 30: 'above_30' }
    return [300, 100, 50, 30].map((lv) => {
      const s = stats[map[lv]] || {}
      const buy = s.buy_count || 0
      const sell = (s.sell_count || 0) + (s.neutral_count || 0)
      const total = buy + sell
      return {
        lv,
        buy,
        sell,
        buyAmt: s.buy_amount || 0,
        sellAmt: (s.sell_amount || 0) + (s.neutral_amount || 0),
        buyPct: total > 0 ? (buy / total) * 100 : 50,
      }
    })
  }, [stats])

  const filteredOrders = useMemo(() => {
    return orders
      .filter((o) => Number(o.amount || 0) >= amountFilter)
      .slice(0, 50)
      .map((o) => ({
        time: String(o.time || '').includes(' ') ? String(o.time).split(' ')[1] : o.time,
        dir: o.direction || (o.type === 'buy' ? '买' : '卖'),
        buy: o.direction ? isBuyDir(o.direction) : o.type === 'buy',
        price: fmtPrice(o.price),
        volume: o.volume_lots ?? o.volume,
        amount: Number(o.amount || 0).toFixed(1),
      }))
  }, [orders, amountFilter])

  const mfRows = useMemo(() => {
    if (!moneyflow?.items?.length) return null
    const last = moneyflow.items[moneyflow.items.length - 1]
    return {
      time: last.time,
      summary: moneyflow.summary,
      rows: [
        { label: '超大单', inVal: last.super_big_in, outVal: last.super_big_out },
        { label: '大单', inVal: last.big_in, outVal: last.big_out },
        { label: '小单', inVal: last.small_in, outVal: last.small_out },
      ],
    }
  }, [moneyflow])

  return (
    <View className='sd-page'>
      {/* 顶部：搜索 + 日期导航 */}
      <View className='sd-top'>
        <View className='sd-search'>
          <Input
            className='sd-search-input'
            value={searchInput}
            placeholder='输入6位股票代码'
            type='number'
            maxlength={6}
            onInput={(e) => setSearchInput(e.detail.value)}
            onConfirm={handleSearch}
          />
          <View className='sd-search-btn' onClick={handleSearch}>查询</View>
        </View>
        <View className='sd-date-nav'>
          <Text
            className={`sd-nav-btn ${canPrev ? '' : 'disabled'}`}
            onClick={() => { if (canPrev) setDt(offsetTradingDay(dt, -1)) }}
          >{'< 前一天'}</Text>
          <Text className='sd-nav-label'>{dt}{isLatest ? ' · 最新' : ''}</Text>
          <Text
            className={`sd-nav-btn ${canNext ? '' : 'disabled'}`}
            onClick={() => { if (canNext) setDt(offsetTradingDay(dt, 1)) }}
          >{'后一天 >'}</Text>
        </View>
      </View>

      {loading && !data ? (
        <View className='sd-loading'>加载中…</View>
      ) : error && !data ? (
        <View className='sd-empty'>{error}</View>
      ) : !data ? (
        <View className='sd-empty'>暂无数据</View>
      ) : (
        <View>
          {/* 基础信息头 */}
          <View className='sd-card sd-header'>
            <View className='sd-header-top'>
              <Text className='sd-name'>{info.name || code}</Text>
              <Text className='sd-code'>{info.code || code}</Text>
            </View>
            <View className='sd-price-row'>
              <Text className='sd-price' style={{ color: priceColor }}>
                {fmtPrice(info.current_price ?? info.price)}
              </Text>
              <Text className='sd-change' style={{ color: priceColor }}>
                {up ? '+' : ''}{info.change_amount != null ? Number(info.change_amount).toFixed(2) : '--'}
                {'  '}
                {up ? '+' : ''}{changePct != null ? `${Number(changePct).toFixed(2)}%` : '--'}
              </Text>
            </View>
            <View className='sd-stats-grid'>
              <View className='sd-stat'><Text className='sd-stat-l'>开</Text><Text className='sd-stat-v'>{fmtPrice(info.open)}</Text></View>
              <View className='sd-stat'><Text className='sd-stat-l'>高</Text><Text className='sd-stat-v' style={{ color: 'var(--up)' }}>{fmtPrice(info.high)}</Text></View>
              <View className='sd-stat'><Text className='sd-stat-l'>低</Text><Text className='sd-stat-v' style={{ color: 'var(--down)' }}>{fmtPrice(info.low)}</Text></View>
              <View className='sd-stat'><Text className='sd-stat-l'>昨</Text><Text className='sd-stat-v'>{fmtPrice(prevClose)}</Text></View>
              <View className='sd-stat'><Text className='sd-stat-l'>量(万手)</Text><Text className='sd-stat-v'>{fmtWan(info.volume)}</Text></View>
              <View className='sd-stat'><Text className='sd-stat-l'>额(亿)</Text><Text className='sd-stat-v'>{fmtYi(info.turnover)}</Text></View>
            </View>
          </View>

          {/* 涨停封单监控 */}
          {monitor?.is_limit_up && (
            <View className='sd-card sd-monitor'>
              <View className='sd-monitor-head'>
                <Text className='sd-tag-red'>涨停</Text>
                <Text className='sd-monitor-price'>{monitor.limit_up_price}</Text>
                {monitor.first_limit_time ? <Text className='sd-monitor-time'>首封 {monitor.first_limit_time}</Text> : null}
                {monitor.break_count > 0 ? <Text className='sd-tag-orange'>炸板 {monitor.break_count} 次</Text> : null}
              </View>
              <View className='sd-monitor-stats'>
                <Text className='sd-monitor-item'>封单 {Number(monitor.seal_amount || 0).toFixed(0)}万</Text>
                <Text className='sd-monitor-item'>封单比 {(monitor.seal_ratio * 100).toFixed(2)}%</Text>
                <Text className='sd-monitor-item'>趋势 {monitor.seal_trend_label || '--'}</Text>
              </View>
            </View>
          )}

          {/* 分时图 */}
          <View className='sd-card'>
            <Text className='sd-card-title'>分时走势</Text>
            <TimeshareChart
              timeshare={data.timeshare}
              prevClose={prevClose}
              limitUp={info.limit_up}
              limitDown={info.limit_down}
            />
            <View className='sd-chart-legend'>
              <Text className='sd-legend-item' style={{ color: 'var(--up)' }}>— 价格</Text>
              <Text className='sd-legend-item' style={{ color: '#f5a623' }}>— 均价</Text>
              <Text className='sd-legend-item' style={{ color: 'var(--text-muted)' }}>--- 昨收</Text>
            </View>
          </View>

          {/* 资金流向 */}
          {mfRows && mfRows.summary && (
            <View className='sd-card'>
              <View className='sd-card-title-row'>
                <Text className='sd-card-title'>资金流向</Text>
                <Text className='sd-card-sub'>同花顺 {mfRows.time ? `${String(mfRows.time).slice(0, 2)}:${String(mfRows.time).slice(2)}` : ''}</Text>
              </View>
              <View className='sd-mf-hero'>
                <Text className='sd-mf-hero-l'>主力净额</Text>
                <Text className='sd-mf-hero-v' style={{ color: (mfRows.summary.main_net_wan || 0) >= 0 ? 'var(--up)' : 'var(--down)' }}>
                  {(mfRows.summary.main_net_wan || 0) >= 0 ? '+' : ''}{fmtMoneyWan(mfRows.summary.main_net_wan)}
                </Text>
              </View>
              {mfRows.rows.map((r) => {
                const net = r.inVal - r.outVal
                const total = r.inVal + r.outVal
                const inPct = total > 0 ? (r.inVal / total) * 100 : 50
                return (
                  <View className='sd-mf-row' key={r.label}>
                    <Text className='sd-mf-label'>{r.label}</Text>
                    <View className='sd-mf-bar'>
                      <View className='sd-mf-bar-in' style={{ width: `${inPct}%` }} />
                      <View className='sd-mf-bar-out' style={{ width: `${100 - inPct}%` }} />
                    </View>
                    <Text className='sd-mf-net' style={{ color: net >= 0 ? 'var(--up)' : 'var(--down)' }}>
                      {net >= 0 ? '+' : ''}{fmtMoneyWan(net / 10000)}
                    </Text>
                  </View>
                )
              })}
            </View>
          )}

          {/* 五档盘口 */}
          {(asks.length > 0 || bids.length > 0) && (
            <View className='sd-card'>
              <Text className='sd-card-title'>五档盘口</Text>
              <View className='sd-book'>
                <View className='sd-book-col'>
                  {asks.slice().reverse().map((it) => (
                    <View className='sd-book-row' key={`a${it.level}`}>
                      <Text className='sd-book-lv'>卖{it.level}</Text>
                      <Text className='sd-book-px' style={{ color: 'var(--down)' }}>{fmtPrice(it.price)}</Text>
                      <Text className='sd-book-amt'>{fmtMoneyWan(Number(it.amount) / 10000)}</Text>
                    </View>
                  ))}
                </View>
                <View className='sd-book-col'>
                  {bids.map((it) => (
                    <View className='sd-book-row' key={`b${it.level}`}>
                      <Text className='sd-book-lv'>买{it.level}</Text>
                      <Text className='sd-book-px' style={{ color: 'var(--up)' }}>{fmtPrice(it.price)}</Text>
                      <Text className='sd-book-amt'>{fmtMoneyWan(Number(it.amount) / 10000)}</Text>
                    </View>
                  ))}
                </View>
              </View>
            </View>
          )}

          {/* 大单分布 */}
          {orders.length > 0 && (
            <View className='sd-card'>
              <Text className='sd-card-title'>大单分布</Text>
              {levelRows.map((r) => (
                <View className='sd-level' key={r.lv}>
                  <View className='sd-level-head'>
                    <Text className='sd-level-label'>≥{r.lv}万</Text>
                    <Text className='sd-level-cnt'>{r.buy + r.sell} 笔</Text>
                  </View>
                  <View className='sd-level-bar'>
                    <View className='sd-level-bar-buy' style={{ width: `${r.buyPct}%` }} />
                    <View className='sd-level-bar-sell' style={{ width: `${100 - r.buyPct}%` }} />
                  </View>
                  <View className='sd-level-detail'>
                    <Text style={{ color: 'var(--up)' }}>买 {r.buy}（{r.buyAmt.toFixed(0)}万）</Text>
                    <Text style={{ color: 'var(--down)' }}>卖 {r.sell}（{r.sellAmt.toFixed(0)}万）</Text>
                  </View>
                </View>
              ))}
            </View>
          )}

          {/* 大单明细 */}
          {orders.length > 0 && (
            <View className='sd-card'>
              <View className='sd-card-title-row'>
                <Text className='sd-card-title'>大单明细</Text>
                <View className='sd-filter'>
                  {[30, 50, 100, 300].map((lv) => (
                    <Text
                      key={lv}
                      className={`sd-filter-btn ${amountFilter === lv ? 'active' : ''}`}
                      onClick={() => setAmountFilter(lv)}
                    >≥{lv}</Text>
                  ))}
                </View>
              </View>
              <View className='sd-trade-head'>
                <Text className='sd-trade-c sd-trade-time'>时间</Text>
                <Text className='sd-trade-c'>性质</Text>
                <Text className='sd-trade-c'>价格</Text>
                <Text className='sd-trade-c'>手数</Text>
                <Text className='sd-trade-c'>金额万</Text>
              </View>
              <ScrollView scrollY className='sd-trade-scroll'>
                {filteredOrders.length === 0 ? (
                  <Text className='sd-trade-empty'>无符合条件的大单</Text>
                ) : (
                  filteredOrders.map((t, i) => (
                    <View className='sd-trade-row' key={`${t.time}-${i}`}>
                      <Text className='sd-trade-c sd-trade-time'>{t.time}</Text>
                      <Text className='sd-trade-c' style={{ color: t.buy ? 'var(--up)' : 'var(--down)' }}>{t.dir}</Text>
                      <Text className='sd-trade-c'>{t.price}</Text>
                      <Text className='sd-trade-c'>{t.volume}</Text>
                      <Text className='sd-trade-c' style={{ color: t.buy ? 'var(--up)' : 'var(--down)' }}>{t.amount}</Text>
                    </View>
                  ))
                )}
              </ScrollView>
            </View>
          )}
        </View>
      )}
    </View>
  )
}
