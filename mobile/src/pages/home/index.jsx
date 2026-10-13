import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { ensureAuth, refreshUser } from '../../services/auth'
import DrawerMenu from '../../components/DrawerMenu'
import MarketBriefBar from '../../components/MarketBriefBar'
import { FEATURES } from '../../config/features'
import './index.scss'

export default function Home() {
  useDidShow(() => {
    if (!ensureAuth()) return
    refreshUser()
  })

  const go = (item) => {
    if (item.tab) {
      Taro.switchTab({ url: item.url })
    } else {
      Taro.navigateTo({ url: item.url })
    }
  }

  return (
    <View className='home-page'>
      <View className='home-top'>
        <DrawerMenu />
        <Text className='home-brand'>重阳市场看板助手</Text>
        <View className='home-top-spacer' />
      </View>

      <MarketBriefBar />

      <Text className='home-section-title'>数据模块</Text>
      <View className='home-grid'>
        {FEATURES.map((item) => (
          <View className='home-cell' key={item.label} onClick={() => go(item)}>
            <Text className='home-cell-icon'>{item.icon}</Text>
            <Text className='home-cell-label'>{item.label}</Text>
            <Text className='home-cell-desc'>{item.desc}</Text>
          </View>
        ))}
      </View>
      <Text className='home-disclaimer'>
        公开市场统计数据查询工具，不构成投资建议；小程序内不提供会员购买及个股实时走势。
      </Text>
    </View>
  )
}
