const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  // 1. 打开首页
  await page.goto('http://localhost:9000', { waitUntil: 'networkidle', timeout: 30000 });
  await page.screenshot({ path: '/tmp/stock_1_home.png', fullPage: false });
  console.log('Screenshot 1: home page');

  // 2. 如果有登录页面，填写账号密码
  const loginInput = await page.$('input[type="text"], input[placeholder*="账号"], input[placeholder*="用户"], input[name="username"]');
  if (loginInput) {
    await loginInput.fill('rock');
    const pwdInput = await page.$('input[type="password"]');
    if (pwdInput) {
      await pwdInput.fill('111111');
      await page.screenshot({ path: '/tmp/stock_2_login_filled.png' });
      console.log('Screenshot 2: login filled');

      // 点击登录按钮
      const loginBtn = await page.$('button[type="submit"], button:has-text("登录"), button:has-text("Login")');
      if (loginBtn) {
        await loginBtn.click();
        await page.waitForTimeout(3000);
        await page.screenshot({ path: '/tmp/stock_3_after_login.png' });
        console.log('Screenshot 3: after login');
      }
    }
  } else {
    console.log('No login form found on home page');
    await page.screenshot({ path: '/tmp/stock_3_after_login.png' });
  }

  // 3. 截图当前页面
  const title = await page.title();
  const url = page.url();
  console.log('Page title:', title);
  console.log('Page URL:', url);

  await browser.close();
})();
