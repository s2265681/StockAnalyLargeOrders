const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/Users/a1/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
    args: ['--no-sandbox', '--disable-gpu'],
  });
  const context = await browser.newContext({ viewport: { width: 1920, height: 900 } });
  const page = await context.newPage();

  // 监听控制台错误
  page.on('console', msg => { if (msg.type() === 'error') console.log('PAGE ERROR:', msg.text()); });
  page.on('response', res => { if (res.url().includes('/api/') && res.status() >= 400) console.log('API ERR:', res.status(), res.url()); });

  // 打开首页，检查是否有登录页
  await page.goto('http://localhost:9000', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: '/tmp/screen_1_home.png' });
  console.log('home:', page.url());

  // 直接通过 API 登录，注入 token 到 localStorage
  const loginResp = await page.evaluate(async () => {
    const r = await fetch('http://localhost:9001/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'rock', password: '123456' }),
    });
    return r.json();
  });
  console.log('login api:', loginResp.success, loginResp.message || '');
  if (loginResp.success && loginResp.data?.token) {
    await page.evaluate((token) => {
      localStorage.setItem('niuniu_token', token);
    }, loginResp.data.token);
    await page.goto('http://localhost:9000/auction-grab', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(2000);
  }

  console.log('after login:', page.url());
  await page.screenshot({ path: '/tmp/screen_3_main.png' });

  // 等待竞价抢筹数据加载（等 score 富化返回）
  await page.waitForSelector('.ag-table-row', { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(12000);
  await page.screenshot({ path: '/tmp/screen_4_auction.png', fullPage: false });
  console.log('auction page done, url:', page.url());

  await browser.close();
})();
