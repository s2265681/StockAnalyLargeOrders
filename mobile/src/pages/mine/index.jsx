import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, Input, Button, ScrollView } from '@tarojs/components'
import { api } from '../../config/api'
import { ensureAuth, getUser, refreshUser, isVip, logout } from '../../services/auth'
import DrawerMenu from '../../components/DrawerMenu'
import './index.scss'

const emailValid = (e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e)

export default function Mine() {
  const [user, setUser] = useState(null)
  const [vip, setVip] = useState(false)
  const [email, setEmail] = useState('')
  const [emailSaving, setEmailSaving] = useState(false)
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [pwdSaving, setPwdSaving] = useState(false)
  const [orders, setOrders] = useState([])

  useDidShow(async () => {
    if (!ensureAuth()) return
    await refreshUser()
    const u = getUser()
    setUser(u)
    setVip(isVip())
    setEmail((u && u.default_email) || '')
    fetchOrders()
  })

  const fetchOrders = async () => {
    try {
      const res = await api.get('/api/orders?page=1&page_size=20')
      if (res && res.success) setOrders(res.data?.items || [])
    } catch (e) { /* ignore */ }
  }

  const handleSaveEmail = async () => {
    const e = email.trim()
    if (e && !emailValid(e)) {
      Taro.showToast({ title: '邮箱格式不正确', icon: 'none' })
      return
    }
    setEmailSaving(true)
    try {
      const res = await api.put('/api/user/profile', { default_email: e })
      if (res && res.success) {
        Taro.showToast({ title: res.message || '常用邮箱已保存', icon: 'success' })
        await refreshUser()
        setUser(getUser())
      } else {
        Taro.showToast({ title: (res && res.message) || '保存失败', icon: 'none' })
      }
    } catch (err) {
      Taro.showToast({ title: '保存失败', icon: 'none' })
    } finally {
      setEmailSaving(false)
    }
  }

  const handleChangePwd = async () => {
    if (!oldPwd || !newPwd) return Taro.showToast({ title: '请填写完整', icon: 'none' })
    if (newPwd.length < 6) return Taro.showToast({ title: '新密码至少6位', icon: 'none' })
    if (newPwd !== confirmPwd) return Taro.showToast({ title: '两次密码不一致', icon: 'none' })
    setPwdSaving(true)
    try {
      const res = await api.post('/api/auth/change-password', {
        old_password: oldPwd,
        new_password: newPwd,
      })
      if (res && res.success) {
        Taro.showToast({ title: '密码修改成功', icon: 'success' })
        setOldPwd(''); setNewPwd(''); setConfirmPwd('')
      } else {
        Taro.showToast({ title: (res && res.message) || '修改失败', icon: 'none' })
      }
    } catch (e) {
      Taro.showToast({ title: '修改失败', icon: 'none' })
    } finally {
      setPwdSaving(false)
    }
  }

  const handleLogout = () => {
    logout()
    Taro.reLaunch({ url: '/pages/login/index' })
  }

  return (
    <View className='mine-page'>
      <View className='mine-top'>
        <DrawerMenu />
        <Text className='mine-brand'>我的</Text>
        <View className='mine-top-spacer' />
      </View>

      <View className='mine-section'>
        <Text className='mine-section-title'>个人信息</Text>
        <View className='mine-row'>
          <Text className='mine-label'>用户名</Text>
          <Text className='mine-value'>{user?.username || '--'}</Text>
        </View>
        <View className='mine-row'>
          <Text className='mine-label'>手机号</Text>
          <Text className='mine-value'>{user?.phone || '未设置'}</Text>
        </View>
        <View className='mine-row'>
          <Text className='mine-label'>常用邮箱</Text>
          <Text className='mine-value'>{user?.default_email || '未设置'}</Text>
        </View>
        <View className='mine-row'>
          <Text className='mine-label'>VIP状态</Text>
          {vip && user?.vip ? (
            <Text className='mine-vip on'>VIP · 到期 {String(user.vip.end_time).slice(0, 10)}</Text>
          ) : (
            <Text className='mine-vip off'>未开通</Text>
          )}
        </View>
        <View className='mine-row'>
          <Text className='mine-label'>注册时间</Text>
          <Text className='mine-value'>{user?.created_at || '--'}</Text>
        </View>
        {!vip && (
          <Button className='mine-vip-btn' onClick={() => Taro.switchTab({ url: '/pages/membership/index' })}>
            开通 VIP
          </Button>
        )}
      </View>

      <View className='mine-section'>
        <Text className='mine-section-title'>常用邮箱</Text>
        <Text className='mine-section-desc'>用于条件预警等通知的默认收件地址</Text>
        <Input
          className='mine-input'
          placeholder='your@email.com'
          value={email}
          onInput={(e) => setEmail(e.detail.value)}
        />
        <Button className='mine-btn' loading={emailSaving} onClick={handleSaveEmail}>保存邮箱</Button>
      </View>

      <View className='mine-section'>
        <Text className='mine-section-title'>修改密码</Text>
        <Input className='mine-input' password placeholder='旧密码' value={oldPwd} onInput={(e) => setOldPwd(e.detail.value)} />
        <Input className='mine-input' password placeholder='新密码（至少6位）' value={newPwd} onInput={(e) => setNewPwd(e.detail.value)} />
        <Input className='mine-input' password placeholder='确认新密码' value={confirmPwd} onInput={(e) => setConfirmPwd(e.detail.value)} />
        <Button className='mine-btn' loading={pwdSaving} onClick={handleChangePwd}>确认修改</Button>
      </View>

      <View className='mine-section'>
        <Text className='mine-section-title'>订单记录</Text>
        {orders.length === 0 ? (
          <Text className='mine-empty'>暂无订单</Text>
        ) : (
          <ScrollView scrollY className='mine-orders'>
            {orders.map((o) => (
              <View className='mine-order' key={o.order_no}>
                <View className='mine-order-l'>
                  <Text className='mine-order-plan'>{o.plan_name}</Text>
                  <Text className='mine-order-no'>{o.order_no}</Text>
                </View>
                <View className='mine-order-r'>
                  <Text className='mine-order-amt'>¥{o.amount}</Text>
                  <Text className={`mine-order-status ${o.status === 'paid' ? 'paid' : 'pending'}`}>
                    {o.status === 'paid' ? '已支付' : '待支付'}
                  </Text>
                </View>
              </View>
            ))}
          </ScrollView>
        )}
      </View>

      <Button className='mine-logout' onClick={handleLogout}>退出登录</Button>
    </View>
  )
}
