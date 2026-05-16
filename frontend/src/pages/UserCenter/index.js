import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input, Button, message, Spin } from 'antd';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../config/api';
import './index.css';

export default function UserCenter() {
  const { user, isVip, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [oldPwd, setOldPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [pwdLoading, setPwdLoading] = useState(false);
  const [orders, setOrders] = useState([]);
  const [ordersLoading, setOrdersLoading] = useState(false);

  useEffect(() => {
    if (!user) {
      navigate('/login');
      return;
    }
    fetchOrders();
  }, [user, navigate]);

  const fetchOrders = async () => {
    setOrdersLoading(true);
    try {
      const res = await api.get('/api/orders?page=1&page_size=20');
      if (res.success) {
        setOrders(res.data?.items || []);
      }
    } catch { /* ignore */ }
    setOrdersLoading(false);
  };

  const handleChangePwd = async () => {
    if (!oldPwd || !newPwd) return message.error('请填写完整');
    if (newPwd.length < 6) return message.error('新密码至少6个字符');
    if (newPwd !== confirmPwd) return message.error('两次密码不一致');

    setPwdLoading(true);
    try {
      const res = await api.post('/api/auth/change-password', {
        old_password: oldPwd,
        new_password: newPwd,
      });
      if (res.success) {
        message.success('密码修改成功');
        setOldPwd(''); setNewPwd(''); setConfirmPwd('');
      } else {
        message.error(res.message);
      }
    } catch {
      message.error('修改失败');
    }
    setPwdLoading(false);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  if (!user) return null;

  return (
    <div className="user-center-container">
      <div className="uc-section">
        <div className="uc-section-title">个人信息</div>
        <div className="uc-info-row">
          <span className="uc-info-label">用户名</span>
          <span className="uc-info-value">{user.username}</span>
        </div>
        <div className="uc-info-row">
          <span className="uc-info-label">手机号</span>
          <span className="uc-info-value">{user.phone || '未设置'}</span>
        </div>
        <div className="uc-info-row">
          <span className="uc-info-label">VIP 状态</span>
          <span className="uc-info-value">
            {isVip ? (
              <span className="uc-vip-badge uc-vip-active">
                VIP · 到期 {user.vip.end_time?.split(' ')[0]}
              </span>
            ) : (
              <span className="uc-vip-badge uc-vip-inactive">未开通</span>
            )}
          </span>
        </div>
        <div className="uc-info-row">
          <span className="uc-info-label">注册时间</span>
          <span className="uc-info-value">{user.created_at}</span>
        </div>
        <div style={{ marginTop: 16 }}>
          <Button danger onClick={handleLogout}>退出登录</Button>
        </div>
      </div>

      <div className="uc-section">
        <div className="uc-section-title">修改密码</div>
        <div className="uc-pwd-form">
          <Input.Password placeholder="旧密码" value={oldPwd} onChange={e => setOldPwd(e.target.value)} />
          <Input.Password placeholder="新密码（至少6位）" value={newPwd} onChange={e => setNewPwd(e.target.value)} />
          <Input.Password placeholder="确认新密码" value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)} />
          <Button type="primary" loading={pwdLoading} onClick={handleChangePwd} style={{ width: 120 }}>
            确认修改
          </Button>
        </div>
      </div>

      <div className="uc-section">
        <div className="uc-section-title">订单记录</div>
        {ordersLoading ? (
          <Spin />
        ) : orders.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 24 }}>暂无订单</div>
        ) : (
          orders.map(o => (
            <div key={o.order_no} className="uc-order-item">
              <div>
                <div style={{ color: 'var(--text-primary)' }}>{o.plan_name}</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{o.order_no}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: 'var(--text-primary)' }}>¥{o.amount}</div>
                <div className={o.status === 'paid' ? 'uc-order-status-paid' : 'uc-order-status-pending'}>
                  {o.status === 'paid' ? '已支付' : '待支付'}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
