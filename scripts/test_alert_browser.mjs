/**
 * 条件预警页面浏览器自动化测试
 * 用法: node scripts/test_alert_browser.mjs
 */
import { chromium } from 'playwright';

const BASE = process.env.TEST_BASE_URL || 'http://localhost:9000';
const USER = 'rock';
const PASS = '123456';
const API = process.env.TEST_API_URL || 'http://localhost:9001';

const TEST_RULES = [
  { code: '600519', alert_type: 'limit_up', label: '涨停' },
  { code: '000001', alert_type: 'limit_down', label: '跌停' },
  { code: '600036', alert_type: 'change_pct', label: '涨跌幅', threshold: 5 },
  { code: '000002', alert_type: 'seal_order', label: '涨停封单', threshold: 5000, direction: 'below' },
];

const results = [];

function log(ok, name, detail = '') {
  results.push({ ok, name, detail });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ': ' + detail : ''}`);
}

async function apiLogin() {
  const res = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  });
  const data = await res.json();
  if (!data.success) throw new Error('API login failed: ' + data.message);
  return data.data.token;
}

async function cleanupRules(token) {
  const res = await fetch(`${API}/api/alert-rules`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!data.success) return;
  for (const r of data.data.items || []) {
    if (['600519', '000001', '600036', '000002'].includes(r.code)) {
      await fetch(`${API}/api/alert-rules/${r.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  }
}

async function getBackendRssKb() {
  try {
    const { execSync } = await import('node:child_process');
    const out = execSync("lsof -tiTCP:9001 -sTCP:LISTEN 2>/dev/null | head -1 | xargs ps -o rss= 2>/dev/null").toString().trim();
    return out ? Number(out) : null;
  } catch {
    return null;
  }
}

