import Taro from '@tarojs/taro'

// 生产：小程序端直连线上域名；H5 端同源走 Nginx 反代（BASE 为空）。
// 通过 TARO_ENV 区分：weapp 必须带域名（且需在小程序后台配置 request 合法域名）。
const PROD_WEAPP_BASE = 'https://www.stockai.xin'

function resolveBase() {
  if (process.env.NODE_ENV !== 'production') {
    // 本地调试：H5 直接打到后端；小程序调试需勾选「不校验合法域名」
    return 'http://localhost:9001'
  }
  return process.env.TARO_ENV === 'h5' ? '' : PROD_WEAPP_BASE
}

const BASE = resolveBase()
const TOKEN_KEY = 'niuniu_token'

export const getToken = () => {
  try {
    return Taro.getStorageSync(TOKEN_KEY) || ''
  } catch (e) {
    return ''
  }
}
export const setToken = (token) => Taro.setStorageSync(TOKEN_KEY, token)
export const removeToken = () => Taro.removeStorageSync(TOKEN_KEY)

/**
 * 统一请求封装。后端返回 { success, data, message } 结构，直接透传 res.data。
 * 非 2xx 抛错，供调用方 catch。
 */
export async function request(path, { method = 'GET', data, header } = {}) {
  const token = getToken()
  const res = await Taro.request({
    url: `${BASE}${path}`,
    method,
    data,
    timeout: 45000,
    header: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...header,
    },
  })
  if (res.statusCode < 200 || res.statusCode >= 300) {
    const err = new Error(`HTTP ${res.statusCode}`)
    err.status = res.statusCode
    err.body = res.data
    throw err
  }
  return res.data
}

export const api = {
  get: (path, opts = {}) => request(path, { method: 'GET', ...opts }),
  post: (path, data, opts = {}) => request(path, { method: 'POST', data, ...opts }),
  put: (path, data, opts = {}) => request(path, { method: 'PUT', data, ...opts }),
  del: (path, opts = {}) => request(path, { method: 'DELETE', ...opts }),
}

export { BASE }
