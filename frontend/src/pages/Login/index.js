import React, { useState, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Input, Button, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useAuth } from '../../context/AuthContext';
import AuthLayout from '../../components/AuthLayout';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const passwordRef = useRef(null);
  const { login } = useAuth();
  const navigate = useNavigate();

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
      navigate('/stock-dashboard');
    } else {
      message.error(result.message);
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
    </AuthLayout>
  );
}