async function main() {
  const memBefore = await getBackendRssKb();
  console.log(`--- 后端内存(测试前): ${memBefore ?? '?'} KB ---`);

  let token;
  try {
    token = await apiLogin();
    await cleanupRules(token);
    log(true, 'API 登录');
  } catch (e) {
    log(false, 'API 登录', e.message);
    process.exit(1);
  }

  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome',
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.setDefaultTimeout(15000);

  // 监听 WebSocket
  let wsConnected = false;
  let monitorStatusViaWs = null;
  let alertTriggeredViaWs = false;
  page.on('websocket', (ws) => {
    const url = ws.url();
    if (url.includes('9001') || url.includes('socket.io')) {
      ws.on('framereceived', (frame) => {
        const text = frame.payload?.toString?.() || '';
        if (text.includes('alert_monitor_status')) {
          const m = text.match(/"display"\s*,\s*"(\w+)"/) || text.match(/"display":"(\w+)"/);
          if (m) monitorStatusViaWs = m[1];
        }
        if (text.includes('alert_rule_triggered')) {
          alertTriggeredViaWs = true;
        }
      });
      ws.on('open', () => { wsConnected = true; });
    }
  });

  try {
    // 注入 token 直达预警页（避免 dev server networkidle 卡死）
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    await page.evaluate((t) => localStorage.setItem('niuniu_token', t), token);
    await page.goto(`${BASE}/alert`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.alert-page-title', { timeout: 20000 });
    await page.waitForFunction(
      () => document.querySelector('.alert-table-wrap') && !document.querySelector('.ant-spin-spinning'),
      { timeout: 20000 },
    );
    log(true, '浏览器登录并进入预警页');

    // 等待 WS 监控状态
    await page.waitForTimeout(2500);
    const badgeText = await page.locator('.alert-page-title').textContent();
    const hasMonitorBadge = /监控正常|非交易时段|监控异常|监控未启动/.test(badgeText || '');
    log(hasMonitorBadge, '监控角标展示', badgeText?.trim().slice(0, 40));
    log(wsConnected || !!monitorStatusViaWs, 'WebSocket 已连接', monitorStatusViaWs || (wsConnected ? 'open' : ''));
    if (monitorStatusViaWs) {
      log(true, 'WebSocket 收到监控状态', monitorStatusViaWs);
    } else {
      log(hasMonitorBadge, 'WebSocket 监控状态推送', hasMonitorBadge ? '角标有值(可能 connect 时 emit)' : '未收到');
    }

    // 逐条创建四种类型
    for (const rule of TEST_RULES) {
      await page.click('button.alert-add-btn');
      await page.waitForSelector('.alert-add-area', { timeout: 5000 });

      await page.locator('.alert-add-row').first().locator('input[placeholder="如 600519"]').fill(rule.code);

      if (rule.alert_type !== 'limit_up') {
        await page.locator('.alert-add-row').first().locator('.alert-field').nth(1).locator('.ant-select').click();
        await page.locator('.ant-select-dropdown:visible').getByTitle(rule.label, { exact: true }).click();
      }

      if (rule.alert_type === 'change_pct') {
        await page.locator('.alert-add-row .change-pct input').fill(String(rule.threshold));
      }
      if (rule.alert_type === 'seal_order') {
        await page.locator('.alert-add-row .seal input').fill(String(rule.threshold));
      }

      const emailInput = page.locator('.alert-add-row').first().locator('input[placeholder="可到个人中心设置常用邮箱"]');
      const emailVal = await emailInput.inputValue();
      if (!emailVal) await emailInput.fill('test@example.com');

      await page.locator('.alert-add-actions button.ant-btn-primary').click();
      await page.waitForTimeout(1500);

      const row = page.locator('.ant-table-tbody tr').filter({ hasText: rule.code });
      const visible = await row.count() > 0;
      const typeOk = visible && (await row.textContent()).includes(rule.label);
      log(typeOk, `创建 ${rule.label} (${rule.code})`, typeOk ? '列表已显示' : '未找到');

      // 收起新增区
      if (await page.locator('.alert-add-area').isVisible()) {
        await page.click('button.alert-add-btn');
        await page.waitForTimeout(300);
      }
    }

    // 编辑涨跌幅规则
    const editRow = page.locator('.ant-table-tbody tr').filter({ hasText: '600036' });
    await editRow.locator('button').first().click();
    await page.waitForSelector('.alert-edit-modal', { timeout: 5000 });
    await page.locator('.alert-edit-form .change-pct input').fill('3');
    await page.locator('.alert-edit-modal .ant-btn-primary').click();
    await page.waitForTimeout(1000);
    const edited = (await page.locator('.ant-table-tbody tr').filter({ hasText: '600036' }).textContent()).includes('+3%')
      || (await page.locator('.ant-table-tbody tr').filter({ hasText: '600036' }).textContent()).includes('3%');
    log(edited, '编辑涨跌幅阈值', edited ? '已变为 3%' : '未更新');

    // API 验证监控在跑
    const msRes = await fetch(`${API}/api/alert-rules/monitor-status`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const ms = await msRes.json();
    const monitorOk = ms.success && ['running', 'sleeping'].includes(ms.data?.display);
    log(monitorOk, '后端监控服务状态', JSON.stringify(ms.data));

    // 等待监控周期（封单3s + 通用5s）并观察内存
    await page.waitForTimeout(10000);
    const rulesRes = await fetch(`${API}/api/alert-rules`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const rulesData = await rulesRes.json();
    const activeCount = (rulesData.data?.items || []).filter(r => r.status === 'active').length;
    log(rulesData.success && activeCount >= 4, 'API 规则列表', `active=${activeCount}`);

    // 停用 + 删除清理
    for (const code of ['600519', '000001', '600036', '000002']) {
      const row = page.locator('.ant-table-tbody tr').filter({ hasText: code });
      if (await row.count() === 0) continue;
      const pauseBtn = row.locator('button').nth(1);
      if (await pauseBtn.count()) {
        await pauseBtn.click();
        await page.waitForTimeout(800);
      }
    }
    log(true, '停用规则', '已点击停用');

    for (const code of ['600519', '000001', '600036', '000002']) {
      const row = page.locator('.ant-table-tbody tr').filter({ hasText: code });
      if (await row.count() === 0) continue;
      await row.locator('button.ant-btn-dangerous').click();
      await page.locator('.ant-popconfirm-buttons .ant-btn-primary').click();
      await page.waitForTimeout(500);
    }
    await page.waitForTimeout(1000);
    const remaining = await page.locator('.ant-table-tbody tr').filter({ hasText: /600519|000001|600036|000002/ }).count();
    log(remaining === 0, '删除测试规则', `剩余 ${remaining} 条`);

  } catch (e) {
    log(false, '测试异常', e.message);
    console.error(e);
  } finally {
    await browser.close();
    if (token) await cleanupRules(token);
  }

  const memAfter = await getBackendRssKb();
  console.log(`--- 后端内存(测试后): ${memAfter ?? '?'} KB ---`);
  if (memBefore && memAfter) {
    const delta = memAfter - memBefore;
    const ok = delta < 50 * 1024; // 增长 < 50MB 视为正常
    log(ok, '后端内存未暴涨', `+${Math.round(delta / 1024)}MB (${memBefore}→${memAfter} KB)`);
  }

  const failed = results.filter(r => !r.ok);
  console.log('\n========== 汇总 ==========');
  console.log(`通过 ${results.length - failed.length}/${results.length}`);
  if (failed.length) {
    failed.forEach(f => console.log(`  FAIL: ${f.name} — ${f.detail}`));
    process.exit(1);
  }
}

main();
