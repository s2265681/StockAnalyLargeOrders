import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { ensureAuth, refreshUser } from '../../services/auth'
import DrawerMenu from '../../components/DrawerMenu'
import MarketBriefBar from '../../components/MarketBriefBar'
import './index.scss'

const FEATURES = [
  { icon: '📈', label: '个股分析', desc: '分时·大单·资金流', url: '/pages/stock-dashboard/index' },
  { icon: '🔥', label: '涨停梯队', desc: '连板高度·封单质量', url: '/pages/limit-up-echelon/index' },
  { icon: '⚡', label: '核心游资', desc: '龙虎榜席位解读', url: '/pages/dragon-tiger/index' },
  { icon: '🎛️', label: '情绪周期', desc: '市场情绪温度', url: '/pages/emotion-cycle/index' },
  { icon: '🕐', label: '竞价异动', desc: '早盘·尾盘筛选', url: '/pages/auction-grab/index' },
  { icon: '🔲', label: '板块异动', desc: '强势板块个股', url: '/pages/sector-grab/index' },
  { icon: '🛡️', label: '权限中心', desc: '开通/续费VIP', url: '/pages/membership/index', tab: true },
]

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

      <View className='home-grid'>
        {FEATURES.map((item) => (
          <View className='home-cell' key={item.label} onClick={() => go(item)}>
            <Text className='home-cell-icon'>{item.icon}</Text>
            <Text className='home-cell-label'>{item.label}</Text>
            <Text className='home-cell-desc'>{item.desc}</Text>
          </View>
        ))}
      </View>
    </View>
  )
}
