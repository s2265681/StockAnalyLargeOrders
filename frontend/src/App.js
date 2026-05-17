import React, { useState } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Alert, Menu, Button, Drawer } from 'antd';
import {
  MenuOutlined,
  CloseOutlined,
  UserOutlined,
  LogoutOutlined,
  LineChartOutlined,
  RobotOutlined,
  FireOutlined,
  ThunderboltOutlined,
  DashboardOutlined,
  ClockCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
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

function NavLogoIcon({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <circle cx="18" cy="18" r="17" fill="var(--gold-bg,#fffbeb)" stroke="var(--color-accent,#d97706)" strokeWidth="1.5" />
      <path d="M18,10 L4,28 Q18,24 32,28 Z" fill="var(--color-accent,#d97706)" opacity="0.25" />
      <rect x="14" y="13" width="8" height="14" rx="2" fill="var(--color-accent,#d97706)" />
      <polygon points="11,13 25,13 23,7 13,7" fill="var(--color-accent2,#f59e0b)" />
      <circle cx="18" cy="10" r="3.5" fill="#fff" opacity="0.95" />
      <circle cx="18" cy="10" r="2" fill="var(--color-accent2,#f59e0b)" />
    </svg>
  );
}

const NAV_ITEMS = [
  { key: '/stock-dashboard', icon: <LineChartOutlined />, label: '个股分析' },
  { key: '/limit-up-echelon', icon: <FireOutlined />, label: '涨停梯队' },
  { key: '/dragon-tiger', icon: <ThunderboltOutlined />, label: '核心游资' },
  { key: '/emotion-cycle', icon: <DashboardOutlined />, label: '情绪周期' },
  { key: '/auction-grab', icon: <ClockCircleOutlined />, label: '竞价抢筹' },
  { key: '/ai-diagnosis', icon: <RobotOutlined />, label: 'AI诊股' },
  { key: '/permission-center', icon: <SafetyCertificateOutlined />, label: '权限中心' },
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
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const isAuthPage = location.pathname === '/login' || location.pathname === '/register';

  const handleMenuClick = ({ key }) => {
    navigate(key);
    setDrawerOpen(false);
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
    setDrawerOpen(false);
  };

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
          {/* 移动端汉堡按钮 */}
          <Button
            className="mobile-menu-btn"
            type="text"
            icon={<MenuOutlined style={{ fontSize: 18, color: 'var(--text-primary)' }} />}
            onClick={() => setDrawerOpen(true)}
            style={{ marginLeft: 8, flexShrink: 0 }}
          />

          {/* Logo */}
          <div
            className="nav-logo-brand"
            onClick={() => window.location.href = '/'}
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', flexShrink: 0, marginRight: 8, marginLeft: 16 }}
          >
            <NavLogoIcon />
            <span className="nav-logo-name" style={{ fontSize: 15, fontWeight: 800, color: 'var(--color-accent)', letterSpacing: 0.5 }}>
              AI炒股指南
            </span>
          </div>

          {/* 桌面端水平菜单 */}
          <Menu
            className="desktop-nav-menu"
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

          {/* 右侧操作区 */}
          <div
            className="nav-right-actions"
            style={{
              display: 'flex',
              alignItems: 'center',
              paddingRight: 16,
              gap: 4,
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
            {/* 桌面端用户操作 */}
            <div className="desktop-user-actions">
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
                    onClick={handleLogout}
                  >
                    退出登录
                  </Button>
                </>
              ) : (
                <Button size="small" type="primary" onClick={() => navigate('/login')}>
                  登录
                </Button>
              )}
            </div>
          </div>
        </Header>
      )}

      {/* 移动端抽屉菜单 */}
      <Drawer
        className="mobile-nav-drawer"
        closable={false}
        title={(
          <div className="mobile-drawer-header-title">
            <NavLogoIcon size={28} />
            <span>AI炒股指南</span>
          </div>
        )}
        extra={(
          <Button
            type="text"
            className="mobile-drawer-close"
            aria-label="关闭菜单"
            icon={<CloseOutlined style={{ fontSize: 16, color: 'var(--text-muted)' }} />}
            onClick={() => setDrawerOpen(false)}
          />
        )}
        placement="left"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={220}
        styles={{
          header: { background: 'var(--bg-header)', borderBottom: '1px solid var(--border-secondary)', padding: '10px 8px' },
          body: { padding: 0, background: 'var(--bg-primary)' },
        }}
      >
        <Menu
          className="mobile-drawer-menu"
          mode="inline"
          inlineIndent={8}
          selectedKeys={[location.pathname]}
          items={NAV_ITEMS}
          onClick={handleMenuClick}
          theme={theme === 'dark' ? 'dark' : 'light'}
          style={{ border: 'none', background: 'transparent' }}
        />
        <div
          style={{
            padding: '12px 0',
            borderTop: '1px solid var(--border-secondary)',
            marginTop: 8,
          }}
        >
          {user ? (
            <>
              <div
                style={{
                  padding: '10px 8px',
                  cursor: 'pointer',
                  color: 'var(--color-accent)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 14,
                }}
                onClick={() => { navigate('/user-center'); setDrawerOpen(false); }}
              >
                <UserOutlined />
                个人中心（{user.username}）
              </div>
              <Button
                block
                type="text"
                danger
                icon={<LogoutOutlined />}
                style={{ textAlign: 'left', justifyContent: 'flex-start', paddingLeft: 8, height: 40 }}
                onClick={handleLogout}
              >
                退出登录
              </Button>
            </>
          ) : (
            <div style={{ padding: '0 8px' }}>
              <Button block type="primary" onClick={() => { navigate('/login'); setDrawerOpen(false); }}>
                登录
              </Button>
            </div>
          )}
        </div>
      </Drawer>

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
