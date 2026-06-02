import * as vscode from 'vscode';
import { StockManager } from './stockManager';
import { StockQuote } from './sinaApi';

export class AlertManager {
  constructor(private readonly stockManager: StockManager) {}

  async check(quotes: StockQuote[]): Promise<void> {
    for (const stock of this.stockManager.getAll()) {
      const q = quotes.find(x => x.code === stock.code);
      if (!q || q.price <= 0) continue;

      await this.checkPriceAlert(stock.code, stock.name, q);
      await this.checkSealAlert(stock.code, stock.name, q);
    }
  }

  private async checkPriceAlert(code: string, name: string, q: StockQuote): Promise<void> {
    const stock = this.stockManager.getAll().find(s => s.code === code);
    if (!stock?.alertPrice || !stock.alertDirection || stock.alertTriggered) return;

    const hit =
      (stock.alertDirection === 'above' && q.price >= stock.alertPrice) ||
      (stock.alertDirection === 'below' && q.price <= stock.alertPrice);
    if (!hit) return;

    await this.stockManager.markAlertTriggered(code);

    const dir = stock.alertDirection === 'above' ? '涨至' : '跌至';
    const sign = q.percent >= 0 ? '+' : '';
    const msg = `🔔 ${name} 价格已${dir} ${stock.alertPrice}　当前: ${q.price}（${sign}${q.percent.toFixed(2)}%）`;

    const action = await vscode.window.showWarningMessage(msg, '查看详情', '清除闹钟');
    if (action === '清除闹钟') await this.stockManager.clearAlert(code);
    else if (action === '查看详情') vscode.commands.executeCommand('stockAnalysis.viewStock');
  }

  private async checkSealAlert(code: string, name: string, q: StockQuote): Promise<void> {
    const stock = this.stockManager.getAll().find(s => s.code === code);
    if (!stock?.sealAlertVol || !stock.sealAlertDirection || stock.sealAlertTriggered) return;
    // 封单只在涨停状态下有意义
    if (!q.isLimitUp || q.buy1Vol <= 0) return;

    const hit =
      (stock.sealAlertDirection === 'above' && q.buy1Vol >= stock.sealAlertVol) ||
      (stock.sealAlertDirection === 'below' && q.buy1Vol <= stock.sealAlertVol);
    if (!hit) return;

    await this.stockManager.markSealAlertTriggered(code);

    const dir = stock.sealAlertDirection === 'above' ? '超过' : '低于';
    const sealWan = (q.buy1Vol / 10000).toFixed(2);
    const sealAmt = (q.buy1Vol * q.buy1Price * 100 / 1e8).toFixed(2);
    const msg = `🔒 ${name} 封单量已${dir} ${(stock.sealAlertVol / 10000).toFixed(2)}万手　当前封单: ${sealWan}万手（${sealAmt}亿）`;

    const action = await vscode.window.showWarningMessage(msg, '查看详情', '清除预警');
    if (action === '清除预警') await this.stockManager.clearSealAlert(code);
    else if (action === '查看详情') vscode.commands.executeCommand('stockAnalysis.viewStock');
  }
}
