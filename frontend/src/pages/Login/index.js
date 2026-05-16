import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Input, Button, message } from 'antd';
import { useAuth } from '../../context/AuthContext';
import './index.css';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

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
      <div className="login-card">
        <div className="login-title">登录</div>
        <div className="login-subtitle">NiuNiuNiu 股票分析平台</div>
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
