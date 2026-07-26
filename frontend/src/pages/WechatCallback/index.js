import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Spin, Button } from 'antd';
import { useAuth } from '../../context/AuthContext';
import AuthLayout from '../../components/AuthLayout';

const ERROR_TEXT = {
  denied: '你取消了微信授权',
  invalid_state: '登录会话已过期，请重新扫码',
  exchange_failed: '微信授权校验失败，请重试',
  user_failed: '创建账号失败，请稍后重试',
  not_configured: '微信登录暂未开放',
  exchange: '登录凭证无效或已过期，请重新登录',
};

export default function WechatCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { loginWithTicket } = useAuth();
  const [error, setError] = useState('');
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const err = searchParams.get('error');
    const ticket = searchParams.get('ticket');

    // 内嵌二维码场景：本页运行在 WxLogin 的 iframe 内，把结果回传父窗口，由父窗口完成登录
    const inIframe = window.top !== window.self;
    if (inIframe && window.parent) {
      if (err) {
        window.parent.postMessage(
          { source: 'wx-login-callback', error: ERROR_TEXT[err] || '微信登录失败' },
          window.location.origin
        );
      } else if (ticket) {
        window.parent.postMessage(
          { source: 'wx-login-callback', ticket },
          window.location.origin
        );
      } else {
        window.parent.postMessage(
          { source: 'wx-login-callback', error: '缺少登录凭证' },
          window.location.origin
        );
      }
      return;
    }

    if (err) {
      setError(ERROR_TEXT[err] || '微信登录失败');
      return;
    }

    if (!ticket) {
      setError('缺少登录凭证');
      return;
    }

    loginWithTicket(ticket).then((res) => {
      if (res.success) {
        const next = sessionStorage.getItem('wx_login_next') || '/stock-dashboard';
        sessionStorage.removeItem('wx_login_next');
        navigate(next, { replace: true });
      } else {
        setError(res.message || '微信登录失败');
      }
    });
  }, [searchParams, loginWithTicket, navigate]);

  return (
    <AuthLayout
      title="微信登录"
      subtitle={error ? '登录未完成' : '正在完成登录...'}
    >
      <div style={{ textAlign: 'center', padding: '12px 0' }}>
        {error ? (
          <>
            <p style={{ color: 'var(--auth-text2)', marginBottom: 20 }}>{error}</p>
            <Button type="primary" block onClick={() => navigate('/login', { replace: true })}>
              返回登录
            </Button>
          </>
        ) : (
          <Spin size="large" />
        )}
      </div>
    </AuthLayout>
  );
}
