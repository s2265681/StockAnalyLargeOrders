/**
 * 百度统计 — SPA 路由 PV 上报。
 * 站点 ID：REACT_APP_BAIDU_TONGJI_ID 或 window.__BAIDU_TONGJI_ID__（由 baidu-tongji-config.js 注入）。
 */

function getSiteId() {
  return (process.env.REACT_APP_BAIDU_TONGJI_ID || window.__BAIDU_TONGJI_ID__ || '').trim();
}

let initialized = false;

export function initBaiduTongji() {
  const siteId = getSiteId();
  if (!siteId || initialized) return;

  window._hmt = window._hmt || [];
  const existing = document.querySelector('script[src*="hm.baidu.com/hm.js"]');
  if (!existing) {
    const hm = document.createElement('script');
    hm.src = `https://hm.baidu.com/hm.js?${siteId}`;
    hm.async = true;
    document.head.appendChild(hm);
  }
  initialized = true;
}

export function trackPageView(path) {
  const siteId = getSiteId();
  if (!siteId) return;

  initBaiduTongji();
  window._hmt = window._hmt || [];
  window._hmt.push(['_trackPageview', path || window.location.pathname + window.location.search]);
}

export function isBaiduTongjiEnabled() {
  return Boolean(getSiteId());
}
