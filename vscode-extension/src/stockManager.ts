import * as vscode from 'vscode';
import { PriceAlarmSetting } from './config';

export interface StockItem {
  code: string;
  name: string;
  // 价格闹钟
  alertPrice?: number;
  alertDirection?: 'above' | 'below';
  alertTriggered?: boolean;
  // 封单量预警
  sealAlertVol?: number;
  sealAlertDirection?: 'above' | 'below';
  sealAlertTriggered?: boolean;
}

const KEY = 'stockAnalysis.stocks';

export class StockManager {
  constructor(private readonly ctx: vscode.ExtensionContext) {}

  getAll(): StockItem[] {
    return this.ctx.globalState.get<StockItem[]>(KEY, []);
  }

  /** 修正历史错误：sh0/1/2/3xxxxx → sz0/1/2/3xxxxx */
  async migrateWrongPrefixes(): Promise<void> {
    const list = this.getAll();
    let changed = false;
    for (const s of list) {
      if (/^sh[0123]\d{5}$/.test(s.code)) {
        s.code = 'sz' + s.code.slice(2);
        if (/^(sh|sz)\d{6}$/.test(s.name) || s.name === s.code.slice(2)) {
          s.name = s.code;
        }
        changed = true;
      }
    }
    if (changed) await this.ctx.globalState.update(KEY, list);
  }

  async add(stock: StockItem): Promise<boolean> {
    const list = this.getAll();
    if (list.some(s => s.code === stock.code)) return false;
    list.push(stock);
    await this.ctx.globalState.update(KEY, list);
    return true;
  }

  async remove(codes: string[]): Promise<void> {
    await this.ctx.globalState.update(KEY, this.getAll().filter(s => !codes.includes(s.code)));
  }

  async clear(): Promise<void> {
    await this.ctx.globalState.update(KEY, []);
  }

  async reorder(orderedCodes: string[]): Promise<void> {
    const map = new Map(this.getAll().map(s => [s.code, s]));
    const sorted = orderedCodes.map(c => map.get(c)).filter((s): s is StockItem => !!s);
    const rest = this.getAll().filter(s => !orderedCodes.includes(s.code));
    await this.ctx.globalState.update(KEY, [...sorted, ...rest]);
  }

  // ── 价格闹钟 ──────────────────────────────────────────────────────────────

  async setAlert(code: string, price: number, direction: 'above' | 'below'): Promise<void> {
    await this._update(code, s => { s.alertPrice = price; s.alertDirection = direction; s.alertTriggered = false; });
  }

  async clearAlert(code: string): Promise<void> {
    await this._update(code, s => { delete s.alertPrice; delete s.alertDirection; delete s.alertTriggered; });
  }

  async markAlertTriggered(code: string): Promise<void> {
    await this._update(code, s => { s.alertTriggered = true; });
  }

  // ── 封单量预警 ────────────────────────────────────────────────────────────

  async setSealAlert(code: string, vol: number, direction: 'above' | 'below'): Promise<void> {
    await this._update(code, s => { s.sealAlertVol = vol; s.sealAlertDirection = direction; s.sealAlertTriggered = false; });
  }

  async clearSealAlert(code: string): Promise<void> {
    await this._update(code, s => { delete s.sealAlertVol; delete s.sealAlertDirection; delete s.sealAlertTriggered; });
  }

  async markSealAlertTriggered(code: string): Promise<void> {
    await this._update(code, s => { s.sealAlertTriggered = true; });
  }

  /** 从 settings.json 同步股票列表与价格闹钟（仅新增/更新，不删除 UI 里已添加的） */
  async syncFromSettings(stocks: string[], priceAlarms: PriceAlarmSetting[]): Promise<void> {
    for (const code of stocks) {
      if (!this.getAll().some(s => s.code === code)) {
        await this.add({ code, name: code.toUpperCase() });
      }
    }
    for (const alarm of priceAlarms) {
      await this.setAlert(alarm.code, alarm.price, alarm.direction);
    }
  }

  // ── 从行情自动更新股票名称 ──────────────────────────────────────────────

  async updateNames(quoteMap: Map<string, string>): Promise<void> {
    const list = this.getAll();
    let changed = false;
    for (const s of list) {
      const name = quoteMap.get(s.code);
      if (name && name !== s.name) {
        s.name = name;
        changed = true;
      }
    }
    if (changed) await this.ctx.globalState.update(KEY, list);
  }

  private async _update(code: string, fn: (s: StockItem) => void): Promise<void> {
    const list = this.getAll();
    const s = list.find(x => x.code === code);
    if (s) { fn(s); await this.ctx.globalState.update(KEY, list); }
  }
}
