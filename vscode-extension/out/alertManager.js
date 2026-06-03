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
exports.AlertManager = void 0;
const vscode = __importStar(require("vscode"));
class AlertManager {
    constructor(stockManager) {
        this.stockManager = stockManager;
        /** 上一轮封单量（手），用于检测环比大减 */
        this.lastSealVol = new Map();
        /** 封单大减提醒冷却 */
        this.lastSealDropAlertAt = new Map();
        /** 上一轮成交额（元），用于大单/成交额异动 */
        this.lastAmount = new Map();
        this.lastLargeTipAlertAt = new Map();
    }
    async check(quotes, cfg) {
        for (const stock of this.stockManager.getAll()) {
            const q = quotes.find(x => x.code === stock.code);
            if (!q || q.price <= 0)
                continue;
            await this.checkPriceAlert(stock.code, stock.name, q);
            if (cfg.enableLockTip) {
                await this.checkSealAlert(stock.code, stock.name, q);
                await this.checkSealDropAlert(stock.code, stock.name, q, cfg);
            }
            else {
                this.lastSealVol.set(stock.code, q.buy1Vol);
            }
            if (cfg.enableLargeTip) {
                await this.checkLargeTip(stock.code, stock.name, q, cfg);
            }
            else {
                this.lastAmount.set(stock.code, q.amount);
            }
        }
    }
    /** 涨停封单较上一轮刷新大幅减少时提醒（开板风险） */
    async checkSealDropAlert(code, name, q, cfg) {
        if (!q.isLimitUp || q.buy1Vol <= 0) {
            this.lastSealVol.set(code, q.buy1Vol);
            return;
        }
        const prev = this.lastSealVol.get(code);
        this.lastSealVol.set(code, q.buy1Vol);
        if (prev == null || prev < cfg.sealDropMinVol)
            return;
        const dropVol = prev - q.buy1Vol;
        if (dropVol <= 0)
            return;
        const dropPct = (dropVol / prev) * 100;
        if (dropPct < cfg.sealDropPercent)
            return;
        const cooldownMs = cfg.sealDropCooldownSec * 1000;
        const lastAt = this.lastSealDropAlertAt.get(code) ?? 0;
        if (Date.now() - lastAt < cooldownMs)
            return;
        this.lastSealDropAlertAt.set(code, Date.now());
        const prevWan = (prev / 10000).toFixed(2);
        const curWan = (q.buy1Vol / 10000).toFixed(2);
        const sealAmt = (q.buy1Vol * q.buy1Price * 100 / 1e8).toFixed(2);
        const msg = `⚠️ ${name} 封单大减 ${dropPct.toFixed(1)}%　` +
            `${prevWan}万手 → ${curWan}万手（约 ${sealAmt}亿）`;
        const action = await vscode.window.showWarningMessage(msg, '查看详情', '知道了');
        if (action === '查看详情')
            vscode.commands.executeCommand('stockAnalysis.viewStock', code);
    }
    /** 单轮刷新成交额突增（万元） */
    async checkLargeTip(code, name, q, cfg) {
        const prev = this.lastAmount.get(code);
        this.lastAmount.set(code, q.amount);
        if (prev == null || prev <= 0)
            return;
        const deltaWan = (q.amount - prev) / 10000;
        if (deltaWan < cfg.largeTipMinAmountWan)
            return;
        const cooldownMs = cfg.largeTipCooldownSec * 1000;
        const lastAt = this.lastLargeTipAlertAt.get(code) ?? 0;
        if (Date.now() - lastAt < cooldownMs)
            return;
        this.lastLargeTipAlertAt.set(code, Date.now());
        const msg = `📈 ${name} 成交额异动 +${deltaWan.toFixed(0)}万　` +
            `本轮累计 ${(q.amount / 1e8).toFixed(2)}亿`;
        const action = await vscode.window.showWarningMessage(msg, '查看详情', '知道了');
        if (action === '查看详情')
            vscode.commands.executeCommand('stockAnalysis.viewStock', code);
    }
    async checkPriceAlert(code, name, q) {
        const stock = this.stockManager.getAll().find(s => s.code === code);
        if (!stock?.alertPrice || !stock.alertDirection || stock.alertTriggered)
            return;
        const hit = (stock.alertDirection === 'above' && q.price >= stock.alertPrice) ||
            (stock.alertDirection === 'below' && q.price <= stock.alertPrice);
        if (!hit)
            return;
        await this.stockManager.markAlertTriggered(code);
        const dir = stock.alertDirection === 'above' ? '涨至' : '跌至';
        const sign = q.percent >= 0 ? '+' : '';
        const msg = `🔔 ${name} 价格已${dir} ${stock.alertPrice}　当前: ${q.price}（${sign}${q.percent.toFixed(2)}%）`;
        const action = await vscode.window.showWarningMessage(msg, '查看详情', '清除闹钟');
        if (action === '清除闹钟')
            await this.stockManager.clearAlert(code);
        else if (action === '查看详情')
            vscode.commands.executeCommand('stockAnalysis.viewStock', code);
    }
    async checkSealAlert(code, name, q) {
        const stock = this.stockManager.getAll().find(s => s.code === code);
        if (!stock?.sealAlertVol || !stock.sealAlertDirection || stock.sealAlertTriggered)
            return;
        if (!q.isLimitUp || q.buy1Vol <= 0)
            return;
        const hit = (stock.sealAlertDirection === 'above' && q.buy1Vol >= stock.sealAlertVol) ||
            (stock.sealAlertDirection === 'below' && q.buy1Vol <= stock.sealAlertVol);
        if (!hit)
            return;
        await this.stockManager.markSealAlertTriggered(code);
        const dir = stock.sealAlertDirection === 'above' ? '超过' : '低于';
        const sealWan = (q.buy1Vol / 10000).toFixed(2);
        const sealAmt = (q.buy1Vol * q.buy1Price * 100 / 1e8).toFixed(2);
        const msg = `🔒 ${name} 封单量已${dir} ${(stock.sealAlertVol / 10000).toFixed(2)}万手　当前封单: ${sealWan}万手（${sealAmt}亿）`;
        const action = await vscode.window.showWarningMessage(msg, '查看详情', '清除预警');
        if (action === '清除预警')
            await this.stockManager.clearSealAlert(code);
        else if (action === '查看详情')
            vscode.commands.executeCommand('stockAnalysis.viewStock', code);
    }
}
exports.AlertManager = AlertManager;
//# sourceMappingURL=alertManager.js.map