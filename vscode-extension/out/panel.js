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
exports.normalizeBackendUrl = normalizeBackendUrl;
exports.buildViewStockUrl = buildViewStockUrl;
exports.openPanel = openPanel;
const vscode = __importStar(require("vscode"));
/** 将 sh603678 / sz000001 等格式转为 6 位代码 */
function toSixDigitCode(code) {
    const m = code.match(/(\d{6})/);
    return m ? m[1] : code;
}
/** 线上 HTTPS 异常时回退 HTTP，避免 ERR_CONNECTION_CLOSED */
function normalizeBackendUrl(url) {
    const trimmed = url.trim().replace(/\/$/, '');
    if (/^https:\/\/(www\.)?stockai\.xin$/i.test(trimmed)) {
        return trimmed.replace(/^https:/i, 'http:');
    }
    return trimmed;
}
/** 构建分时图页面 URL（未登录时由前端 RequireAuth 跳转登录，并保留 code 参数） */
function buildViewStockUrl(backendUrl, stockCode) {
    const base = normalizeBackendUrl(backendUrl);
    const six = stockCode ? toSixDigitCode(stockCode) : '';
    return six ? `${base}/stock-dashboard?code=${six}` : `${base}/stock-dashboard`;
}
/** 在 Cursor / VS Code 内置 Simple Browser 中打开页面 */
async function openPanel(url) {
    try {
        await vscode.commands.executeCommand('simpleBrowser.show', url);
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`无法在编辑器内打开页面: ${msg}`);
    }
}
//# sourceMappingURL=panel.js.map