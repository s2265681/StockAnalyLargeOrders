// frontend/src/pages/Login/index.js
import React, { useState, useEffect } from 'react';
import { Form, Input, Button, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) navigate('/stock-dashboard', { replace: true });
  }, [user, navigate]);

  const onFinish = async ({ username, password }) => {
    setLoading(true);
    try {
      const res = await login(username, password);
      if (res.success) {
        message.success('登录成功');
        navigate('/stock-dashboard', { replace: true });
      } else {
        message.error(res.message || '登录失败');
      }
    } catch (e) {
      message.error('网络错误，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#141213',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          background: '#1e1e2e',
          border: '1px solid #2a2a3a',
          borderRadius: 12,
          padding: '48px 40px',
          width: 380,
        }}
      >
        <h2
          style={{
            color: '#fff',
            textAlign: 'center',
            marginBottom: 32,
            fontSize: 22,
          }}
        >
          牛牛牛 · 登录
        </h2>
        <Form onFinish={onFinish} layout="vertical">
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              placeholder="用户名"
              size="large"
              style={{
                background: '#2a2a3a',
                border: '1px solid #3a3a5c',
                color: '#fff',
              }}
            />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              placeholder="密码"
              size="large"
              style={{
                background: '#2a2a3a',
                border: '1px solid #3a3a5c',
                color: '#fff',
              }}
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              size="large"
              loading={loading}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  );
}
