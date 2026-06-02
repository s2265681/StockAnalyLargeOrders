"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.fetchQuotes = fetchQuotes;
exports.searchStock = searchStock;
const https = __importStar(require("https"));
const http = __importStar(require("http"));
function httpGet(url) {
    return new Promise((resolve, reject) => {
        const client = url.startsWith('https') ? https : http;
        const req = client.get(url, {
            headers: {
                'Referer': 'https://finance.sina.com.cn',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            },
        }, (res) => {
            const chunks = [];
            res.on('data', (c) => chunks.push(c));
            res.on('end', () => resolve(new TextDecoder('gbk').decode(Buffer.concat(chunks))));
        });
        req.on('error', reject);
        req.setTimeout(8000, () => req.destroy(new Error('timeout')));
    });
}
async function fetchQuotes(codes) {
    if (codes.length === 0)
        return [];
    const url = `https://hq.sinajs.cn/rn=${Date.now()}&list=${codes.join(',')}`;
    const text = await httpGet(url);
    const results = [];
    for (const line of text.split('\n')) {
        const match = line.match(/hq_str_(\w+)="([^"]*)"/);
        if (!match || !match[2])
            continue;
        const code = match[1];
        const f = match[2].split(',');
        if (f.length < 32 || !f[0])
            continue;
        const yestClose = parseFloat(f[2]) || 0;
        const price = parseFloat(f[3]) || 0;
        const updown = parseFloat((price - yestClose).toFixed(2));
        const percent = yestClose > 0
            ? parseFloat(((updown / yestClose) * 100).toFixed(2))
            : 0;
        results.push({
            code,
            name: f[0],
            open: parseFloat(f[1]) || 0,
            yestClose,
            price,
            high: parseFloat(f[4]) || 0,
            low: parseFloat(f[5]) || 0,
            percent,
            updown,
            volume: Math.round((parseFloat(f[8]) || 0) / 100),
            amount: parseFloat(f[9]) || 0,
            buy1Vol: parseInt(f[10]) || 0,
            buy1Price: parseFloat(f[11]) || 0,
            sell1Vol: parseInt(f[20]) || 0,
            sell1Price: parseFloat(f[21]) || 0,
            time: `${f[30]} ${f[31]}`.trim(),
            isLimitUp: price > 0 && price >= parseFloat((yestClose * 1.1).toFixed(2)),
            isLimitDown: price > 0 && price <= parseFloat((yestClose * 0.9).toFixed(2)),
        });
    }
    return results;
}
async function searchStock(keyword) {
    const url = `https://suggest3.sinajs.cn/suggest/type=11,12&key=${encodeURIComponent(keyword)}`;
    try {
        const text = await httpGet(url);
        const match = text.match(/suggestvalue="([^"]*)"/);
        if (!match?.[1])
            return [];
        return match[1]
            .split(';')
            .filter(Boolean)
            .slice(0, 8)
            .map(item => {
            const p = item.split(',');
            if (p.length < 4 || !/^\d{6}$/.test(p[2]))
                return null;
            return { code: `${p[1] === '11' ? 'sh' : 'sz'}${p[2]}`, name: p[0] };
        })
            .filter((r) => r !== null);
    }
    catch {
        return [];
    }
}
//# sourceMappingURL=sinaApi.js.map