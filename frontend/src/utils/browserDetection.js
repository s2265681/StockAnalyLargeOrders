/**
 * 浏览器检测工具
 * 用于检测IE和通达信内嵌浏览器
 */

// 检测是否为IE浏览器
export const isIE = () => {
  if (typeof window === 'undefined') return false;
  return /MSIE|Trident/.test(window.navigator.userAgent);
};

// 检测是否为通达信内嵌浏览器
export const isTdxBrowser = () => {
  if (typeof window === 'undefined') return false;
  return /TdxW/.test(window.navigator.userAgent);
};

// 检测Chrome版本
export const getChromeVersion = () => {
  if (typeof window === 'undefined') return null;
  const match = window.navigator.userAgent.match(/Chrome\/(\d+)/);
  return match ? parseInt(match[1], 10) : null;
};

// 检测是否为旧版本浏览器
export const isOldBrowser = () => {
  const chromeVersion = getChromeVersion();
  return isIE() || (chromeVersion && chromeVersion < 81);
};

// 获取浏览器信息
export const getBrowserInfo = () => {
  if (typeof window === 'undefined') return null;
  
  return {
    userAgent: window.navigator.userAgent,
    isIE: isIE(),
    isTdx: isTdxBrowser(),
    chromeVersion: getChromeVersion(),
    isOld: isOldBrowser(),
    platform: window.navigator.platform,
    language: window.navigator.language
  };
};

// 浏览器兼容性检查
export const checkCompatibility = () => {
  const info = getBrowserInfo();
  
  if (!info) return { compatible: true, warnings: [] };
  
  const warnings = [];
  
  if (info.isIE) {
    warnings.push('检测到IE浏览器，某些功能可能受限');
  }
  
  if (info.isTdx) {
    console.log('检测到通达信内嵌浏览器');
  }
  
  if (info.chromeVersion && info.chromeVersion < 81) {
    warnings.push(`Chrome版本较旧 (${info.chromeVersion})，建议升级到81+`);
  }
  
  return {
    compatible: warnings.length === 0,
    warnings,
    info
  };
};

// 全局错误处理
export const setupErrorHandling = () => {
  if (typeof window === 'undefined') return;
  
  // JavaScript错误处理
  window.addEventListener('error', (event) => {
    console.error('JavaScript错误:', {
      message: event.message,
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      error: event.error,
      browser: getBrowserInfo()
    });
  });
  
  // Promise错误处理
  window.addEventListener('unhandledrejection', (event) => {
    console.error('未处理的Promise拒绝:', {
      reason: event.reason,
      browser: getBrowserInfo()
    });
  });
  
  // 性能监控
  if ('performance' in window) {
    window.addEventListener('load', () => {
      setTimeout(() => {
        const perfData = performance.getEntriesByType('navigation')[0];
        if (perfData) {
          console.log('页面加载性能:', {
            loadTime: perfData.loadEventEnd - perfData.loadEventStart,
            domContentLoaded: perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart,
            browser: getBrowserInfo()
          });
        }
      }, 0);
    });
  }
};

export default {
  isIE,
  isTdxBrowser,
  getChromeVersion,
  isOldBrowser,
  getBrowserInfo,
  checkCompatibility,
  setupErrorHandling
}; 