// frontend/src/components/PermissionGuard.js
import React from 'react';
import { Button } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * 权限遮罩：非VIP用户显示升级提示，覆盖在children上
 * 用法：<PermissionGuard><YourComponent /></PermissionGuard>
 */
export default function PermissionGuard({ children }) {
  const { isVip, user, loading } = useAuth();
  const navigate = useNavigate();

  if (loading) return null;
  if (!user) {
    navigate('/login');
    return null;
  }
  if (isVip) return children;

  return (
    <div style={{ position: 'relative', minHeight: 400 }}>
      <div
        style={{
          filter: 'blur(4px)',
          pointerEvents: 'none',
          userSelect: 'none',
          maxHeight: 400,
          overflow: 'hidden',
        }}
      >
        {children}
      </div>
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(20,18,19,0.75)',
        }}
      >
        <div
          style={{
            background: '#1e1e2e',
            border: '1px solid #3a3a5c',
            borderRadius: 12,
            padding: '32px 48px',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 12 }}>🔒</div>
          <div
            style={{ color: '#fff', fontSize: 18, fontWeight: 600, marginBottom: 8 }}
          >
            此功能需要VIP权限
          </div>
          <div style={{ color: '#aaa', fontSize: 14, marginBottom: 20 }}>
            升级权限后解锁全部分析功能
          </div>
          <Button
            type="primary"
            size="large"
            onClick={() => navigate('/permission-center')}
          >
            立即升级
          </Button>
        </div>
      </div>
    </div>
  );
}
