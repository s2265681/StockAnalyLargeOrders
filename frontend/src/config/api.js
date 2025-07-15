// API配置文件
// 支持通过环境变量动态配置API地址

// 从环境变量获取配置，如果没有则使用默认值
const getApiConfig = () => {
  const currentEnv = process.env.NODE_ENV || 'development';
  const customBaseUrl = process.env.REACT_APP_API_BASE_URL;
  
  // 默认配置
  const defaultConfig = {
    development: {
      baseURL: 'http://localhost:9001',
      timeout: 10000,
    },
    production: {
      baseURL: 'http://18.141.179.222:9001', 
      timeout: 15000,
    }
  };

  // 如果有环境变量配置，优先使用环境变量
  if (customBaseUrl) {
    return {
      baseURL: customBaseUrl,
      timeout: parseInt(process.env.REACT_APP_API_TIMEOUT) || defaultConfig[currentEnv].timeout,
      environment: currentEnv,
      isDebug: process.env.REACT_APP_DEBUG_API === 'true'
    };
  }

  return {
    ...defaultConfig[currentEnv],
    environment: currentEnv,
    isDebug: currentEnv === 'development'
  };
};

// 导出当前环境的配置
export const apiConfig = getApiConfig();

// 构建完整的API URL
export const buildApiUrl = (endpoint) => {
  return `${apiConfig.baseURL}${endpoint}`;
};

// 通用的fetch封装，包含错误处理和超时
export const apiRequest = async (endpoint, options = {}) => {
  const url = buildApiUrl(endpoint);
  const config = {
    timeout: apiConfig.timeout,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  // 调试日志
  if (apiConfig.isDebug) {
    console.log(`📡 API Request: ${url}`, config);
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), config.timeout);
    
    const response = await fetch(url, {
      ...config,
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    
    // 调试日志
    if (apiConfig.isDebug) {
      console.log(`✅ API Response: ${url}`, data);
    }
    
    return data;
  } catch (error) {
    // 错误日志
    if (apiConfig.isDebug) {
      console.error(`❌ API Error: ${url}`, error);
    }
    
    if (error.name === 'AbortError') {
      throw new Error('请求超时');
    }
    throw error;
  }
};

// 导出环境信息（用于调试）
export const getEnvironmentInfo = () => {
  return {
    environment: apiConfig.environment,
    baseURL: apiConfig.baseURL,
    timeout: apiConfig.timeout,
    isProduction: apiConfig.environment === 'production',
    isDevelopment: apiConfig.environment === 'development',
    isDebug: apiConfig.isDebug,
    nodeEnv: process.env.NODE_ENV,
    customApiUrl: process.env.REACT_APP_API_BASE_URL || 'not set'
  };
};

// 健康检查函数
export const checkApiHealth = async () => {
  try {
    const response = await apiRequest('/health', { timeout: 5000 });
    return { status: 'healthy', response };
  } catch (error) {
    return { status: 'unhealthy', error: error.message };
  }
};

// 在开发环境下打印API配置信息
if (apiConfig.isDebug) {
  console.log('🔧 API Configuration:', getEnvironmentInfo());
}

// 导出常用的HTTP方法
export const api = {
  get: (endpoint, options = {}) => apiRequest(endpoint, { method: 'GET', ...options }),
  post: (endpoint, data, options = {}) => apiRequest(endpoint, { 
    method: 'POST', 
    body: JSON.stringify(data),
    ...options 
  }),
  put: (endpoint, data, options = {}) => apiRequest(endpoint, { 
    method: 'PUT', 
    body: JSON.stringify(data),
    ...options 
  }),
  delete: (endpoint, options = {}) => apiRequest(endpoint, { method: 'DELETE', ...options })
}; 