// frontend/src/App.js
import React from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Alert, Menu, Button } from 'antd';
import { useAtom } from 'jotai';
import Home from './pages/Home';
import StockDashboard from './pages/StockDashboard';
import EmotionCycle from './pages/EmotionCycle';
import LimitUpEchelon from './pages/LimitUpEchelon';
import AuctionGrab from './pages/AuctionGrab';
import DragonTiger from './pages/DragonTiger';
import AiDiagnosis from './pages/AiDiagnosis';
import Login from './pages/Login';
import Register from './pages/Register';
import UserCenter from './pages/UserCenter';
import PermissionCenter from './pages/PermissionCenter';
import PermissionGuard from './components/PermissionGuard';
import ThemeToggle, { useTheme } from './components/ThemeToggle';
import { useAuth } from './context/AuthContext';
import { errorAtom } from './store/atoms';

const { Content, Header } = Layout;

const NAV_ITEMS = [
  { key: '/stock-dashboard', label: '个股分析' },
  { key: '/ai-diagnosis', label: 'AI诊股' },
  { key: '/limit-up-echelon', label: '涨停梯队' },
  { key: '/dragon-tiger', label: '核心游资' },
  { key: '/emotion-cycle', label: '情绪周期' },
  { key: '/auction-grab', label: '竞价抢筹' },
  { key: '/permission-center', label: '权限中心' },
];

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

function AppInner() {
  const [error, setError] = useAtom(errorAtom);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const handleMenuClick = ({ key }) => navigate(key);
  const isAuthPage = location.pathname === '/login' || location.pathname === '/register';

  return (
    <Layout className="layout" style={{ minHeight: '100vh' }}>
      {!isAuthPage && (
        <Header
          style={{
            padding: 0,
            background: 'var(--bg-header)',
            borderBottom: '1px solid var(--border-secondary)',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Menu
            mode="horizontal"
            selectedKeys={[location.pathname]}
            items={NAV_ITEMS}
            onClick={handleMenuClick}
            style={{
              background: 'transparent',
              borderBottom: 'none',
              flex: 1,
              minWidth: 0,
            }}
            theme={theme === 'dark' ? 'dark' : 'light'}
          />
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              paddingRight: 16,
              gap: 8,
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
            {user ? (
              <>
                <span
                  style={{ color: 'var(--color-accent)', cursor: 'pointer', fontSize: 14 }}
                  onClick={() => navigate('/user-center')}
                >
                  {user.username}
                </span>
                <Button
                  type="text"
                  size="small"
                  style={{ color: 'var(--text-muted)' }}
                  onClick={async () => {
                    await logout();
                    navigate('/login');
                  }}
                >
                  退出
                </Button>
              </>
            ) : (
              <Button size="small" type="primary" onClick={() => navigate('/login')}>
                登录
              </Button>
            )}
          </div>
        </Header>
      )}
      <Content>
        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
            className="app-error-banner"
            style={{
              position: 'fixed',
              top: 20,
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 9999,
              maxWidth: '600px',
              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.45)',
            }}
          />
        )}
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/" element={<Navigate to="/stock-dashboard" replace />} />
          <Route path="/home" element={<RequireAuth><Home /></RequireAuth>} />
          <Route
            path="/stock-dashboard"
            element={<RequireAuth><StockDashboard /></RequireAuth>}
          />
          <Route
            path="/ai-diagnosis"
            element={<RequireAuth><AiDiagnosis /></RequireAuth>}
          />
          <Route
            path="/limit-up-echelon"
            element={<RequireAuth><LimitUpEchelon /></RequireAuth>}
          />
          <Route
            path="/dragon-tiger"
            element={<RequireAuth><DragonTiger /></RequireAuth>}
          />
          <Route
            path="/emotion-cycle"
            element={
              <RequireAuth>
                <PermissionGuard>
                  <EmotionCycle />
                </PermissionGuard>
              </RequireAuth>
            }
          />
          <Route
            path="/auction-grab"
            element={
              <RequireAuth>
                <PermissionGuard>
                  <AuctionGrab />
                </PermissionGuard>
              </RequireAuth>
            }
          />
          <Route
            path="/permission-center"
            element={<RequireAuth><PermissionCenter /></RequireAuth>}
          />
          <Route
            path="/user-center"
            element={<RequireAuth><UserCenter /></RequireAuth>}
          />
          <Route path="*" element={<Navigate to="/stock-dashboard" replace />} />
        </Routes>
      </Content>
    </Layout>
  );
}

function App() {
  return <AppInner />;
}

export default App;
