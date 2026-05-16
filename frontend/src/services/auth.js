// frontend/src/services/auth.js
import { apiConfig } from '../config/api';

const BASE = apiConfig.baseURL;
const TOKEN_KEY = 'niuniu_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const removeToken = () => localStorage.removeItem(TOKEN_KEY);

const authFetch = async (path, options = {}) => {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  const data = await res.json();
  return data;
};

export const login = (username, password) =>
  authFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });

export const logout = () =>
  authFetch('/api/auth/logout', { method: 'POST' });

export const changePassword = (old_password, new_password) =>
  authFetch('/api/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ old_password, new_password }),
  });

export const getProfile = () => authFetch('/api/user/profile');

export const getOrders = (page = 1, page_size = 10) =>
  authFetch(`/api/orders?page=${page}&page_size=${page_size}`);

export const createOrder = (plan_type) =>
  authFetch('/api/orders/create', {
    method: 'POST',
    body: JSON.stringify({ plan_type }),
  });

export const mockPay = (order_no) =>
  authFetch('/api/orders/mock-pay', {
    method: 'POST',
    body: JSON.stringify({ order_no }),
  });
