import { useState, useEffect, useCallback } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { api, getToken } from '../../config/api'
import './index.scss'

const FLAG_MAP = {
  gb_dji: '🇺🇸', gb_ixic: '🇺🇸', gb_inx: '🇺🇸',
  rt_hkHSI: '🇭🇰', gb_nikkei: '🇯🇵', N225: '🇯🇵',
  b_INDEXDOW: '🇺🇸', b_INDEXNASDAQ: '🇺🇸', b_INDEXSP: '🇺🇸',
  b_INDEXHK: '🇭🇰', b_INDEXNK225: '🇯🇵',
}

function formatTime(iso) {
  if (!iso) return ''
  const s = String(iso)
  return s.length >= 16 ? s.slice(11, 16) : s
}

const briefErrorText = (msg) => {
  const s = String(msg || '')
  if (s.includes('海外指数') || s.includes('东财') || s.includes('新浪') || s.includes('b_INDEX')) {
    return '海外指数获取失败，请稍后重试'
  }
  if (s.length > 24) return s.slice(0, 24) + '…'
  return s || '生成失败'
}

export default function MarketBriefBar() {
  const [brief, setBrief] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [errorHint, setErrorHint] = useState('')

  const loadBrief = useCallback(async () => {
    const res = await api.get('/api/market-brief/today')
    if (res.success && res.data?.available) {
      setBrief(res.data)
      return true
    }
    setBrief(null)
    return false
  }, [])

  const generateBrief = useCallback(async (force = false) => {
    setGenerating(true)
    setErrorHint('')
    try {
      const res = await api.post('/api/market-brief/refresh', { force }, { timeout: 120000 })
      if (res.success && res.data?.available) {
        setBrief(res.data)
        Taro.showToast({ title: '盘前资讯已生成', icon: 'success' })
        return true
      }
      const hint = briefErrorText(res.message)
      setErrorHint(hint)
      Taro.showToast({ title: hint, icon: 'none' })
    } catch (e) {
      const hint = briefErrorText(e.message)
      setErrorHint(hint)
      Taro.showToast({ title: hint, icon: 'none' })
    } finally {
      setGenerating(false)
    }
    return false
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setErrorHint('')
      try {
        await loadBrief()
      } catch (e) {
        /* 静默 */
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [loadBrief])

  if (loading || generating) {
    return (
      <View className='brief-card brief-state'>
        <Text className='brief-state-text'>
          {generating ? '正在生成今日盘前资讯（约 30–90 秒）…' : '加载盘前资讯…'}
        </Text>
      </View>
    )
  }

  if (!brief?.overseas?.length || !brief?.ai_summary) {
    const hasToken = !!getToken()
    return (
      <View className='brief-card brief-state'>
        <Text className='brief-badge'>盘前参考</Text>
        <Text className='brief-state-text'>
          {errorHint || '今日尚未生成'}
        </Text>
        {hasToken && (
          <Text className='brief-gen-btn' onClick={() => generateBrief(true)}>
            {errorHint ? '重新生成' : '立即生成'}
          </Text>
        )}
      </View>
    )
  }

  return (
    <View className='brief-card'>
      <View className='brief-head'>
        <Text className='brief-badge'>盘前参考</Text>
        <Text className='brief-time'>{formatTime(brief.generated_at)} 更新</Text>
      </View>

      <View className='brief-indices'>
        {brief.overseas.map((idx) => (
          <View className='brief-chip' key={idx.symbol}>
            <Text className='brief-chip-flag'>{FLAG_MAP[idx.symbol] || '🌐'}</Text>
            <Text className='brief-chip-name'>{idx.name}</Text>
            <Text className={`brief-chip-pct ${idx.change_pct >= 0 ? 'up' : 'down'}`}>
              {idx.change_pct >= 0 ? '+' : ''}{idx.change_pct}%
            </Text>
          </View>
        ))}
      </View>

      <View className='brief-summary' onClick={() => setExpanded((v) => !v)}>
        <Text className='brief-summary-tag'>AI 摘要</Text>
        <Text className='brief-summary-text'>
          {expanded ? brief.ai_summary : (brief.ai_summary.length > 56 ? `${brief.ai_summary.slice(0, 56)}…` : brief.ai_summary)}
        </Text>
        <Text className='brief-summary-action'>{expanded ? '收起' : '查看全文'}</Text>
      </View>
    </View>
  )
}
