// frontend/src/context/AuthContext.js
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  getToken,
  setToken,
  removeToken,
  login as apiLogin,
  logout as apiLogout,
  getProfile,
} from '../services/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isVip, setIsVip] = useState(false);
  const [expireTime, setExpireTime] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setIsVip(false);
      setExpireTime(null);
      setLoading(false);
      return;
    }
    try {
      const res = await getProfile();
      if (res.success && res.data) {
        setUser(res.data);
        setIsVip(res.data.is_vip || false);
        setExpireTime(res.data.expire_time || null);
      } else {
        removeToken();
        setUser(null);
        setIsVip(false);
        setExpireTime(null);
      }
    } catch {
      removeToken();
      setUser(null);
      setIsVip(false);
      setExpireTime(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (username, password) => {
    const res = await apiLogin(username, password);
    if (res.success) {
      setToken(res.token);
      await refreshUser();
    }
    return res;
  };

  const logout = async () => {
    try {
      await apiLogout();
    } catch {}
    removeToken();
    setUser(null);
    setIsVip(false);
    setExpireTime(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, isVip, expireTime, loading, login, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
