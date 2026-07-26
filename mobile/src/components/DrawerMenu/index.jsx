import { useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { getUser, logout } from '../../services/auth'
import './index.scss'

const MENU_ITEMS = [
  { icon: '📈', label: '个股分析', url: '/pages/stock-dashboard/index' },
  { icon: '🔥', label: '涨停梯队', url: '/pages/limit-up-echelon/index' },
  { icon: '⚡', label: '核心游资', url: '/pages/dragon-tiger/index' },
  { icon: '🎛️', label: '情绪周期', url: '/pages/emotion-cycle/index' },
  { icon: '🕐', label: '竞价异动', url: '/pages/auction-grab/index' },
  { icon: '🔲', label: '板块异动', url: '/pages/sector-grab/index' },
  { icon: '🛡️', label: '权限中心', url: '/pages/membership/index', tab: true },
]

export default function DrawerMenu() {
  const [open, setOpen] = useState(false)
  const user = getUser()

  const go = (item) => {
    setOpen(false)
    if (item.tab) {
      Taro.switchTab({ url: item.url })
    } else {
      Taro.navigateTo({ url: item.url })
    }
  }

  const goMine = () => {
    setOpen(false)
    Taro.switchTab({ url: '/pages/mine/index' })
  }

  const handleLogout = () => {
    logout()
    setOpen(false)
    Taro.reLaunch({ url: '/pages/login/index' })
  }

  return (
    <View className='drawer'>
      <View className='drawer-trigger' onClick={() => setOpen(true)}>
        <View className='drawer-trigger-bar' />
        <View className='drawer-trigger-bar' />
        <View className='drawer-trigger-bar' />
      </View>

      {open && (
        <View className='drawer-mask' onClick={() => setOpen(false)}>
          <View className='drawer-panel' onClick={(e) => e.stopPropagation()}>
            <View className='drawer-head'>
              <Text className='drawer-logo'>重阳市场看板助手</Text>
              <Text className='drawer-close' onClick={() => setOpen(false)}>✕</Text>
            </View>

            <View className='drawer-list'>
              {MENU_ITEMS.map((item) => (
                <View className='drawer-item' key={item.label} onClick={() => go(item)}>
                  <Text className='drawer-item-icon'>{item.icon}</Text>
                  <Text className='drawer-item-label'>{item.label}</Text>
                </View>
              ))}
            </View>

            <View className='drawer-foot'>
              <View className='drawer-item drawer-item-user' onClick={goMine}>
                <Text className='drawer-item-icon'>👤</Text>
                <Text className='drawer-item-label'>
                  个人中心{user && user.username ? `（${user.username}）` : ''}
                </Text>
              </View>
              {user && (
                <View className='drawer-item drawer-item-logout' onClick={handleLogout}>
                  <Text className='drawer-item-icon'>⏻</Text>
                  <Text className='drawer-item-label'>退出登录</Text>
                </View>
              )}
            </View>
          </View>
        </View>
      )}
    </View>
  )
}
