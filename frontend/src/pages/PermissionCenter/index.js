import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Modal, message } from 'antd';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../config/api';
import './index.css';

const PLANS = [
  { key: 'monthly',   name: '月度VIP',  price: 380,   unit: '/月',  days: 30 },
  { key: 'quarterly', name: '季度VIP',  price: 900,   unit: '/季',  days: 90,  badge: '热门' },
  { key: 'semi',      name: '半年VIP',  price: 1600,  unit: '/半年', days: 180 },
  { key: 'annual',    name: '年度VIP',  price: 2500,  unit: '/年',  days: 365, badge: '最划算' },
];

export default function PermissionCenter() {
  const { user, isVip, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [selected, setSelected] = useState('quarterly');
  const [loading, setLoading] = useState(false);

  if (!user) {
    navigate('/login');
    return null;
  }

  const handlePurchase = async () => {
    setLoading(true);
    try {
      const createRes = await api.post('/api/orders/create', { plan_type: selected });
      if (!createRes.success) {
        message.error(createRes.message);
        setLoading(false);
        return;
      }

      const orderNo = createRes.data.order_no;

      Modal.confirm({
        title: '确认支付',
        content: `订单号: ${orderNo}\n套餐: ${createRes.data.plan_name}\n金额: ¥${createRes.data.amount}\n\n（测试环境：点击确认将模拟支付）`,
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
    } catch {
      message.error('操作失败');
    }
    setLoading(false);
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
            <div className="pc-plan-price">¥{plan.price}</div>
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
          立即开通
        </Button>
      </div>
    </div>
  );
}
