import * as vscode from 'vscode';
import { ExtensionConfig } from './config';
import { StockManager } from './stockManager';
import { StockQuote } from './sinaApi';

export class AlertManager {
  /** 上一轮封单量（手），用于检测环比大减 */
  private readonly lastSealVol = new Map<string, number>();
  /** 封单大减提醒冷却 */
  private readonly lastSealDropAlertAt = new Map<string, number>();
  /** 上一轮成交额（元），用于大单/成交额异动 */
  private readonly lastAmount = new Map<string, number>();
  private readonly lastLargeTipAlertAt = new Map<string, number>();

  constructor(private readonly stockManager: StockManager) {}

  async check(quotes: StockQuote[], cfg: ExtensionConfig): Promise<void> {
    for (const stock of this.stockManager.getAll()) {
      const q = quotes.find(x => x.code === stock.code);
      if (!q || q.price <= 0) continue;

      await this.checkPriceAlert(stock.code, stock.name, q);
      if (cfg.enableLockTip) {
        await this.checkSealAlert(stock.code, stock.name, q);
        await this.checkSealDropAlert(stock.code, stock.name, q, cfg);
      } else {
        this.lastSealVol.set(stock.code, q.buy1Vol);
      }
      if (cfg.enableLargeTip) {
        await this.checkLargeTip(stock.code, stock.name, q, cfg);
      } else {
        this.lastAmount.set(stock.code, q.amount);
      }
    }
  }

  /** 涨停封单较上一轮刷新大幅减少时提醒（开板风险） */
  private async checkSealDropAlert(
    code: string,
    name: string,
    q: StockQuote,
    cfg: ExtensionConfig,
  ): Promise<void> {
    if (!q.isLimitUp || q.buy1Vol <= 0) {
      this.lastSealVol.set(code, q.buy1Vol);
      return;
    }

    const prev = this.lastSealVol.get(code);
    this.lastSealVol.set(code, q.buy1Vol);

    if (prev == null || prev < cfg.sealDropMinVol) return;

    const dropVol = prev - q.buy1Vol;
    if (dropVol <= 0) return;

    const dropPct = (dropVol / prev) * 100;
    if (dropPct < cfg.sealDropPercent) return;

    const cooldownMs = cfg.sealDropCooldownSec * 1000;
    const lastAt = this.lastSealDropAlertAt.get(code) ?? 0;
    if (Date.now() - lastAt < cooldownMs) return;

    this.lastSealDropAlertAt.set(code, Date.now());

    const prevWan = (prev / 1e6).toFixed(2);
    const curWan = (q.buy1Vol / 1e6).toFixed(2);
    const sealAmt = (q.buy1Vol * q.buy1Price / 1e8).toFixed(2);
    const msg =
      `⚠️ ${name} 封单大减 ${dropPct.toFixed(1)}%　` +
      `${prevWan}万手 → ${curWan}万手（约 ${sealAmt}亿）`;

    const action = await vscode.window.showWarningMessage(msg, '查看详情', '知道了');
    if (action === '查看详情') vscode.commands.executeCommand('stockAnalysis.viewStock', code);
  }

  /** 单轮刷新成交额突增（万元） */
  private async checkLargeTip(
    code: string,
    name: string,
    q: StockQuote,
    cfg: ExtensionConfig,
  ): Promise<void> {
    const prev = this.lastAmount.get(code);
    this.lastAmount.set(code, q.amount);

    if (prev == null || prev <= 0) return;

    const deltaWan = (q.amount - prev) / 10000;
    if (deltaWan < cfg.largeTipMinAmountWan) return;

    const cooldownMs = cfg.largeTipCooldownSec * 1000;
    const lastAt = this.lastLargeTipAlertAt.get(code) ?? 0;
    if (Date.now() - lastAt < cooldownMs) return;

    this.lastLargeTipAlertAt.set(code, Date.now());

    const msg =
      `📈 ${name} 成交额异动 +${deltaWan.toFixed(0)}万　` +
      `本轮累计 ${(q.amount / 1e8).toFixed(2)}亿`;

    const action = await vscode.window.showWarningMessage(msg, '查看详情', '知道了');
    if (action === '查看详情') vscode.commands.executeCommand('stockAnalysis.viewStock', code);
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
    else if (action === '查看详情') vscode.commands.executeCommand('stockAnalysis.viewStock', code);
  }

  private async checkSealAlert(code: string, name: string, q: StockQuote): Promise<void> {
    const stock = this.stockManager.getAll().find(s => s.code === code);
    if (!stock?.sealAlertVol || !stock.sealAlertDirection || stock.sealAlertTriggered) return;
    if (!q.isLimitUp || q.buy1Vol <= 0) return;

    const hit =
      (stock.sealAlertDirection === 'above' && q.buy1Vol >= stock.sealAlertVol * 100) ||
      (stock.sealAlertDirection === 'below' && q.buy1Vol <= stock.sealAlertVol * 100);
    if (!hit) return;

    await this.stockManager.markSealAlertTriggered(code);

    const dir = stock.sealAlertDirection === 'above' ? '超过' : '低于';
    const sealWan = (q.buy1Vol / 1e6).toFixed(2);
    const sealAmt = (q.buy1Vol * q.buy1Price / 1e8).toFixed(2);
    const msg = `🔒 ${name} 封单量已${dir} ${(stock.sealAlertVol / 10000).toFixed(2)}万手　当前封单: ${sealWan}万手（${sealAmt}亿）`;

    const action = await vscode.window.showWarningMessage(msg, '查看详情', '清除预警');
    if (action === '清除预警') await this.stockManager.clearSealAlert(code);
    else if (action === '查看详情') vscode.commands.executeCommand('stockAnalysis.viewStock', code);
  }
}
