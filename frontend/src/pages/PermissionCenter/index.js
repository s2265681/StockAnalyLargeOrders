// frontend/src/pages/PermissionCenter/index.js
import React, { useState } from 'react';
import { Button, Modal, message } from 'antd';
import { useAuth } from '../../context/AuthContext';
import { createOrder, mockPay } from '../../services/auth';
import './index.css';

const PLANS = [
  { key: 'monthly',   name: '月度VIP',  price: '¥380/月',    amount: 380 },
  { key: 'quarterly', name: '季度VIP',  price: '¥900/季',    amount: 900 },
  { key: 'semi',      name: '半年VIP',  price: '¥1600/半年', amount: 1600 },
  { key: 'annual',    name: '年度VIP',  price: '¥2500/年',   amount: 2500 },
];

const FEATURES = ['level2大单数据', '情绪周期', '竞价抢筹', '板块抢筹', '风险预警'];

export default function PermissionCenter() {
  const { refreshUser } = useAuth();
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [qrVisible, setQrVisible] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [currentOrder, setCurrentOrder] = useState(null);
  const [loading, setLoading] = useState(false);

  const onBuy = (plan) => {
    setSelectedPlan(plan);
    setConfirmVisible(true);
  };

  const onConfirm = async () => {
    setLoading(true);
    try {
      const res = await createOrder(selectedPlan.key);
      if (res.success) {
        setCurrentOrder(res.data);
        setConfirmVisible(false);
        setQrVisible(true);
      } else {
        message.error(res.message || '创建订单失败');
      }
    } catch {
      message.error('网络错误');
    } finally {
      setLoading(false);
    }
  };

  const onMockPay = async () => {
    if (!currentOrder) return;
    setLoading(true);
    try {
      const res = await mockPay(currentOrder.order_no);
      if (res.success) {
        message.success(res.message || '支付成功！');
        setQrVisible(false);
        await refreshUser();
      } else {
        message.error(res.message || '支付失败');
      }
    } catch {
      message.error('网络错误');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="permission-center">
      <h2>权限中心</h2>
      <div className="plans-grid">
        {PLANS.map((plan, i) => (
          <div key={plan.key} className={`plan-card${i === 0 ? ' highlight' : ''}`}>
            <div className="plan-name">{plan.name}</div>
            <div className="plan-price">{plan.price}</div>
            <ul className="plan-features">
              {FEATURES.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <Button type="primary" block size="large" onClick={() => onBuy(plan)}>
              立即开通
            </Button>
          </div>
        ))}
      </div>

      {/* 确认购买弹窗 */}
      <Modal
        title="确认购买"
        open={confirmVisible}
        onCancel={() => setConfirmVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setConfirmVisible(false)}>
            取消
          </Button>,
          <Button
            key="confirm"
            type="primary"
            loading={loading}
            onClick={onConfirm}
          >
            确认购买
          </Button>,
        ]}
      >
        {selectedPlan && (
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <div style={{ color: '#888', marginBottom: 8 }}>
              您选择的是 {selectedPlan.name}
            </div>
            <div style={{ color: '#1677ff', fontSize: 22, fontWeight: 700 }}>
              价格：{selectedPlan.price}
            </div>
          </div>
        )}
      </Modal>

      {/* 微信支付弹窗 */}
      <Modal
        title="微信支付"
        open={qrVisible}
        onCancel={() => setQrVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setQrVisible(false)}>
            取消
          </Button>,
          <Button
            key="pay"
            type="primary"
            loading={loading}
            onClick={onMockPay}
          >
            已完成支付
          </Button>,
        ]}
      >
        {currentOrder && (
          <div className="qr-modal-content">
            <img
              src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=wechat-pay-${currentOrder.order_no}`}
              alt="微信支付二维码"
            />
            <div className="qr-price">
              ¥{Number(currentOrder.amount).toFixed(2)} / {selectedPlan?.name}
            </div>
            <div className="qr-hint">请使用微信扫码支付</div>
          </div>
        )}
      </Modal>
    </div>
  );
}
