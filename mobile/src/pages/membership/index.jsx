import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, Button } from '@tarojs/components'
import { ensureAuth, getUser, refreshUser, isVip } from '../../services/auth'
import './index.scss'

const PC_SITE = 'https://www.stockai.xin'

const VIP_FEATURES = [
  '全部统计模块无限制使用',
  '涨停梯队、连板溢价、龙虎榜',
  '情绪周期、竞价/板块异动',
  '与 PC 网站同一账号同步',
]

export default function Membership() {
  const [vipEnd, setVipEnd] = useState('')
  const [username, setUsername] = useState('')

  useDidShow(async () => {
    if (!ensureAuth()) return
    await refreshUser()
    const user = getUser()
    setUsername(user?.username || '')
    if (isVip() && user?.vip) setVipEnd(user.vip.end_time)
    else setVipEnd('')
  })

  const copySite = () => {
    Taro.setClipboardData({
      data: PC_SITE,
      success: () => Taro.showToast({ title: '网址已复制', icon: 'success' }),
    })
  }

  return (
    <View className='vip-page'>
      <View className='vip-header'>
        <Text className='vip-title'>会员说明</Text>
        {vipEnd ? (
          <Text className='vip-status'>当前账号已开通 VIP，有效期至 {String(vipEnd).slice(0, 10)}</Text>
        ) : (
          <Text className='vip-status'>
            {username ? `${username} · ` : ''}开通后解锁全部统计功能
          </Text>
        )}
      </View>

      <View className='vip-card'>
        <Text className='vip-card-title'>小程序内暂不提供购买</Text>
        <Text className='vip-card-desc'>
          根据平台规范，VIP 会员请在电脑浏览器打开官网开通，支付成功后与本小程序账号自动同步。
        </Text>
        <Text className='vip-site'>{PC_SITE}</Text>
        <Button className='vip-copy-btn' onClick={copySite}>复制官网地址</Button>
      </View>

      <View className='vip-benefits'>
        <Text className='vip-benefits-title'>会员权益</Text>
        {VIP_FEATURES.map((item) => (
          <View className='vip-benefit-row' key={item}>
            <Text className='vip-benefit-dot'>✓</Text>
            <Text className='vip-benefit-text'>{item}</Text>
          </View>
        ))}
      </View>

      <View className='vip-steps'>
        <Text className='vip-steps-title'>PC 端开通步骤</Text>
        <Text className='vip-step'>1. 电脑浏览器打开 {PC_SITE}</Text>
        <Text className='vip-step'>2. 使用与本小程序相同的账号登录</Text>
        <Text className='vip-step'>3. 进入「权限中心」选择套餐并完成支付</Text>
        <Text className='vip-step'>4. 回到小程序下拉刷新或重新进入即可</Text>
      </View>

      <Text className='vip-disclaimer'>
        本平台仅提供公开市场统计数据查询，不构成投资建议，不提供荐股、代客理财及证券交易服务。
      </Text>
    </View>
  )
}
