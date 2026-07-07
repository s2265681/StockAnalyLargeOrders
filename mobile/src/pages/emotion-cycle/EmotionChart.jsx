import { useEffect, useRef } from 'react'
import Taro from '@tarojs/taro'
import { Canvas } from '@tarojs/components'

const SERIES = [
  { key: 'limit_up_count', name: '涨停', color: '#f5222d' },
  { key: 'limit_down_count', name: '跌停', color: '#1677ff' },
  { key: 'consec_limit', name: '连板', color: '#52c41a' },
  { key: 'latest_height', name: '最高', color: '#fa8c16' },
]

const num = (v) => {
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

export default function EmotionChart({ records, canvasId = 'emotionChart' }) {
  const boxRef = useRef(null)

  useEffect(() => {
    const draw = () => {
      const sys = Taro.getSystemInfoSync()
      const pxPerRpx = sys.windowWidth / 750
      const w = Math.round(686 * pxPerRpx)
      const h = Math.round(420 * pxPerRpx)

      const ctx = Taro.createCanvasContext(canvasId)
      ctx.clearRect(0, 0, w, h)

      const rows = (records || []).filter((r) => r && r.date)
      if (rows.length === 0) {
        ctx.setFillStyle('#8a94a6')
        ctx.setFontSize(Math.round(24 * pxPerRpx))
        ctx.setTextAlign('center')
        ctx.fillText('暂无数据', w / 2, h / 2)
        ctx.draw()
        return
      }

      const padL = Math.round(56 * pxPerRpx)
      const padR = Math.round(16 * pxPerRpx)
      const padT = Math.round(44 * pxPerRpx)
      const padB = Math.round(40 * pxPerRpx)
      const plotW = w - padL - padR
      const plotH = h - padT - padB

      // y 范围
      let maxV = 0
      rows.forEach((r) => {
        SERIES.forEach((s) => {
          const v = num(r[s.key])
          if (v != null && v > maxV) maxV = v
        })
      })
      if (maxV <= 0) maxV = 1
      const yMax = Math.ceil(maxV / 10) * 10 || 10
      const n = rows.length
      const xToPx = (i) => padL + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW)
      const yToPx = (v) => padT + (1 - v / yMax) * plotH

      // 网格 + y 刻度
      ctx.setStrokeStyle('rgba(140,148,166,0.18)')
      ctx.setLineWidth(1)
      ctx.setFillStyle('#8a94a6')
      ctx.setFontSize(Math.round(20 * pxPerRpx))
      ctx.setTextAlign('right')
      const ticks = 4
      for (let t = 0; t <= ticks; t++) {
        const val = (yMax / ticks) * t
        const y = yToPx(val)
        ctx.beginPath()
        ctx.moveTo(padL, y)
        ctx.lineTo(w - padR, y)
        ctx.stroke()
        ctx.fillText(String(Math.round(val)), padL - Math.round(8 * pxPerRpx), y + Math.round(6 * pxPerRpx))
      }

      // x 轴日期标签（稀疏，最多 5 个）
      ctx.setTextAlign('center')
      const labelStep = Math.max(1, Math.ceil(n / 5))
      rows.forEach((r, i) => {
        if (i % labelStep !== 0 && i !== n - 1) return
        const md = String(r.date).slice(5)
        ctx.fillText(md, xToPx(i), h - Math.round(14 * pxPerRpx))
      })

      // 折线
      SERIES.forEach((s) => {
        ctx.setStrokeStyle(s.color)
        ctx.setLineWidth(Math.max(1, Math.round(1.5 * pxPerRpx)))
        ctx.beginPath()
        let started = false
        rows.forEach((r, i) => {
          const v = num(r[s.key])
          if (v == null) return
          const x = xToPx(i)
          const y = yToPx(v)
          if (!started) { ctx.moveTo(x, y); started = true } else { ctx.lineTo(x, y) }
        })
        ctx.stroke()
      })

      // 图例（顶部）
      const legendY = Math.round(22 * pxPerRpx)
      const itemW = plotW / SERIES.length
      ctx.setFontSize(Math.round(22 * pxPerRpx))
      ctx.setTextAlign('left')
      SERIES.forEach((s, i) => {
        const x = padL + i * itemW
        ctx.setFillStyle(s.color)
        ctx.fillRect(x, legendY - Math.round(10 * pxPerRpx), Math.round(20 * pxPerRpx), Math.round(6 * pxPerRpx))
        ctx.setFillStyle('#333')
        ctx.fillText(s.name, x + Math.round(26 * pxPerRpx), legendY)
      })

      ctx.draw()
    }

    if (Taro.nextTick) Taro.nextTick(draw); else draw()
    const timer = setTimeout(draw, 150)
    return () => clearTimeout(timer)
  }, [records, canvasId])

  return (
    <Canvas
      canvasId={canvasId}
      id={canvasId}
      ref={boxRef}
      style={{ width: '686rpx', height: '420rpx' }}
    />
  )
}
