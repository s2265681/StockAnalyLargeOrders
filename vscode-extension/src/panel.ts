import * as vscode from 'vscode';

/** 将 sh603678 / sz000001 等格式转为 6 位代码 */
export function toSixDigitCode(code: string): string {
  const m = code.match(/(\d{6})/);
  return m ? m[1] : code;
}

/** 线上 HTTPS 异常时回退 HTTP，避免 ERR_CONNECTION_CLOSED */
export function normalizeBackendUrl(url: string): string {
  const trimmed = url.trim().replace(/\/$/, '');
  if (/^https:\/\/(www\.)?stockai\.xin$/i.test(trimmed)) {
    return trimmed.replace(/^https:/i, 'http:');
  }
  return trimmed;
}

/** 构建分时图页面 URL（未登录时由前端 RequireAuth 跳转登录，并保留 code 参数） */
export function buildViewStockUrl(backendUrl: string, stockCode?: string): string {
  const base = normalizeBackendUrl(backendUrl);
  const six = stockCode ? toSixDigitCode(stockCode) : '';
  return six ? `${base}/stock-dashboard?code=${six}` : `${base}/stock-dashboard`;
}

/** 在 Cursor / VS Code 内置 Simple Browser 中打开页面 */
export async function openPanel(url: string): Promise<void> {
  try {
    await vscode.commands.executeCommand('simpleBrowser.show', url);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    vscode.window.showErrorMessage(`无法在编辑器内打开页面: ${msg}`);
  }
}
