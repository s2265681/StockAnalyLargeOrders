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

/** 根据 6 位代码推断正确市场前缀 */
function marketPrefixForDigits(digits: string): string {
  if (/^[568]/.test(digits)) return 'sh';
  if (/^9/.test(digits)) return 'bj';
  return 'sz';
}

/** 6 位或带市场前缀的股票代码 → sh/sz/bj 前缀小写（会纠正错误前缀，如 sh002855 → sz002855） */
export function normalizeStockCode(raw: string): string | null {
  const text = String(raw || '').trim().toLowerCase();
  if (!text) return null;

  let digits: string | null = null;
  if (/^(sh|sz|bj)(\d{6})$/.test(text)) {
    digits = text.slice(2);
  } else if (/^\d{6}$/.test(text)) {
    digits = text;
  }
  if (!digits) return null;

  return `${marketPrefixForDigits(digits)}${digits}`;
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
