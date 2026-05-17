import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Input, Button, message } from 'antd';
import { useAuth } from '../../context/AuthContext';
import ThemeToggle, { useTheme } from '../../components/ThemeToggle';
import './index.css';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      return message.error('请输入用户名和密码');
    }

    setLoading(true);
    const result = await login(username.trim(), password);
    setLoading(false);

    if (result.success) {
      message.success('登录成功');
      navigate('/stock-dashboard');
    } else {
      message.error(result.message);
    }
  };

  return (
    <div className="login-container">
      <div className="auth-page-header">
        <div className="auth-logo" onClick={() => navigate('/')}>
          <svg width="28" height="28" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg">
            <circle cx="18" cy="18" r="17" fill="var(--gold-bg,#fffbeb)" stroke="var(--color-accent,#d97706)" strokeWidth="1.5"/>
            <path d="M18,10 L4,28 Q18,24 32,28 Z" fill="var(--color-accent,#d97706)" opacity="0.25"/>
            <rect x="14" y="13" width="8" height="14" rx="2" fill="var(--color-accent,#d97706)"/>
            <polygon points="11,13 25,13 23,7 13,7" fill="var(--color-accent2,#f59e0b)"/>
            <circle cx="18" cy="10" r="3.5" fill="#fff" opacity="0.95"/>
            <circle cx="18" cy="10" r="2" fill="var(--color-accent2,#f59e0b)"/>
          </svg>
          <span className="auth-logo-name">AI炒股指南</span>
        </div>
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
      </div>
      <div className="login-card">
        <div className="login-title">登录</div>
        <div className="login-subtitle">AI炒股指南</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Input
            placeholder="用户名"
            value={username}
            onChange={e => setUsername(e.target.value)}
            onPressEnter={handleLogin}
          />
          <Input.Password
            placeholder="密码"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onPressEnter={handleLogin}
          />
          <Button
            type="primary"
            className="login-btn"
            loading={loading}
            onClick={handleLogin}
          >
            登录
          </Button>
          <div className="login-footer">
            没有账号？<Link to="/register">立即注册</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
