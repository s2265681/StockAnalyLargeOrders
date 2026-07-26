import { useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Input, Button } from '@tarojs/components'
import { register } from '../../services/auth'
import './index.scss'

export default function Register() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [phone, setPhone] = useState('')
  const [loading, setLoading] = useState(false)

  const handleRegister = async () => {
    if (!username.trim() || username.trim().length < 2) {
      Taro.showToast({ title: '用户名至少2个字符', icon: 'none' })
      return
    }
    if (!password || password.length < 6) {
      Taro.showToast({ title: '密码至少6个字符', icon: 'none' })
      return
    }
    if (password !== confirmPwd) {
      Taro.showToast({ title: '两次密码不一致', icon: 'none' })
      return
    }
    setLoading(true)
    try {
      const result = await register(username.trim(), password, phone.trim() || undefined)
      if (result.success) {
        Taro.showToast({ title: '注册成功', icon: 'success' })
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
        <Text className='auth-title'>创建账号</Text>
        <Text className='auth-subtitle'>加入 重阳市场看板助手，开启智能看盘之旅</Text>
        <Input
          className='auth-input'
          placeholder='用户名（2-20个字符）'
          value={username}
          onInput={e => setUsername(e.detail.value)}
        />
        <Input
          className='auth-input'
          password
          placeholder='密码（至少6个字符）'
          value={password}
          onInput={e => setPassword(e.detail.value)}
        />
        <Input
          className='auth-input'
          password
          placeholder='确认密码'
          value={confirmPwd}
          onInput={e => setConfirmPwd(e.detail.value)}
        />
        <Input
          className='auth-input'
          type='number'
          placeholder='手机号（可选）'
          value={phone}
          onInput={e => setPhone(e.detail.value)}
        />
        <Button className='auth-btn' loading={loading} onClick={handleRegister}>
          注册
        </Button>
        <View
          className='auth-link'
          onClick={() => Taro.navigateBack().catch(() => Taro.reLaunch({ url: '/pages/login/index' }))}
        >
          已有账号？去登录
        </View>
      </View>
    </View>
  )
}
