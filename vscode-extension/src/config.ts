import * as vscode from 'vscode';
import { normalizeBackendUrl } from './panel';

export interface PriceAlarmSetting {
  code: string;
  price: number;
  direction: 'above' | 'below';
}

export interface ExtensionConfig {
  backendUrl: string;
  refreshInterval: number;
  stocks: string[];
  priceAlarms: PriceAlarmSetting[];
  maxDisplayCount: number;
  showMiniName: boolean;
  stockMiniNames: Record<string, string>;
  showChangeValue: boolean;
  autoHideByMarket: boolean;
  showLockCount: boolean;
  enableLockTip: boolean;
  enableLargeTip: boolean;
  sealDropPercent: number;
  sealDropMinVol: number;
  sealDropCooldownSec: number;
  largeTipMinAmountWan: number;
  largeTipCooldownSec: number;
}

export interface StatusDisplayConfig {
  maxDisplayCount: number;
  showMiniName: boolean;
  stockMiniNames: Record<string, string>;
  showChangeValue: boolean;
  showLockCount: boolean;
  autoHideByMarket: boolean;
}

/** 6 位或带市场前缀的股票代码 → sh/sz/bj 前缀小写 */
export function normalizeStockCode(raw: string): string | null {
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

export function readExtensionConfig(): ExtensionConfig {
  const c = vscode.workspace.getConfiguration('stockAnalysis');
  const rawAlarms = c.get<unknown[]>('priceAlarms', []);
  const priceAlarms: PriceAlarmSetting[] = [];
  for (const item of rawAlarms) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, unknown>;
    const code = normalizeStockCode(String(row.code ?? ''));
    const price = Number(row.price);
    const direction = row.direction === 'below' ? 'below' : 'above';
    if (!code || !Number.isFinite(price) || price <= 0) continue;
    priceAlarms.push({ code, price, direction });
  }

  const rawStocks = c.get<string[]>('stocks', []);
  const stocks = rawStocks
    .map(s => normalizeStockCode(s))
    .filter((s): s is string => !!s);

  const rawMini = c.get<Record<string, string>>('stockMiniNames', {});
  const stockMiniNames: Record<string, string> = {};
  for (const [k, v] of Object.entries(rawMini)) {
    const code = normalizeStockCode(k);
    if (code && v?.trim()) stockMiniNames[code] = v.trim();
  }

  return {
    backendUrl: normalizeBackendUrl(c.get<string>('backendUrl', 'https://www.stockai.xin/')),
    refreshInterval: Math.max(3000, c.get<number>('refreshInterval', 5000)),
    stocks,
    priceAlarms,
    maxDisplayCount: Math.max(1, c.get<number>('maxDisplayCount', 5)),
    showMiniName: c.get<boolean>('showMiniName', false),
    stockMiniNames,
    showChangeValue: c.get<boolean>('showChangeValue', false),
    autoHideByMarket: c.get<boolean>('autoHideByMarket', false),
    showLockCount: c.get<boolean>('showLockCount', false),
    enableLockTip: c.get<boolean>('enableLockTip', true),
    enableLargeTip: c.get<boolean>('enableLargeTip', false),
    sealDropPercent: Math.max(5, c.get<number>('sealDropPercent', 30)),
    sealDropMinVol: Math.max(0, c.get<number>('sealDropMinVol', 10000)),
    sealDropCooldownSec: Math.max(10, c.get<number>('sealDropCooldownSec', 60)),
    largeTipMinAmountWan: Math.max(10, c.get<number>('largeTipMinAmountWan', 300)),
    largeTipCooldownSec: Math.max(10, c.get<number>('largeTipCooldownSec', 60)),
  };
}

export function toStatusDisplayConfig(cfg: ExtensionConfig): StatusDisplayConfig {
  return {
    maxDisplayCount: cfg.maxDisplayCount,
    showMiniName: cfg.showMiniName,
    stockMiniNames: cfg.stockMiniNames,
    showChangeValue: cfg.showChangeValue,
    showLockCount: cfg.showLockCount,
    autoHideByMarket: cfg.autoHideByMarket,
  };
}
