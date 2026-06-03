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
exports.normalizeStockCode = normalizeStockCode;
exports.readExtensionConfig = readExtensionConfig;
exports.toStatusDisplayConfig = toStatusDisplayConfig;
const vscode = __importStar(require("vscode"));
const panel_1 = require("./panel");
/** 6 位或带市场前缀的股票代码 → sh/sz/bj 前缀小写 */
function normalizeStockCode(raw) {
    const text = String(raw || '').trim().toLowerCase();
    if (!text)
        return null;
    if (/^(sh|sz|bj)\d{6}$/.test(text))
        return text;
    if (/^\d{6}$/.test(text)) {
        if (/^[568]/.test(text))
            return `sh${text}`;
        if (/^9/.test(text))
            return `bj${text}`;
        return `sz${text}`;
    }
    return null;
}
function readExtensionConfig() {
    const c = vscode.workspace.getConfiguration('stockAnalysis');
    const rawAlarms = c.get('priceAlarms', []);
    const priceAlarms = [];
    for (const item of rawAlarms) {
        if (!item || typeof item !== 'object')
            continue;
        const row = item;
        const code = normalizeStockCode(String(row.code ?? ''));
        const price = Number(row.price);
        const direction = row.direction === 'below' ? 'below' : 'above';
        if (!code || !Number.isFinite(price) || price <= 0)
            continue;
        priceAlarms.push({ code, price, direction });
    }
    const rawStocks = c.get('stocks', []);
    const stocks = rawStocks
        .map(s => normalizeStockCode(s))
        .filter((s) => !!s);
    const rawMini = c.get('stockMiniNames', {});
    const stockMiniNames = {};
    for (const [k, v] of Object.entries(rawMini)) {
        const code = normalizeStockCode(k);
        if (code && v?.trim())
            stockMiniNames[code] = v.trim();
    }
    return {
        backendUrl: (0, panel_1.normalizeBackendUrl)(c.get('backendUrl', 'https://www.stockai.xin/')),
        refreshInterval: Math.max(3000, c.get('refreshInterval', 5000)),
        stocks,
        priceAlarms,
        maxDisplayCount: Math.max(1, c.get('maxDisplayCount', 5)),
        showMiniName: c.get('showMiniName', false),
        stockMiniNames,
        showChangeValue: c.get('showChangeValue', false),
        autoHideByMarket: c.get('autoHideByMarket', false),
        showLockCount: c.get('showLockCount', false),
        enableLockTip: c.get('enableLockTip', true),
        enableLargeTip: c.get('enableLargeTip', false),
        sealDropPercent: Math.max(5, c.get('sealDropPercent', 30)),
        sealDropMinVol: Math.max(0, c.get('sealDropMinVol', 10000)),
        sealDropCooldownSec: Math.max(10, c.get('sealDropCooldownSec', 60)),
        largeTipMinAmountWan: Math.max(10, c.get('largeTipMinAmountWan', 300)),
        largeTipCooldownSec: Math.max(10, c.get('largeTipCooldownSec', 60)),
    };
}
function toStatusDisplayConfig(cfg) {
    return {
        maxDisplayCount: cfg.maxDisplayCount,
        showMiniName: cfg.showMiniName,
        stockMiniNames: cfg.stockMiniNames,
        showChangeValue: cfg.showChangeValue,
        showLockCount: cfg.showLockCount,
        autoHideByMarket: cfg.autoHideByMarket,
    };
}
//# sourceMappingURL=config.js.map