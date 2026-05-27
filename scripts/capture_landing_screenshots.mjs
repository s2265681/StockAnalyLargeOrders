/**
 * 登录并截取官网功能展示图
 * 用法: node scripts/capture_landing_screenshots.mjs [BASE_URL]
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, '../frontend/public/landing-screenshots');
const BASE = process.env.BASE_URL || process.argv[2] || 'https://stockai.xin';
const API = process.env.API_URL || (BASE.includes('localhost') ? 'http://localhost:9001' : BASE);
const USER = 'rock';
const PASS = '123456';

const PAGES = [
  { id: 'stock-dashboard', path: '/stock-dashboard?code=601991', title: '个股分析', wait: '.stock-dashboard-container', delay: 4000 },
  { id: 'ai-diagnosis', path: '/ai-diagnosis', title: 'AI诊股', wait: '.ai-diagnosis-page, [class*="diagnosis"]', delay: 3000 },
  { id: 'limit-up-echelon', path: '/limit-up-echelon', title: '涨停梯队', wait: '.limit-up-echelon, [class*="echelon"]', delay: 3000 },
  { id: 'dragon-tiger', path: '/dragon-tiger', title: '核心游资', wait: '.dragon-tiger-page, [class*="dragon"]', delay: 3000 },
  { id: 'emotion-cycle', path: '/emotion-cycle', title: '情绪周期', wait: '.emotion-cycle-page, [class*="emotion"]', delay: 4000 },
  { id: 'auction-grab', path: '/auction-grab', title: '竞价抢筹', wait: '.auction-grab-page, [class*="auction"]', delay: 3000 },
  { id: 'alert', path: '/alert', title: '条件预警', wait: '.alert-page-title', delay: 2000 },
];

async function apiLogin() {
  const res = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  });
  const data = await res.json();
  if (!data.success) throw new Error('API login failed: ' + (data.message || JSON.stringify(data)));
  return data.data.token;
}

async function hideChrome(page) {
  await page.addStyleTag({
    content: `
      .mobile-menu-btn, .ant-layout-header .ant-menu { visibility: hidden !important; }
      .ant-drawer { display: none !important; }
    `,
  }).catch(() => {});
}

async function capture(page, spec, viewport) {
  const suffix = viewport.width <= 480 ? '-mobile' : '';
  const file = path.join(OUT_DIR, `${spec.id}${suffix}.png`);
  await page.setViewportSize(viewport);
  await page.goto(`${BASE}${spec.path}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  try {
    await page.waitForSelector(spec.wait, { timeout: 25000 });
  } catch {
    await page.waitForTimeout(3000);
  }
  await page.waitForTimeout(spec.delay);
  await hideChrome(page);
  const header = await page.locator('.ant-layout-header').first();
  const box = await header.boundingBox().catch(() => null);
  const clipY = box ? Math.max(0, box.y + box.height) : 56;
  await page.screenshot({
    path: file,
    type: 'png',
    clip: { x: 0, y: clipY, width: viewport.width, height: Math.min(viewport.height - clipY, viewport.width <= 480 ? 700 : 620) },
  });
  console.log('✓', file);
  return file;
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const token = await apiLogin();
  console.log('Logged in via API');

  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const context = await browser.newContext({ deviceScaleFactor: 2 });
  const page = await context.newPage();

  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((t) => {
    localStorage.setItem('niuniu_token', t);
    localStorage.setItem('niuniu_theme', 'light');
  }, token);

  const desktop = { width: 1280, height: 900 };
  const mobile = { width: 390, height: 844 };

  for (const spec of PAGES) {
    try {
      await capture(page, spec, desktop);
      if (['stock-dashboard', 'limit-up-echelon', 'emotion-cycle'].includes(spec.id)) {
        await capture(page, spec, mobile);
      }
    } catch (e) {
      console.error('✗', spec.id, e.message);
    }
  }

  await browser.close();
  console.log('Done →', OUT_DIR);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
