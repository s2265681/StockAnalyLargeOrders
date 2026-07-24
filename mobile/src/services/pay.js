import Taro from '@tarojs/taro'
import { api } from '../config/api'

// 展示用套餐（与后端 services/order_service.py PLANS 对应）
export const PLANS = [
  { type: 'daily', name: '测试VIP 1分', amount: 0.01, days: 1 },
  { type: 'monthly', name: '月度VIP', amount: 380, days: 30 },
  { type: 'quarterly', name: '季度VIP', amount: 900, days: 90 },
  { type: 'semi', name: '半年VIP', amount: 1600, days: 180 },
  { type: 'annual', name: '年度VIP', amount: 2500, days: 365 },
]

async function createOrder(planType) {
  const res = await api.post('/api/orders/create', { plan_type: planType })
  if (!res || !res.success || !res.data) {
    throw new Error((res && res.message) || '创建订单失败')
  }
  return res.data.order_no
}

async function miniprogramPrepay(orderNo, code) {
  const res = await api.post('/api/orders/wechat-miniprogram-prepay', {
    order_no: orderNo,
    code,
  })
  if (!res || !res.success || !res.data || !res.data.pay_params) {
    throw new Error((res && res.message) || '发起支付失败')
  }
  return res.data.pay_params
}

async function getOrderStatus(orderNo) {
  const res = await api.get(`/api/orders/status?order_no=${encodeURIComponent(orderNo)}`)
  return res && res.data ? res.data.status : 'pending'
}

function wxLoginCode() {
  return new Promise((resolve, reject) => {
    Taro.login({
      success: (r) => (r.code ? resolve(r.code) : reject(new Error('微信登录失败'))),
      fail: () => reject(new Error('微信登录失败')),
    })
  })
}

function requestPayment(params) {
  return new Promise((resolve, reject) => {
    Taro.requestPayment({
      ...params,
      success: () => resolve(true),
      fail: (err) => reject(err),
    })
  })
}

/**
 * 完整小程序支付流程：下单 → 微信登录 → 预支付 → 拉起收银台 → 确认订单状态。
 * 返回 { success, paid, message }。
 */
export async function payPlan(planType) {
  try {
    const orderNo = await createOrder(planType)
    const code = await wxLoginCode()
    const payParams = await miniprogramPrepay(orderNo, code)
    try {
      await requestPayment(payParams)
    } catch (err) {
      // 用户取消或支付失败
      if (err && err.errMsg && err.errMsg.indexOf('cancel') >= 0) {
        return { success: false, paid: false, message: '已取消支付' }
      }
      return { success: false, paid: false, message: '支付失败' }
    }
    // 支付成功后确认后端订单（触发主动查单兜底）
    const status = await getOrderStatus(orderNo)
    return { success: true, paid: status === 'paid', message: '支付成功' }
  } catch (e) {
    return { success: false, paid: false, message: (e && e.message) || '支付异常' }
  }
}
