import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Input, Button, message } from 'antd';
import { useAuth } from '../../context/AuthContext';
import './index.css';

export default function Register() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleRegister = async () => {
    if (!username.trim() || username.trim().length < 2) {
      return message.error('用户名至少2个字符');
    }
    if (!password || password.length < 6) {
      return message.error('密码至少6个字符');
    }
    if (password !== confirmPwd) {
      return message.error('两次密码不一致');
    }

    setLoading(true);
    const result = await register(username.trim(), password, phone.trim() || undefined);
    setLoading(false);

    if (result.success) {
      message.success('注册成功');
      navigate('/stock-dashboard');
    } else {
      message.error(result.message);
    }
  };

  return (
    <div className="register-container">
      <div className="register-card">
        <div className="register-title">创建账号</div>
        <div className="register-subtitle">注册 NiuNiuNiu 股票分析平台</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Input
            placeholder="用户名（2-20个字符）"
            value={username}
            onChange={e => setUsername(e.target.value)}
            onPressEnter={handleRegister}
          />
          <Input.Password
            placeholder="密码（至少6个字符）"
            value={password}
            onChange={e => setPassword(e.target.value)}
          />
          <Input.Password
            placeholder="确认密码"
            value={confirmPwd}
            onChange={e => setConfirmPwd(e.target.value)}
          />
          <Input
            placeholder="手机号（可选）"
            value={phone}
            onChange={e => setPhone(e.target.value)}
            onPressEnter={handleRegister}
          />
          <Button
            type="primary"
            className="register-btn"
            loading={loading}
            onClick={handleRegister}
          >
            注册
          </Button>
          <div className="register-footer">
            已有账号？<Link to="/login">去登录</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
