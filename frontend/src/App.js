import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout, Alert } from 'antd';
import { useAtom } from 'jotai';
import Home from './pages/Home';
import StockDashboard from './pages/StockDashboard';
import { errorAtom } from './store/atoms';

const { Content } = Layout;

function App() {
  const [error, setError] = useAtom(errorAtom);

  return (
    <Layout className="layout" style={{ minHeight: '100vh' }}>
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
          
          {/* 404页面 - 重定向到股票分析页面 */}
          <Route path="*" element={<Navigate to="/stock-dashboard" replace />} />
        </Routes>
      </Content>
    </Layout>
  );
}

export default App; 