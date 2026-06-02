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
exports.toSixDigitCode = toSixDigitCode;
exports.buildViewStockUrl = buildViewStockUrl;
exports.openPanel = openPanel;
exports.openTimeshareInBrowser = openTimeshareInBrowser;
const vscode = __importStar(require("vscode"));
/** 将 sh603678 / sz000001 等格式转为 6 位代码 */
function toSixDigitCode(code) {
    const m = code.match(/(\d{6})/);
    return m ? m[1] : code;
}
/** 构建登录页 URL，登录后进入分时图（有股票时带 code 参数） */
function buildViewStockUrl(backendUrl, stockCode) {
    const base = backendUrl.replace(/\/$/, '');
    const six = stockCode ? toSixDigitCode(stockCode) : '';
    const next = six
        ? `/stock-dashboard?code=${encodeURIComponent(six)}`
        : '/stock-dashboard';
    return `${base}/login?next=${encodeURIComponent(next)}`;
}
async function openPanel(url) {
    try {
        // VS Code built-in Simple Browser — supports full HTTP pages including React SPAs
        await vscode.commands.executeCommand('simpleBrowser.show', url);
    }
    catch {
        // Fallback: open in system browser if Simple Browser unavailable
        await vscode.env.openExternal(vscode.Uri.parse(url));
    }
}
/** 在系统默认浏览器中打开分时图（登录后跳转 stock-dashboard） */
async function openTimeshareInBrowser(backendUrl, stockCode) {
    const url = buildViewStockUrl(backendUrl, stockCode);
    await vscode.env.openExternal(vscode.Uri.parse(url));
}
//# sourceMappingURL=panel.js.map