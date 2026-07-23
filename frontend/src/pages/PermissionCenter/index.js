import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Modal, message, Spin } from 'antd';
import { QRCodeSVG } from 'qrcode.react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../config/api';
import './index.css';

const TEST_PLANS = [
  { key: 'daily',  name: '测试VIP 1分', price: 0.01, unit: '/次', days: 1, badge: '测试' },
  { key: 'test2',  name: '测试VIP 2分', price: 0.02, unit: '/次', days: 1, badge: '测试' },
];

const PROD_PLANS = [
  { key: 'monthly',   name: '月度VIP',  price: 380,   unit: '/月',  days: 30 },
  { key: 'quarterly', name: '季度VIP',  price: 900,   unit: '/季',  days: 90,  badge: '热门' },
  { key: 'semi',      name: '半年VIP',  price: 1600,  unit: '/半年', days: 180 },
  { key: 'annual',    name: '年度VIP',  price: 2500,  unit: '/年',  days: 365, badge: '最划算' },
];

// 测试阶段默认只展示 1 分 / 2 分套餐；正式上线时把 REACT_APP_PAY_TEST 设为 false
const PAY_TEST_MODE = process.env.REACT_APP_PAY_TEST !== 'false';
const PLANS = PAY_TEST_MODE ? TEST_PLANS : [...TEST_PLANS, ...PROD_PLANS];

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

export default function PermissionCenter() {
  const { user, isVip, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [selected, setSelected] = useState('daily');
  const [loading, setLoading] = useState(false);
  const [wechatEnabled, setWechatEnabled] = useState(false);
  const [payModalOpen, setPayModalOpen] = useState(false);
  const [payInfo, setPayInfo] = useState(null);
  const [payPolling, setPayPolling] = useState(false);
  const pollTimerRef = useRef(null);
  const pollStartedRef = useRef(0);

  useEffect(() => {
    api.get('/api/orders/payment-config')
      .then((res) => {
        if (res.success) {
          setWechatEnabled(!!res.data?.wechat_enabled);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
    }
  }, []);

  if (!user) {
    navigate('/login');
    return null;
  }

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setPayPolling(false);
  };

  const startPolling = (orderNo) => {
    stopPolling();
    pollStartedRef.current = Date.now();
    setPayPolling(true);

    pollTimerRef.current = setInterval(async () => {
      if (Date.now() - pollStartedRef.current > POLL_TIMEOUT_MS) {
        stopPolling();
        message.warning('支付超时，请重新下单');
        setPayModalOpen(false);
        return;
      }

      try {
        const res = await api.get(`/api/orders/status?order_no=${encodeURIComponent(orderNo)}`);
        if (res.success && res.data?.status === 'paid') {
          stopPolling();
          setPayModalOpen(false);
          message.success('支付成功，VIP 已激活！');
          await refreshUser();
        }
      } catch {
        /* 轮询失败时继续重试 */
      }
    }, POLL_INTERVAL_MS);
  };

  const handleWechatPay = async (orderNo) => {
    const prepayRes = await api.post('/api/orders/wechat-prepay', { order_no: orderNo });
    if (!prepayRes.success) {
      message.error(prepayRes.message || '创建支付失败');
      return;
    }

    setPayInfo(prepayRes.data);
    setPayModalOpen(true);
    startPolling(orderNo);
  };

  const handleMockPay = (orderNo, planName, amount) => {
    Modal.confirm({
      title: '确认支付',
      content: `订单号: ${orderNo}\n套餐: ${planName}\n金额: ¥${amount}\n\n（测试环境：点击确认将模拟支付）`,
      okText: '确认支付',
      cancelText: '取消',
      onOk: async () => {
        const payRes = await api.post('/api/orders/mock-pay', { order_no: orderNo });
        if (payRes.success) {
          message.success('支付成功，VIP 已激活！');
          await refreshUser();
        } else {
          message.error(payRes.message);
        }
      },
    });
  };

  const handlePurchase = async () => {
    setLoading(true);
    try {
      const createRes = await api.post('/api/orders/create', { plan_type: selected });
      if (!createRes.success) {
        message.error(createRes.message);
        return;
      }

      const { order_no: orderNo, plan_name: planName, amount } = createRes.data;

      if (wechatEnabled) {
        await handleWechatPay(orderNo);
      } else {
        handleMockPay(orderNo, planName, amount);
      }
    } catch {
      message.error('操作失败');
    } finally {
      setLoading(false);
    }
  };

  const handleClosePayModal = () => {
    stopPolling();
    setPayModalOpen(false);
    setPayInfo(null);
  };

  return (
    <div className="permission-center-container">
      <div className="pc-title">开通 VIP</div>
      <div className="pc-subtitle">
        {isVip
          ? `当前 VIP 有效期至 ${user.vip?.end_time?.split(' ')[0]}，可续费延长`
          : '解锁情绪周期、竞价抢筹等高级分析功能'}
      </div>

      <div className="pc-plans">
        {PLANS.map(plan => (
          <div
            key={plan.key}
            className={`pc-plan-card ${selected === plan.key ? 'selected' : ''}`}
            onClick={() => setSelected(plan.key)}
          >
            <div className="pc-plan-name">{plan.name}</div>
            <div className="pc-plan-price">¥{plan.price < 1 ? plan.price.toFixed(2) : plan.price}</div>
            <div className="pc-plan-unit">{plan.days}天</div>
            {plan.badge && <span className="pc-plan-badge">{plan.badge}</span>}
          </div>
        ))}
      </div>

      <div style={{ textAlign: 'center', marginTop: 32 }}>
        <Button
          type="primary"
          size="large"
          loading={loading}
          onClick={handlePurchase}
          style={{ width: 200, height: 44, fontSize: 16 }}
        >
          {wechatEnabled ? '微信扫码支付' : '立即开通'}
        </Button>
        {wechatEnabled && (
          <div className="pc-pay-hint">请使用微信扫一扫完成支付</div>
        )}
      </div>

      <Modal
        title="微信扫码支付"
        open={payModalOpen}
        onCancel={handleClosePayModal}
        footer={[
          <Button key="close" onClick={handleClosePayModal}>
            关闭
          </Button>,
        ]}
        width={360}
        centered
        destroyOnClose
      >
        {payInfo ? (
          <div className="pc-pay-modal">
            <div className="pc-pay-amount">¥{payInfo.amount}</div>
            <div className="pc-pay-plan">{payInfo.plan_name}</div>
            <div className="pc-pay-qrcode">
              <QRCodeSVG value={payInfo.code_url} size={200} level="M" />
            </div>
            <div className="pc-pay-order">订单号：{payInfo.order_no}</div>
            <div className="pc-pay-status">
              {payPolling ? (
                <>
                  <Spin size="small" style={{ marginRight: 8 }} />
                  等待支付中，支付完成后将自动开通 VIP
                </>
              ) : (
                '支付状态查询已停止'
              )}
            </div>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        )}
      </Modal>
    </div>
  );
}
