import React from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Alert, Menu } from 'antd';
import { useAtom } from 'jotai';
import Home from './pages/Home';
import StockDashboard from './pages/StockDashboard';
import EmotionCycle from './pages/EmotionCycle';
import LimitUpEchelon from './pages/LimitUpEchelon';
import { errorAtom } from './store/atoms';

const { Content, Header } = Layout;

const navItems = [
  { key: '/stock-dashboard', label: '个股分析' },
  { key: '/limit-up-echelon', label: '涨停梯队' },
  { key: '/emotion-cycle', label: '情绪周期' },
];

function App() {
  const [error, setError] = useAtom(errorAtom);
  const navigate = useNavigate();
  const location = useLocation();

  const handleMenuClick = ({ key }) => {
    navigate(key);
  };

  return (
    <Layout className="layout" style={{ minHeight: '100vh' }}>
      <Header style={{ padding: 0, background: '#141213', borderBottom: '1px solid #2a2a2a' }}>
        <Menu
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={navItems}
          onClick={handleMenuClick}
          style={{
            background: '#141213',
            borderBottom: 'none',
            color: '#fff',
          }}
          theme="dark"
        />
      </Header>
      <Content>
        {error && (
          <Alert
            message="错误"
            description={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
            style={{
              position: 'fixed',
              top: 20,
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 9999,
              maxWidth: '600px'
            }}
          />
        )}

        <Routes>
          {/* 默认路由重定向到股票分析页面 */}
          <Route path="/" element={<Navigate to="/stock-dashboard" replace />} />

          {/* 首页路由 */}
          <Route path="/home" element={<Home />} />

          {/* 股票分析页面路由 */}
          <Route path="/stock-dashboard" element={<StockDashboard />} />

          {/* 涨停梯队页面路由 */}
          <Route path="/limit-up-echelon" element={<LimitUpEchelon />} />

          {/* 情绪周期页面路由 */}
          <Route path="/emotion-cycle" element={<EmotionCycle />} />

          {/* 404页面 - 重定向到股票分析页面 */}
          <Route path="*" element={<Navigate to="/stock-dashboard" replace />} />
        </Routes>
      </Content>
    </Layout>
  );
}

export default App; 