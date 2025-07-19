// IE兼容性polyfill - 必须在其他import之前
import 'react-app-polyfill/ie11';
import 'react-app-polyfill/stable';
import 'core-js/stable';
import 'regenerator-runtime/runtime';

import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import './index.css';

// 浏览器检测和错误处理
import { checkCompatibility, setupErrorHandling } from './utils/browserDetection';

// 设置错误处理
setupErrorHandling();

// 检查浏览器兼容性
const compatibility = checkCompatibility();
if (!compatibility.compatible) {
  console.warn('浏览器兼容性警告:', compatibility.warnings);
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>
); 