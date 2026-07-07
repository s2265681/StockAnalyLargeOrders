import { useEffect, useRef } from 'react'
import Taro from '@tarojs/taro'
import { Canvas } from '@tarojs/components'

const buildTradingTimeAxis = () => {
  const pts = []
  for (let h = 9; h <= 11; h++) {
    const start = h === 9 ? 30 : 0
    const end = h === 11 ? 30 : 59
    for (let m = start; m <= end; m++) {
      pts.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
    }
  }
  for (let h = 13; h <= 15; h++) {
    const end = h === 15 ? 0 : 59
    for (let m = 0; m <= end; m++) {
      pts.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
    }
  }
  return pts
}

const normalizeTimeKey = (t) => {
  const s = String(t || '').trim()
  if (!s) return ''
  if (s.includes(':')) return s.length > 5 ? s.slice(-8, -3) : s
  if (s.length === 4) return `${s.slice(0, 2)}:${s.slice(2)}`
  if (s.length === 6) return `${s.slice(0, 2)}:${s.slice(2, 4)}`
  return s
}

const AXIS = buildTradingTimeAxis()

export default function TimeshareChart({ timeshare, prevClose, limitUp, limitDown, canvasId = 'tsChart' }) {
  const sizeRef = useRef({ w: 0, h: 0 })

  useEffect(() => {
    const draw = () => {
    const sys = Taro.getSystemInfoSync()
    const pxPerRpx = sys.windowWidth / 750
    const w = Math.round(718 * pxPerRpx)
    const h = Math.round(360 * pxPerRpx)
    sizeRef.current = { w, h }

    const ctx = Taro.createCanvasContext(canvasId)
    ctx.clearRect(0, 0, w, h)

    const padL = Math.round(2 * pxPerRpx)
    const padR = Math.round(2 * pxPerRpx)
    const padT = Math.round(8 * pxPerRpx)
    const padB = Math.round(8 * pxPerRpx)
    const plotW = w - padL - padR
    const plotH = h - padT - padB

    const prev = parseFloat(prevClose)
    const byTime = new Map()
    ;(timeshare || []).forEach((item) => {
      byTime.set(normalizeTimeKey(item.time), item)
    })

    const prices = []
    const avgs = []
    AXIS.forEach((t) => {
      const item = byTime.get(t)
      const p = item ? parseFloat(item.price ?? item.avg_price) : null
      const a = item ? parseFloat(item.avg_price) : null
      prices.push(Number.isFinite(p) ? p : null)
      avgs.push(Number.isFinite(a) ? a : null)
    })

    const valid = prices.filter((p) => p != null)
    if (!Number.isFinite(prev) || valid.length === 0) {
      ctx.setFillStyle('#8a94a6')
      ctx.setFontSize(Math.round(24 * pxPerRpx))
      ctx.setTextAlign('center')
      ctx.fillText('暂无分时数据', w / 2, h / 2)
      ctx.draw()
      return
    }

    // Y 轴范围：优先用涨跌停对称，否则用价格极值对称
    let maxDiff
    const lu = parseFloat(limitUp)
    const ld = parseFloat(limitDown)
    if (Number.isFinite(lu) && Number.isFinite(ld)) {
      maxDiff = Math.max(lu - prev, prev - ld)
    } else {
      const hi = Math.max(...valid, prev)
      const lo = Math.min(...valid, prev)
      maxDiff = Math.max(hi - prev, prev - lo) || prev * 0.01
    }
    const yTop = prev + maxDiff
    const yBot = prev - maxDiff
    const yToPx = (v) => padT + ((yTop - v) / (yTop - yBot)) * plotH
    const xToPx = (i) => padL + (i / (AXIS.length - 1)) * plotW

    // 网格
    ctx.setStrokeStyle('rgba(140,148,166,0.18)')
    ctx.setLineWidth(1)
    ;[0.25, 0.5, 0.75].forEach((r) => {
      const y = padT + r * plotH
      ctx.beginPath()
      ctx.moveTo(padL, y)
      ctx.lineTo(w - padR, y)
      ctx.stroke()
    })
    // 午盘分隔（11:30 后为 121 点）
    const midIdx = 121
    const midX = xToPx(midIdx)
    ctx.beginPath()
    ctx.moveTo(midX, padT)
    ctx.lineTo(midX, padT + plotH)
    ctx.stroke()

    // 昨收基准虚线
    const baseY = yToPx(prev)
    ctx.setStrokeStyle('rgba(140,148,166,0.5)')
    ctx.setLineDash?.([4, 4])
    ctx.beginPath()
    ctx.moveTo(padL, baseY)
    ctx.lineTo(w - padR, baseY)
    ctx.stroke()
    ctx.setLineDash?.([])

    const last = valid[valid.length - 1]
    const upColor = '#e5484d'
    const downColor = '#12a150'
    const lineColor = last >= prev ? upColor : downColor

    // 价格线
    ctx.setStrokeStyle(lineColor)
    ctx.setLineWidth(Math.max(1, Math.round(1.5 * pxPerRpx)))
    ctx.beginPath()
    let started = false
    prices.forEach((p, i) => {
      if (p == null) return
      const x = xToPx(i)
      const y = yToPx(p)
      if (!started) {
        ctx.moveTo(x, y)
        started = true
      } else {
        ctx.lineTo(x, y)
      }
    })
    ctx.stroke()

    // 均价线
    ctx.setStrokeStyle('#f5a623')
    ctx.setLineWidth(1)
    ctx.beginPath()
    started = false
    avgs.forEach((a, i) => {
      if (a == null) return
      const x = xToPx(i)
      const y = yToPx(a)
      if (!started) {
        ctx.moveTo(x, y)
        started = true
      } else {
        ctx.lineTo(x, y)
      }
    })
    ctx.stroke()

    ctx.draw()
    }
    // weapp 下 canvas 节点可能晚于 effect 就绪：nextTick + 延时兜底重绘
    if (Taro.nextTick) Taro.nextTick(draw); else draw()
    const timer = setTimeout(draw, 150)
    return () => clearTimeout(timer)
  }, [timeshare, prevClose, limitUp, limitDown, canvasId])

  return (
    <Canvas
      canvasId={canvasId}
      id={canvasId}
      style={{ width: '718rpx', height: '360rpx' }}
    />
  )
}
