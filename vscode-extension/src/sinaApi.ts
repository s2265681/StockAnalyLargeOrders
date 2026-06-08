import * as https from 'https';
import * as http from 'http';

export interface StockQuote {
  code: string;
  name: string;
  price: number;
  open: number;
  yestClose: number;
  high: number;
  low: number;
  percent: number;
  updown: number;
  volume: number;   // 成交量（手）
  amount: number;   // 成交额（元）
  buy1Vol: number;
  buy1Price: number;
  sell1Vol: number;
  sell1Price: number;
  time: string;
  isLimitUp: boolean;
  isLimitDown: boolean;
}

export interface SearchResult {
  code: string;  // e.g. "sh603678"
  name: string;
}

function httpGet(url: string, referer?: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http;
    const req = client.get(
      url,
      {
        headers: {
          'Referer': referer ?? 'https://gu.qq.com/',
          'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        },
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (c: Buffer) => chunks.push(c));
        res.on('end', () => resolve(new TextDecoder('gbk').decode(Buffer.concat(chunks))));
      }
    );
    req.on('error', reject);
    req.setTimeout(8000, () => req.destroy(new Error('timeout')));
  });
}

function formatTencentTime(ts: string): string {
  if (ts.length === 14) {
    return `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(8, 10)}:${ts.slice(10, 12)}:${ts.slice(12, 14)}`;
  }
  return ts;
}

export async function fetchQuotes(codes: string[]): Promise<StockQuote[]> {
  if (codes.length === 0) return [];

  const url = `https://qt.gtimg.cn/q=${codes.join(',')}`;
  const text = await httpGet(url, 'https://gu.qq.com/');
  const results: StockQuote[] = [];

  for (const line of text.split('\n')) {
    const match = line.match(/v_(\w+)="([^"]*)"/);
    if (!match || !match[2]) continue;

    const code = match[1];
    const f = match[2].split('~');
    if (f.length < 38 || !f[1]) continue;

    const yestClose = parseFloat(f[4]) || 0;
    const price     = parseFloat(f[3]) || 0;
    const updown    = parseFloat(f[31]) || parseFloat((price - yestClose).toFixed(2));
    const percent   = parseFloat(f[32]) || (yestClose > 0
      ? parseFloat(((price - yestClose) / yestClose * 100).toFixed(2))
      : 0);

    results.push({
      code,
      name:        f[1],
      price,
      open:        parseFloat(f[5]) || 0,
      yestClose,
      high:        parseFloat(f[33]) || 0,
      low:         parseFloat(f[34]) || 0,
      percent,
      updown,
      volume:      parseInt(f[6]) || 0,               // 手
      amount:      (parseFloat(f[37]) || 0) * 10000,  // 万元 → 元
      buy1Vol:     (parseInt(f[10]) || 0) * 100,      // 手 → 股
      buy1Price:   parseFloat(f[9]) || 0,
      sell1Vol:    (parseInt(f[20]) || 0) * 100,      // 手 → 股
      sell1Price:  parseFloat(f[19]) || 0,
      time:        formatTencentTime(f[30] || ''),
      isLimitUp:   price > 0 && price >= parseFloat((yestClose * 1.1).toFixed(2)),
      isLimitDown: price > 0 && price <= parseFloat((yestClose * 0.9).toFixed(2)),
    });
  }
  return results;
}

export async function searchStock(keyword: string): Promise<SearchResult[]> {
  const url = `https://suggest3.sinajs.cn/suggest/type=11,12&key=${encodeURIComponent(keyword)}`;
  try {
    const text = await httpGet(url, 'https://finance.sina.com.cn');
    const match = text.match(/suggestvalue="([^"]*)"/);
    if (!match?.[1]) return [];

    return match[1]
      .split(';')
      .filter(Boolean)
      .slice(0, 8)
      .map(item => {
        const p = item.split(',');
        if (p.length < 4 || !/^\d{6}$/.test(p[2])) return null;
        return { code: `${p[1] === '11' ? 'sh' : 'sz'}${p[2]}`, name: p[0] };
      })
      .filter((r): r is SearchResult => r !== null);
  } catch {
    return [];
  }
}
