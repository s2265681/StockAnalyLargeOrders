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
        md.supportThemeIcons = true;
        for (const q of quotes) {
            const sign = q.percent >= 0 ? '+' : '';
            const sealVol = q.isLimitUp && q.buy1Vol > 0
                ? `${(q.buy1Vol / 10000).toFixed(2)}万手`
                : '—';
            const sealAmt = q.isLimitUp && q.buy1Vol > 0 && q.buy1Price > 0
                ? `${(q.buy1Vol * q.buy1Price * 100 / 1e8).toFixed(2)}亿`
                : '—';
            const status = q.isLimitUp ? '🔒 涨停封板' : q.isLimitDown ? '🔓 跌停' : '正常';
            md.appendMarkdown(`### ${q.name}  \`${q.code.toUpperCase()}\`\n`);
            md.appendMarkdown(`**${q.price}**　${sign}${q.updown}　(${sign}${q.percent.toFixed(2)}%)　${status}\n\n`);
            md.appendMarkdown(`| | |\n|---|---|\n`);
            md.appendMarkdown(`| 今开 | ${q.open} |\n`);
            md.appendMarkdown(`| 最高 | ${q.high} |\n`);
            md.appendMarkdown(`| 最低 | ${q.low} |\n`);
            md.appendMarkdown(`| 昨收 | ${q.yestClose} |\n`);
            md.appendMarkdown(`| 成交量 | ${(q.volume / 10000).toFixed(2)}万手 |\n`);
            md.appendMarkdown(`| 成交额 | ${(q.amount / 1e8).toFixed(2)}亿 |\n`);
            md.appendMarkdown(`| 封单量 | **${sealVol}** |\n`);
            md.appendMarkdown(`| 封单金额 | **${sealAmt}** |\n`);
            md.appendMarkdown(`\n*${q.time}*\n\n---\n\n`);
        }
        return md;
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