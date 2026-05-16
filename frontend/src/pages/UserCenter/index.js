// frontend/src/pages/UserCenter/index.js
import React, { useState, useEffect } from 'react';
import { Table, Button, Form, Input, message, Tag, Pagination } from 'antd';
import { useAuth } from '../../context/AuthContext';
import { getOrders, changePassword } from '../../services/auth';
import './index.css';

const STATUS_MAP = {
  pending: { color: 'orange', text: '未支付' },
  paid: { color: 'green', text: '支付完成' },
};

export default function UserCenter() {
  const { user, isVip, expireTime } = useAuth();
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pwdLoading, setPwdLoading] = useState(false);
  const [form] = Form.useForm();

  const fetchOrders = async (p) => {
    try {
      const res = await getOrders(p, 10);
      if (res.success) {
        setOrders(res.data.list);
        setTotal(res.data.total);
      }
    } catch {}
  };

  useEffect(() => {
    fetchOrders(page);
  }, [page]);

  const onChangePwd = async ({ old_password, new_password, confirm }) => {
    if (new_password !== confirm) {
      message.error('两次密码不一致');
      return;
    }
    setPwdLoading(true);
    try {
      const res = await changePassword(old_password, new_password);
      if (res.success) {
        message.success('密码修改成功');
        form.resetFields();
      } else {
        message.error(res.message || '修改失败');
      }
    } catch {
      message.error('网络错误');
    } finally {
      setPwdLoading(false);
    }
  };

  const columns = [
    { title: '权限名称', dataIndex: 'plan_name', key: 'plan_name' },
    {
      title: '单号',
      dataIndex: 'order_no',
      key: 'order_no',
      ellipsis: true,
      render: (v) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '额度',
      dataIndex: 'amount',
      key: 'amount',
      render: (v) => `¥${Number(v).toFixed(2)}`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s) => (
        <Tag color={STATUS_MAP[s]?.color}>{STATUS_MAP[s]?.text || s}</Tag>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
  ];

  return (
    <div className="user-center">
      <div className="info-card">
        <h3>用户信息</h3>
        <div className="info-row">
          <span className="info-label">用户名：</span>
          <span className="info-value">{user?.username}</span>
        </div>
        <div className="info-row">
          <span className="info-label">手机号：</span>
          <span className="info-value">{user?.phone || '未绑定'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">有效期：</span>
          <span className="info-value">
            {isVip ? (
              <span className="vip-badge">{expireTime}</span>
            ) : (
              <span className="no-vip">未开通VIP</span>
            )}
          </span>
        </div>
      </div>

      <div className="info-card">
        <h3>修改密码</h3>
        <Form
          form={form}
          onFinish={onChangePwd}
          layout="vertical"
          style={{ maxWidth: 360, margin: '0 auto' }}
        >
          <Form.Item
            name="old_password"
            rules={[{ required: true, message: '请输入旧密码' }]}
          >
            <Input.Password
              placeholder="旧密码"
              style={{
                background: '#2a2a3a',
                border: '1px solid #3a3a5c',
                color: '#fff',
              }}
            />
          </Form.Item>
          <Form.Item
            name="new_password"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '至少6位' },
            ]}
          >
            <Input.Password
              placeholder="新密码（至少6位）"
              style={{
                background: '#2a2a3a',
                border: '1px solid #3a3a5c',
                color: '#fff',
              }}
            />
          </Form.Item>
          <Form.Item
            name="confirm"
            rules={[{ required: true, message: '请确认新密码' }]}
          >
            <Input.Password
              placeholder="确认新密码"
              style={{
                background: '#2a2a3a',
                border: '1px solid #3a3a5c',
                color: '#fff',
              }}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={pwdLoading} block>
              确认修改
            </Button>
          </Form.Item>
        </Form>
      </div>

      <div className="info-card">
        <h3>订单列表</h3>
        <Table
          dataSource={orders}
          columns={columns}
          rowKey="id"
          pagination={false}
          style={{ background: 'transparent' }}
        />
        <div style={{ textAlign: 'right', marginTop: 12 }}>
          <Pagination
            current={page}
            total={total}
            pageSize={10}
            onChange={(p) => setPage(p)}
            showTotal={(t) => `共 ${t} 条`}
          />
        </div>
      </div>
    </div>
  );
}
