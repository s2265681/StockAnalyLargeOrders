import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../config/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem('niuniu_token');
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await api.get('/api/user/profile');
      if (res.success && res.data) {
        setUser(res.data);
      } else {
        localStorage.removeItem('niuniu_token');
        setUser(null);
      }
    } catch {
      localStorage.removeItem('niuniu_token');
      setUser(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (username, password) => {
    const res = await api.post('/api/auth/login', { username, password });
    if (res.success && res.data?.token) {
      localStorage.setItem('niuniu_token', res.data.token);
      await refreshUser();
      return { success: true };
    }
    return { success: false, message: res.message || '登录失败' };
  };

  const register = async (username, password, phone) => {
    const res = await api.post('/api/auth/register', { username, password, phone });
    if (res.success && res.data?.token) {
      localStorage.setItem('niuniu_token', res.data.token);
      await refreshUser();
      return { success: true };
    }
    return { success: false, message: res.message || '注册失败' };
  };

  const logout = () => {
    localStorage.removeItem('niuniu_token');
    setUser(null);
  };

  const isVip = !!(user?.vip?.end_time && new Date(user.vip.end_time) > new Date());

  return (
    <AuthContext.Provider value={{ user, loading, isVip, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
