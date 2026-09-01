/**
 * 将 REACT_APP_BAIDU_TONGJI_ID 写入 public/baidu-tongji-config.js，
 * 供 landing.html 与 SPA 共用（构建/启动前执行）。
 */
const fs = require('fs');
const path = require('path');

const siteId = (process.env.REACT_APP_BAIDU_TONGJI_ID || '').trim();
const outPath = path.join(__dirname, '../public/baidu-tongji-config.js');

const content = `// Auto-generated — do not edit. Set REACT_APP_BAIDU_TONGJI_ID in env.
window.__BAIDU_TONGJI_ID__ = ${JSON.stringify(siteId)};
`;

fs.writeFileSync(outPath, content, 'utf8');
console.log(siteId ? `[baidu-tongji] config written (id: ${siteId.slice(0, 4)}…)` : '[baidu-tongji] no site id — tracking disabled');
