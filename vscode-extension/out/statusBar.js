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
exports.StatusBarManager = void 0;
const vscode = __importStar(require("vscode"));
class StatusBarManager {
    constructor(ctx) {
        this.visible = true;
        this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 1000);
        this.item.command = 'stockAnalysis.showMenu';
        ctx.subscriptions.push(this.item);
    }
    update(quotes) {
        if (!this.visible)
            return;
        if (quotes.length === 0) {
            this.item.text = '🔭 AI炒股看盘';
            this.item.tooltip = '点击打开菜单（或按 Ctrl+Alt+S）';
            this.item.show();
            return;
        }
        const parts = quotes.map(q => {
            const arrow = q.percent >= 0 ? '↗' : '↘';
            const sign = q.percent >= 0 ? '+' : '';
            const tag = q.isLimitUp ? '[涨停]' : q.isLimitDown ? '[跌停]' : '';
            return `${q.name} ${q.price} ${arrow}${sign}${q.percent.toFixed(2)}%${tag}`;
        });
        this.item.text = `$(graph-line) ${parts.join('  |  ')}`;
        this.item.tooltip = this.buildTooltip(quotes);
        this.item.show();
    }
    buildTooltip(quotes) {
        const md = new vscode.MarkdownString('', true);
        md.isTrusted = true;
        md.supportHtml = true;
        md.supportThemeIcons = true;
        const cells = quotes.map((q, index) => {
            const divider = index < quotes.length - 1
                ? 'border-right:1px solid rgba(128,128,128,0.35);'
                : '';
            return (`<td style="vertical-align:top;padding:0 14px;white-space:nowrap;${divider}">` +
                `${this.buildStockCardHtml(q)}</td>`);
        }).join('');
        md.appendMarkdown('<div style="overflow-x:auto;overflow-y:hidden;max-width:960px;padding-bottom:6px;' +
            '-webkit-overflow-scrolling:touch;">' +
            '<table style="border-collapse:collapse;width:max-content;"><tr>' +
            cells +
            '</tr></table></div>\n');
        return md;
    }
    buildStockCardHtml(q) {
        const sign = q.percent >= 0 ? '+' : '';
        const sealVol = q.isLimitUp && q.buy1Vol > 0
            ? `${(q.buy1Vol / 10000).toFixed(2)}万手`
            : '—';
        const sealAmt = q.isLimitUp && q.buy1Vol > 0 && q.buy1Price > 0
            ? `${(q.buy1Vol * q.buy1Price * 100 / 1e8).toFixed(2)}亿`
            : '—';
        const status = q.isLimitUp ? '🔒 涨停封板' : q.isLimitDown ? '🔓 跌停' : '正常';
        const name = this.escapeHtml(q.name);
        const code = this.escapeHtml(q.code.toUpperCase());
        return (`<div style="min-width:200px;max-width:260px;font-size:12px;line-height:1.5;">` +
            `<div style="font-weight:600;margin-bottom:4px;">${name} <code>${code}</code></div>` +
            `<div><strong>${q.price}</strong> ${sign}${q.updown} (${sign}${q.percent.toFixed(2)}%) ${status}</div>` +
            `<table style="margin-top:6px;font-size:11px;border-collapse:collapse;">` +
            `<tr><td style="opacity:0.75;padding-right:10px;">今开</td><td>${q.open}</td></tr>` +
            `<tr><td style="opacity:0.75;padding-right:10px;">最高</td><td>${q.high}</td></tr>` +
            `<tr><td style="opacity:0.75;padding-right:10px;">最低</td><td>${q.low}</td></tr>` +
            `<tr><td style="opacity:0.75;padding-right:10px;">昨收</td><td>${q.yestClose}</td></tr>` +
            `<tr><td style="opacity:0.75;padding-right:10px;">成交量</td><td>${(q.volume / 10000).toFixed(2)}万手</td></tr>` +
            `<tr><td style="opacity:0.75;padding-right:10px;">成交额</td><td>${(q.amount / 1e8).toFixed(2)}亿</td></tr>` +
            `<tr><td style="opacity:0.75;padding-right:10px;">封单量</td><td><strong>${sealVol}</strong></td></tr>` +
            `<tr><td style="opacity:0.75;padding-right:10px;">封单金额</td><td><strong>${sealAmt}</strong></td></tr>` +
            `</table>` +
            `<div style="margin-top:8px;">${this.buildFooterRow(q.time, q.code)}</div>` +
            `</div>`);
    }
    escapeHtml(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    /** 底部：左侧时间，右侧「查看分时图」可点击链接 */
    buildFooterRow(time, code) {
        const href = `command:stockAnalysis.viewStock?${encodeURIComponent(JSON.stringify([code]))}`;
        return (`<table style="width:100%"><tr>` +
            `<td><span style="opacity:0.85">${time}</span></td>` +
            `<td style="text-align:right"><a href="${href}">$(link-external) 查看分时图</a></td>` +
            `</tr></table>`);
    }
    setLoading() {
        if (!this.visible)
            return;
        this.item.text = '$(sync~spin) AI炒股看盘...';
        this.item.show();
    }
    toggle() {
        this.visible = !this.visible;
        this.visible ? this.item.show() : this.item.hide();
        return this.visible;
    }
    isVisible() {
        return this.visible;
    }
}
exports.StatusBarManager = StatusBarManager;
//# sourceMappingURL=statusBar.js.map