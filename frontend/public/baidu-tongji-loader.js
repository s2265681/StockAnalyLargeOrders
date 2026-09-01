/**
 * 百度统计 hm.js 加载器（landing.html 等静态页使用）。
 * 需先加载 baidu-tongji-config.js 设置 window.__BAIDU_TONGJI_ID__。
 */
(function () {
  var siteId = window.__BAIDU_TONGJI_ID__;
  if (!siteId) return;

  window._hmt = window._hmt || [];
  var hm = document.createElement('script');
  hm.src = 'https://hm.baidu.com/hm.js?' + siteId;
  hm.async = true;
  var first = document.getElementsByTagName('script')[0];
  first.parentNode.insertBefore(hm, first);
})();
