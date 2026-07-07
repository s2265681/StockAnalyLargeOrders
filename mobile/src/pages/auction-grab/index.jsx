import { useDidShow } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { ensureAuth } from '../../services/auth'
import './index.scss'

export default function AuctionGrab() {
  useDidShow(() => {
    ensureAuth()
  })

  return (
    <View className='page-wrap'>
      <View className='placeholder-card'>
        <Text className='placeholder-title'>竞价抢筹</Text>
        <Text className='placeholder-sub'>功能迁移中，敬请期待</Text>
      </View>
    </View>
  )
}
