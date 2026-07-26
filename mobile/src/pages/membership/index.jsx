import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, Button } from '@tarojs/components'
import { ensureAuth, getUser, refreshUser, isVip } from '../../services/auth'
import { PLANS, payPlan } from '../../services/pay'
import './index.scss'

export default function Membership() {
  const [selected, setSelected] = useState('monthly')
  const [paying, setPaying] = useState(false)
  const [vipEnd, setVipEnd] = useState('')

  useDidShow(async () => {
    if (!ensureAuth()) return
    await refreshUser()
    const user = getUser()
    if (isVip() && user && user.vip) setVipEnd(user.vip.end_time)
  })

  const handlePay = async () => {
    if (paying) return
    setPaying(true)
    Taro.showLoading({ title: '正在发起支付', mask: true })
    const res = await payPlan(selected)
    Taro.hideLoading()
    setPaying(false)
    if (res.paid) {
      Taro.showToast({ title: 'VIP 已开通', icon: 'success' })
      await refreshUser()
      const user = getUser()
      if (user && user.vip) setVipEnd(user.vip.end_time)
    } else {
      Taro.showToast({ title: res.message, icon: 'none' })
    }
  }

  return (
    <View className='vip-page'>
      <View className='vip-header'>
        <Text className='vip-title'>重阳市场看板助手 · 会员</Text>
        {vipEnd ? (
          <Text className='vip-status'>会员有效期至 {String(vipEnd).slice(0, 10)}</Text>
        ) : (
          <Text className='vip-status'>开通后解锁全部分析功能</Text>
        )}
      </View>

      <View className='plan-list'>
        {PLANS.map((p) => (
          <View
            key={p.type}
            className={`plan-item ${selected === p.type ? 'plan-item--on' : ''}`}
            onClick={() => setSelected(p.type)}
          >
            <View className='plan-main'>
              <Text className='plan-name'>{p.name}</Text>
              <Text className='plan-days'>{p.days} 天</Text>
            </View>
            <Text className='plan-price'>¥{p.amount}</Text>
          </View>
        ))}
      </View>

      <Button className='pay-btn' loading={paying} onClick={handlePay}>
        微信支付
      </Button>
      <Text className='pay-note'>支付即视为同意会员服务条款，虚拟商品不支持退款</Text>
    </View>
  )
}
