import Taro from '@tarojs/taro'
import { api, setToken, removeToken, getToken } from '../config/api'

// 轻量鉴权：无 React Context，用模块级缓存 + Taro storage。
// 页面通过 ensureAuth() 守卫，通过 getUser()/refreshUser() 取用户。

let _user = null

export const isLoggedIn = () => !!getToken()

export async function login(username, password) {
  const res = await api.post('/api/auth/login', { username, password })
  if (res && res.success && res.data && res.data.token) {
    setToken(res.data.token)
    await refreshUser()
    return { success: true }
  }
  return { success: false, message: (res && res.message) || '登录失败' }
}

export async function register(username, password, phone) {
  const res = await api.post('/api/auth/register', { username, password, phone })
  if (res && res.success && res.data && res.data.token) {
    setToken(res.data.token)
    await refreshUser()
    return { success: true }
  }
  return { success: false, message: (res && res.message) || '注册失败' }
}

export function logout() {
  removeToken()
  _user = null
}

export function getUser() {
  return _user
}

export async function refreshUser() {
  if (!getToken()) {
    _user = null
    return null
  }
  try {
    const res = await api.get('/api/user/profile')
    if (res && res.success && res.data) {
      _user = res.data
      return _user
    }
  } catch (e) {
    // token 失效
  }
  removeToken()
  _user = null
  return null
}

export function isVip() {
  const end = _user && _user.vip && _user.vip.end_time
  return !!(end && new Date(end) > new Date())
}

/** 页面 onShow 里调用：未登录则跳登录页。返回是否已登录。 */
export function ensureAuth() {
  if (!isLoggedIn()) {
    Taro.reLaunch({ url: '/pages/login/index' })
    return false
  }
  return true
}
