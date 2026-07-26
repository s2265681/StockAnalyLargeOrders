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
    // 非 VIP：底层渲染 mock 预览数据，上层叠加半透明遮罩升级提示
    const preview = React.isValidElement(children)
      ? React.cloneElement(children, { preview: true })
      : children;

    return (
      <div style={{ position: 'relative', height: 'calc(100vh - 64px)', overflow: 'hidden' }}>
        <div style={{ height: '100%', pointerEvents: 'none', userSelect: 'none' }} aria-hidden>
          {preview}
        </div>
        <div style={{
          position: 'absolute', inset: 0, zIndex: 10,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0, 0, 0, 0.35)',
          backdropFilter: 'blur(3px)',
          WebkitBackdropFilter: 'blur(3px)',
        }}>
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            textAlign: 'center', padding: '32px 48px', borderRadius: 12,
            background: 'var(--bg-primary)', color: 'var(--text-primary)',
            border: '1px solid var(--border-secondary)',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.25)',
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
        </div>
      </div>
    );
  }

  return children;
}
