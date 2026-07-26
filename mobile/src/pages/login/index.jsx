import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, Input, Button } from '@tarojs/components'
import { login, isLoggedIn } from '../../services/auth'
import './index.scss'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  useDidShow(() => {
    if (isLoggedIn()) {
      Taro.reLaunch({ url: '/pages/stock-dashboard/index' })
    }
  })

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      Taro.showToast({ title: '请输入用户名和密码', icon: 'none' })
      return
    }
    setLoading(true)
    try {
      const result = await login(username.trim(), password)
      if (result.success) {
        Taro.showToast({ title: '登录成功', icon: 'success' })
        Taro.reLaunch({ url: '/pages/stock-dashboard/index' })
      } else {
        Taro.showToast({ title: result.message, icon: 'none' })
      }
    } catch (e) {
      Taro.showToast({ title: '网络异常，请重试', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className='auth-page'>
      <View className='auth-card'>
        <Text className='auth-title'>欢迎回来</Text>
        <Text className='auth-subtitle'>登录你的 重阳市场看板助手 账号</Text>
        <Input
          className='auth-input'
          placeholder='用户名'
          value={username}
          onInput={e => setUsername(e.detail.value)}
        />
        <Input
          className='auth-input'
          password
          placeholder='密码'
          value={password}
          onInput={e => setPassword(e.detail.value)}
        />
        <Button className='auth-btn' loading={loading} onClick={handleLogin}>
          登录
        </Button>
        <View
          className='auth-link'
          onClick={() => Taro.navigateTo({ url: '/pages/register/index' })}
        >
          没有账号？立即注册
        </View>
      </View>
    </View>
  )
}
