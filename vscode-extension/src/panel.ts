import * as vscode from 'vscode';

/** 将 sh603678 / sz000001 等格式转为 6 位代码 */
export function toSixDigitCode(code: string): string {
  const m = code.match(/(\d{6})/);
  return m ? m[1] : code;
}

/** 构建登录页 URL，登录后进入分时图（有股票时带 code 参数） */
export function buildViewStockUrl(backendUrl: string, stockCode?: string): string {
  const base = backendUrl.replace(/\/$/, '');
  const six = stockCode ? toSixDigitCode(stockCode) : '';
  const next = six
    ? `/stock-dashboard?code=${encodeURIComponent(six)}`
    : '/stock-dashboard';
  return `${base}/login?next=${encodeURIComponent(next)}`;
}

export async function openPanel(url: string): Promise<void> {
  try {
    // VS Code built-in Simple Browser — supports full HTTP pages including React SPAs
    await vscode.commands.executeCommand('simpleBrowser.show', url);
  } catch {
    // Fallback: open in system browser if Simple Browser unavailable
    await vscode.env.openExternal(vscode.Uri.parse(url));
  }
}
