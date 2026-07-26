import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, Link, useLocation, useSearchParams } from 'react-router-dom';
import { Input, Button, message, Spin } from 'antd';
import { UserOutlined, LockOutlined, WechatOutlined } from '@ant-design/icons';
import { useAuth } from '../../context/AuthContext';
import AuthLayout from '../../components/AuthLayout';
import { getWechatQrcode } from '../../services/auth';

const WXLOGIN_SRC = 'https://res.wx.qq.com/connect/zh_CN/htmledition/js/wxLogin.js';
const QR_CONTAINER_ID = 'wx-qrcode-container';

function getPostLoginPath(location, searchParams) {
  const next = searchParams.get('next');
  if (next && next.startsWith('/') && !next.startsWith('//')) {
    return next;
  }
  const from = location.state?.from;
  if (from?.pathname) {
    const path = from.pathname + (from.search || '');
    if (path.startsWith('/') && !path.startsWith('//')) return path;
  }
  return '/stock-dashboard';
}

function loadWxLoginScript() {
  return new Promise((resolve, reject) => {
    if (window.WxLogin) return resolve(window.WxLogin);
    const existing = document.getElementById('wxlogin-sdk');
    if (existing) {
      existing.addEventListener('load', () => resolve(window.WxLogin));
      existing.addEventListener('error', reject);
      return;
    }
    const s = document.createElement('script');
    s.id = 'wxlogin-sdk';
    s.src = WXLOGIN_SRC;
    s.async = true;
    s.onload = () => resolve(window.WxLogin);
    s.onerror = reject;
    document.body.appendChild(s);
  });
}

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [wxLoading, setWxLoading] = useState(false);
  const [showQr, setShowQr] = useState(false);
  const passwordRef = useRef(null);
  const { user, loading: authLoading, login, loginWithTicket } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    if (!authLoading && user) {
      navigate(getPostLoginPath(location, searchParams), { replace: true });
    }
  }, [authLoading, user, location, searchParams, navigate]);

  const focusPassword = () => {
    passwordRef.current?.focus();
  };

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      return message.error('请输入用户名和密码');
    }

    setLoading(true);
    const result = await login(username.trim(), password);
    setLoading(false);

    if (result.success) {
      message.success('登录成功');
      navigate(getPostLoginPath(location, searchParams), { replace: true });
    } else {
      message.error(result.message);
    }
  };

  const finishWithTicket = useCallback(async (ticket) => {
    const res = await loginWithTicket(ticket);
    if (res.success) {
      message.success('登录成功');
      navigate(getPostLoginPath(location, searchParams), { replace: true });
    } else {
      message.error(res.message || '微信登录失败');
      setShowQr(false);
    }
  }, [loginWithTicket, navigate, location, searchParams]);

  // 监听内嵌回调页(iframe)通过 postMessage 回传的 ticket/error
  useEffect(() => {
    if (!showQr) return undefined;
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return;
      const data = event.data;
      if (!data || data.source !== 'wx-login-callback') return;
      if (data.ticket) {
        finishWithTicket(data.ticket);
      } else if (data.error) {
        message.error(data.error);
        setShowQr(false);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [showQr, finishWithTicket]);

  const handleWechatLogin = async () => {
    setWxLoading(true);
    try {
      const res = await getWechatQrcode();
      if (!res.success || !res.data?.app_id || !res.data?.redirect_uri) {
        message.error(res.message || '微信登录暂不可用');
        setWxLoading(false);
        return;
      }
      sessionStorage.setItem('wx_login_next', getPostLoginPath(location, searchParams));
      await loadWxLoginScript();
      setShowQr(true);
      // 等容器挂载后再渲染二维码
      setTimeout(() => {
        if (!window.WxLogin) {
          message.error('微信登录组件加载失败');
          setShowQr(false);
          setWxLoading(false);
          return;
        }
        /* eslint-disable no-new */
        new window.WxLogin({
          self_redirect: true,
          id: QR_CONTAINER_ID,
          appid: res.data.app_id,
          scope: 'snsapi_login',
          redirect_uri: encodeURIComponent(res.data.redirect_uri),
          state: res.data.state || '',
          style: 'black',
          href: '',
        });
        setWxLoading(false);
      }, 0);
    } catch {
      message.error('微信登录暂不可用');
      setShowQr(false);
      setWxLoading(false);
    }
  };

  return (
    <AuthLayout
      title="欢迎回来"
      subtitle="登录你的 AI炒股指南 账号"
      footer={<>没有账号？<Link to="/register">立即注册</Link></>}
    >
      <form
        className="auth-login-form"
        onSubmit={e => {
          e.preventDefault();
          handleLogin();
        }}
      >
        <Input
          prefix={<UserOutlined style={{ color: 'var(--auth-text3)' }} />}
          placeholder="用户名"
          value={username}
          onChange={e => setUsername(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.preventDefault();
              focusPassword();
            }
          }}
        />
        <Input.Password
          ref={passwordRef}
          prefix={<LockOutlined style={{ color: 'var(--auth-text3)' }} />}
          placeholder="密码"
          value={password}
          onChange={e => setPassword(e.target.value)}
        />
        <Button type="primary" htmlType="submit" loading={loading}>
          登录
        </Button>
      </form>

      <div className="auth-divider"><span>或</span></div>

      {showQr ? (
        <div className="wx-qr-wrap">
          <div id={QR_CONTAINER_ID} className="wx-qr-frame">
            <Spin />
          </div>
          <Button type="link" block onClick={() => setShowQr(false)}>
            使用账号密码登录
          </Button>
        </div>
      ) : (
        <Button
          block
          icon={<WechatOutlined style={{ color: '#07c160' }} />}
          loading={wxLoading}
          onClick={handleWechatLogin}
        >
          微信扫码登录
        </Button>
      )}
    </AuthLayout>
  );
}
