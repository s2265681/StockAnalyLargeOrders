import React, { useState, useRef, useEffect } from 'react';
import { useNavigate, Link, useLocation, useSearchParams } from 'react-router-dom';
import { Input, Button, message } from 'antd';
import { UserOutlined, LockOutlined, WechatOutlined } from '@ant-design/icons';
import { useAuth } from '../../context/AuthContext';
import AuthLayout from '../../components/AuthLayout';
import { getWechatQrcode } from '../../services/auth';

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

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [wxLoading, setWxLoading] = useState(false);
  const passwordRef = useRef(null);
  const { user, loading: authLoading, login } = useAuth();
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

  const handleWechatLogin = async () => {
    setWxLoading(true);
    try {
      const res = await getWechatQrcode();
      if (res.success && res.data?.authorize_url) {
        // 记录登录后目标路径，回调页读取后跳转
        sessionStorage.setItem('wx_login_next', getPostLoginPath(location, searchParams));
        window.location.href = res.data.authorize_url;
      } else {
        message.error(res.message || '微信登录暂不可用');
        setWxLoading(false);
      }
    } catch {
      message.error('微信登录暂不可用');
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

      <Button
        block
        icon={<WechatOutlined style={{ color: '#07c160' }} />}
        loading={wxLoading}
        onClick={handleWechatLogin}
      >
        微信扫码登录
      </Button>
    </AuthLayout>
  );
}
