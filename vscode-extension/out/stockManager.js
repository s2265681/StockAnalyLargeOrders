"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.StockManager = void 0;
const KEY = 'stockAnalysis.stocks';
class StockManager {
    constructor(ctx) {
        this.ctx = ctx;
    }
    getAll() {
        return this.ctx.globalState.get(KEY, []);
    }
    async add(stock) {
        const list = this.getAll();
        if (list.some(s => s.code === stock.code))
            return false;
        list.push(stock);
        await this.ctx.globalState.update(KEY, list);
        return true;
    }
    async remove(codes) {
        await this.ctx.globalState.update(KEY, this.getAll().filter(s => !codes.includes(s.code)));
    }
    async clear() {
        await this.ctx.globalState.update(KEY, []);
    }
    async reorder(orderedCodes) {
        const map = new Map(this.getAll().map(s => [s.code, s]));
        const sorted = orderedCodes.map(c => map.get(c)).filter((s) => !!s);
        const rest = this.getAll().filter(s => !orderedCodes.includes(s.code));
        await this.ctx.globalState.update(KEY, [...sorted, ...rest]);
    }
    // ── 价格闹钟 ──────────────────────────────────────────────────────────────
    async setAlert(code, price, direction) {
        await this._update(code, s => { s.alertPrice = price; s.alertDirection = direction; s.alertTriggered = false; });
    }
    async clearAlert(code) {
        await this._update(code, s => { delete s.alertPrice; delete s.alertDirection; delete s.alertTriggered; });
    }
    async markAlertTriggered(code) {
        await this._update(code, s => { s.alertTriggered = true; });
    }
    // ── 封单量预警 ────────────────────────────────────────────────────────────
    async setSealAlert(code, vol, direction) {
        await this._update(code, s => { s.sealAlertVol = vol; s.sealAlertDirection = direction; s.sealAlertTriggered = false; });
    }
    async clearSealAlert(code) {
        await this._update(code, s => { delete s.sealAlertVol; delete s.sealAlertDirection; delete s.sealAlertTriggered; });
    }
    async markSealAlertTriggered(code) {
        await this._update(code, s => { s.sealAlertTriggered = true; });
    }
    /** 从 settings.json 同步股票列表与价格闹钟（仅新增/更新，不删除 UI 里已添加的） */
    async syncFromSettings(stocks, priceAlarms) {
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
    async updateNames(quoteMap) {
        const list = this.getAll();
        let changed = false;
        for (const s of list) {
            const name = quoteMap.get(s.code);
            if (name && name !== s.name) {
                s.name = name;
                changed = true;
            }
        }
        if (changed)
            await this.ctx.globalState.update(KEY, list);
    }
    async _update(code, fn) {
        const list = this.getAll();
        const s = list.find(x => x.code === code);
        if (s) {
            fn(s);
            await this.ctx.globalState.update(KEY, list);
        }
    }
}
exports.StockManager = StockManager;
//# sourceMappingURL=stockManager.js.map