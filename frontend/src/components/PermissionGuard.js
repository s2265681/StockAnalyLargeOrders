import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from 'antd';
import { useAuth } from '../context/AuthContext';

export default function PermissionGuard({ children }) {
  const { user, isVip } = useAuth();
  const navigate = useNavigate();

  if (!user) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: 'calc(100vh - 64px)',
        background: 'var(--bg-primary)', color: 'var(--text-primary)',
      }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔒</div>
        <div style={{ fontSize: 18, marginBottom: 8 }}>请先登录</div>
        <div style={{ color: 'var(--text-muted)', marginBottom: 24 }}>登录后即可使用此功能</div>
        <Button type="primary" onClick={() => navigate('/login')}>去登录</Button>
      </div>
    );
  }

  if (!isVip) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: 'calc(100vh - 64px)',
        background: 'var(--bg-primary)', color: 'var(--text-primary)',
      }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔒</div>
        <div style={{ fontSize: 18, marginBottom: 8 }}>此功能需要 VIP 权限</div>
        <div style={{ color: 'var(--text-muted)', marginBottom: 24 }}>
          开通 VIP 后即可解锁全部分析功能
        </div>
        <Button type="primary" onClick={() => navigate('/permission-center')}>
          立即开通
        </Button>
      </div>
    );
  }

  return children;
}
