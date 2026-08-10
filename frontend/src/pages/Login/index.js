import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, Link, useLocation, useSearchParams } from 'react-router-dom';
import { Input, Button, message, Spin } from 'antd';
import { UserOutlined, LockOutlined, WechatOutlined } from '@ant-design/icons';
import { useAuth } from '../../context/AuthContext';
import AuthLayout from '../../components/AuthLayout';
import { getWechatQrcode } from '../../services/auth';

const WXLOGIN_SRC = 'https://res.wx.qq.com/connect/zh_CN/htmledition/js/wxLogin.js';
const QR_CONTAINER_ID = 'wx-qrcode-container';
const MOBILE_QUERY = '(max-width: 960px)';
const WX_LOGIN_CSS_HREF = 'data:text/css;base64,LmltcG93ZXJCb3ggLnRpdGxlIHsgZGlzcGxheTogbm9uZSAhaW1wb3J0YW50OyB9Ci5pbXBvd2VyQm94IC5pbmZvIHsgZGlzcGxheTogbm9uZSAhaW1wb3J0YW50OyB9Ci5pbXBvd2VyQm94IC5xcmNvZGUgeyB3aWR0aDogMjIwcHg7IG1hcmdpbi10b3A6IDA7IGJvcmRlcjogbm9uZTsgfQouaW1wb3dlckJveCB7IHdpZHRoOiAyMjBweDsgYm9yZGVyOiBub25lOyBtYXJnaW46IDAgYXV0bzsgfQouc3RhdHVzX2ljb24geyBkaXNwbGF5OiBub25lICFpbXBvcnRhbnQ7IH0KLmltcG93ZXJCb3ggLnN0YXR1cyB7IGRpc3BsYXk6IG5vbmUgIWltcG9ydGFudDsgfQo=';

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
  const [loginMode, setLoginMode] = useState('password');
  const [qrReady, setQrReady] = useState(false);
  const [qrError, setQrError] = useState('');
  const [wxAvailable, setWxAvailable] = useState(true);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(MOBILE_QUERY).matches,
  );
  const passwordRef = useRef(null);
  const { user, loading: authLoading, login, loginWithTicket } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY);
    const onChange = (e) => setIsMobile(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

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
    }
  }, [loginWithTicket, navigate, location, searchParams]);

  useEffect(() => {
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return;
      const data = event.data;
      if (!data || data.source !== 'wx-login-callback') return;
      if (data.ticket) {
        finishWithTicket(data.ticket);
      } else if (data.error) {
        message.error(data.error);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [finishWithTicket]);

  useEffect(() => {
    if (authLoading || user || loginMode !== 'wechat' || isMobile) return undefined;
    let cancelled = false;
    setQrReady(false);
    setQrError('');
    const container = document.getElementById(QR_CONTAINER_ID);
    if (container) container.innerHTML = '';

    (async () => {
      try {
        const res = await getWechatQrcode();
        if (cancelled) return;
        if (!res.success || !res.data?.app_id || !res.data?.redirect_uri) {
          setWxAvailable(false);
          setQrError(res.message || '微信登录暂不可用');
          return;
        }
        sessionStorage.setItem('wx_login_next', getPostLoginPath(location, searchParams));
        await loadWxLoginScript();
        if (cancelled) return;
        if (!window.WxLogin) {
          setQrError('微信登录组件加载失败');
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
          href: WX_LOGIN_CSS_HREF,
        });
        setQrReady(true);
      } catch {
        if (!cancelled) setQrError('微信登录暂不可用');
      }
    })();
    return () => { cancelled = true; };
  }, [authLoading, user, loginMode, isMobile, location, searchParams]);

  const qrAside = (
    <>
      <h3 className="auth-aside-title">微信扫码登录</h3>
      <div className="auth-aside-qr">
        <div id={QR_CONTAINER_ID} className="auth-aside-qr-slot" />
        {!qrReady && (
          <div className="auth-aside-qr-mask">
            {qrError ? <span className="auth-aside-qr-err">{qrError}</span> : <Spin />}
          </div>
        )}
      </div>
      <p className="auth-aside-hint">使用微信扫一扫登录<br />"AI炒股指南"</p>
    </>
  );

  if (loginMode === 'wechat' && !isMobile) {
    return (
      <AuthLayout
        aside={qrAside}
        onBack={() => setLoginMode('password')}
        wechatOnly
      />
    );
  }

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

      {!isMobile && wxAvailable && (
        <>
          <div className="auth-divider"><span>或</span></div>
          <Button
            block
            icon={<WechatOutlined style={{ color: '#07c160' }} />}
            onClick={() => setLoginMode('wechat')}
          >
            微信扫码登录
          </Button>
        </>
      )}
    </AuthLayout>
  );
}
