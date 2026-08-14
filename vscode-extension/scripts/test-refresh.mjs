/**
 * 验证增删后状态栏列表合并逻辑 + 行情 API
 * 运行: node scripts/test-refresh.mjs
 */
import * as https from 'https';

// ── normalizeStockCode (mirror config.ts) ──────────────────────────────────
function normalizeStockCode(raw) {
  const text = String(raw || '').trim().toLowerCase();
  if (!text) return null;
  if (/^(sh|sz|bj)\d{6}$/.test(text)) return text;
  if (/^\d{6}$/.test(text)) {
    if (/^[568]/.test(text)) return `sh${text}`;
    if (/^9/.test(text)) return `bj${text}`;
    return `sz${text}`;
  }
  return null;
}

// ── mergeQuotesWithStocks (mirror extension.ts) ────────────────────────────
function placeholderQuote(stock) {
  return { code: stock.code, name: stock.name, isPlaceholder: true, price: 0 };
}

function mergeQuotesWithStocks(stocks, fetched) {
  const map = new Map(fetched.filter(q => !q.isPlaceholder).map(q => [q.code, q]));
  return stocks.map(s => map.get(s.code) ?? placeholderQuote(s));
}

function formatBar(quotes, max = 5) {
  const limited = quotes.slice(0, max);
  const parts = limited.map(q => q.isPlaceholder ? `${q.name} —` : `${q.name} ${q.price}`);
  const more = quotes.length > limited.length ? ` +${quotes.length - limited.length}` : '';
  return parts.join('  |  ') + more;
}

// ── fetchQuotes (minimal) ──────────────────────────────────────────────────
function httpGet(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { Referer: 'https://gu.qq.com/', 'User-Agent': 'Mozilla/5.0' } }, res => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => resolve(Buffer.concat(chunks).toString('latin1')));
    }).on('error', reject);
  });
}

async function fetchQuoteCodes(codes) {
  const url = `https://qt.gtimg.cn/q=${codes.join(',')}`;
  const text = await httpGet(url);
  const results = [];
  for (const line of text.split('\n')) {
    const m = line.match(/v_(\w+)="([^"]*)"/);
    if (!m?.[2]) continue;
    const f = m[2].split('~');
    if (f.length < 38 || !f[1]) continue;
    results.push({ code: m[1], name: f[1], price: parseFloat(f[3]) || 0 });
  }
  return results;
}

// ── Tests ──────────────────────────────────────────────────────────────────
let passed = 0;
let failed = 0;

function assert(cond, msg) {
  if (cond) { passed++; console.log(`  ✓ ${msg}`); }
  else { failed++; console.error(`  ✗ ${msg}`); }
}

console.log('\n=== 1. normalizeStockCode ===');
assert(normalizeStockCode('002437') === 'sz002437', '002437 → sz002437');
assert(normalizeStockCode('603678') === 'sh603678', '603678 → sh603678');
assert(normalizeStockCode('688001') === 'sh688001', '688001 → sh688001 (科创板)');
assert(normalizeStockCode('920001') === 'bj920001', '920001 → bj920001 (北交所)');

console.log('\n=== 2. mergeQuotesWithStocks (模拟增删) ===');
const stocks = [
  { code: 'sh600664', name: '哈药股份' },
  { code: 'sz002437', name: '誉衡药业' },
];
const fetchedOnlyOne = [{ code: 'sh600664', name: '哈药股份', price: 8.88 }];
const merged = mergeQuotesWithStocks(stocks, fetchedOnlyOne);
assert(merged.length === 2, '添加第2只后列表长度=2');
assert(merged[1].code === 'sz002437', '第2只是 sz002437');
assert(merged[1].isPlaceholder === true, '无行情时显示占位');
const barText = formatBar(merged);
assert(barText.includes('哈药股份'), '状态栏含哈药股份');
assert(barText.includes('誉衡药业'), '状态栏含新添加股票（占位）');
assert(barText.includes('—'), '占位显示 —');

// 模拟删除
const afterRemove = mergeQuotesWithStocks(stocks.filter(s => s.code !== 'sz002437'), fetchedOnlyOne);
assert(afterRemove.length === 1, '删除后列表长度=1');
assert(formatBar(afterRemove) === '哈药股份 8.88', '删除后状态栏只剩哈药股份');

// 模拟清空
assert(formatBar(mergeQuotesWithStocks([], [])) === '', '清空后无内容');

console.log('\n=== 3. 行情 API 实测 ===');
try {
  const codes = ['sh600664', 'sz002437'];
  const quotes = await fetchQuoteCodes(codes);
  console.log(`  请求 ${codes.join(',')} → 返回 ${quotes.length} 条:`);
  for (const q of quotes) console.log(`    ${q.code} ${q.name} ${q.price}`);

  const liveMerged = mergeQuotesWithStocks(stocks, quotes);
  assert(liveMerged.every(q => !q.isPlaceholder), '两只均有行情时不应占位');
  console.log(`  状态栏预览: ${formatBar(liveMerged)}`);

  // 错误前缀：sh002437 应无行情
  const wrongPrefix = await fetchQuoteCodes(['sh002437']);
  assert(wrongPrefix.length === 0, '错误前缀 sh002437 无行情');
  const fixedMerged = mergeQuotesWithStocks([{ code: 'sz002437', name: '誉衡药业' }], wrongPrefix);
  assert(fixedMerged[0].isPlaceholder, '错误前缀时仍显示占位项');
} catch (e) {
  failed++;
  console.error('  ✗ API 请求失败:', e.message);
}

console.log('\n=== 4. searchStock 解析（002437 应显示誉衡药业 + sz002437）===');
function parseSearchSuggest(text) {
  const match = text.match(/suggestvalue="([^"]*)"/);
  if (!match?.[1]) return [];
  return match[1].split(';').filter(Boolean).slice(0, 8).map(item => {
    const p = item.split(',');
    if (p.length < 5 || !/^\d{6}$/.test(p[2])) return null;
    const code = (p[3] || p[0] || '').trim().toLowerCase();
    if (!/^(sh|sz|bj)\d{6}$/.test(code)) return null;
    const name = (p[4] || p[6] || p[2]).trim();
    return name ? { code, name } : null;
  }).filter(Boolean);
}

try {
  const suggestBuf = await new Promise((resolve, reject) => {
    https.get('https://suggest3.sinajs.cn/suggest/type=11,12&key=002437', { headers: { Referer: 'https://finance.sina.com.cn' } }, res => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => resolve(Buffer.concat(chunks)));
    }).on('error', reject);
  });
  const suggestText = new TextDecoder('gbk').decode(suggestBuf);
  const parsed = parseSearchSuggest(suggestText);
  assert(parsed.length >= 1, '002437 搜索有结果');
  assert(parsed[0].code === 'sz002437', '002437 → sz002437');
  assert(parsed[0].name === '誉衡药业', '名称应为誉衡药业');
} catch (e) {
  failed++;
  console.error('  ✗ search 请求失败:', e.message);
}

console.log(`\n=== 结果: ${passed} passed, ${failed} failed ===\n`);
process.exit(failed > 0 ? 1 : 0);
