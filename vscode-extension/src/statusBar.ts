import * as vscode from 'vscode';
import { StatusDisplayConfig } from './config';
import { isAShareMarketOpen } from './marketHours';
import { StockQuote } from './sinaApi';

export class StatusBarManager {
  private item: vscode.StatusBarItem;
  private visible = true;
  private displayConfig: StatusDisplayConfig = {
    maxDisplayCount: 5,
    showMiniName: false,
    stockMiniNames: {},
    showChangeValue: false,
    showLockCount: false,
    autoHideByMarket: false,
  };

  constructor(ctx: vscode.ExtensionContext) {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 1000);
    this.item.command = 'stockAnalysis.showMenu';
    ctx.subscriptions.push(this.item);
  }

  setDisplayConfig(config: StatusDisplayConfig): void {
    this.displayConfig = config;
  }

  private displayName(q: StockQuote): string {
    const { showMiniName, stockMiniNames } = this.displayConfig;
    const custom = stockMiniNames[q.code];
    if (custom) return custom;
    if (showMiniName) return q.name.slice(0, 2);
    return q.name;
  }

  private formatStatusSegment(q: StockQuote): string {
    const name = this.displayName(q);
    const arrow = q.percent >= 0 ? '↗' : '↘';
    const sign = q.percent >= 0 ? '+' : '';
    const tag = q.isLimitUp ? '[涨停]' : q.isLimitDown ? '[跌停]' : '';

    const changePart = this.displayConfig.showChangeValue
      ? ` ${sign}${q.updown.toFixed(2)}`
      : '';

    const lockPart =
      this.displayConfig.showLockCount && q.isLimitUp && q.buy1Vol > 0
        ? ` 封${(q.buy1Vol / 1e6).toFixed(1)}万`
        : '';

    return `${name} ${q.price}${changePart} ${arrow}${sign}${q.percent.toFixed(2)}%${tag}${lockPart}`;
  }

  update(quotes: StockQuote[]): void {
    if (!this.visible) return;

    if (this.displayConfig.autoHideByMarket && !isAShareMarketOpen()) {
      this.item.hide();
      return;
    }

    if (quotes.length === 0) {
      this.item.text = '🔭 AI炒股看盘';
      this.item.tooltip = '点击打开菜单（或按 Ctrl+Alt+S）';
      this.item.show();
      return;
    }

    const limited = quotes.slice(0, this.displayConfig.maxDisplayCount);
    const parts = limited.map(q => this.formatStatusSegment(q));
    const more = quotes.length > limited.length ? ` +${quotes.length - limited.length}` : '';

    this.item.text = `$(graph-line) ${parts.join('  |  ')}${more}`;
    this.item.tooltip = this.buildTooltip(quotes);
    this.item.show();
  }

  private buildTooltip(quotes: StockQuote[]): vscode.MarkdownString {
    const md = new vscode.MarkdownString('', true);
    md.isTrusted = true;
    md.supportHtml = true;
    md.supportThemeIcons = true;

    const cells = quotes.map((q, index) => {
      const divider = index < quotes.length - 1
        ? 'border-right:1px solid rgba(128,128,128,0.35);'
        : '';
      return (
        `<td style="vertical-align:top;padding:0 14px;white-space:nowrap;min-width:max-content;${divider}">` +
        `${this.buildStockCardHtml(q)}</td>`
      );
    }).join('');

    md.appendMarkdown(
      '<div style="overflow-x:auto;overflow-y:hidden;max-width:960px;padding-bottom:6px;' +
      '-webkit-overflow-scrolling:touch;">' +
      '<table style="border-collapse:collapse;width:max-content;"><tr>' +
      cells +
      '</tr></table></div>\n'
    );

    return md;
  }

  private buildStockCardHtml(q: StockQuote): string {
    const sign = q.percent >= 0 ? '+' : '';
    const sealVol = q.isLimitUp && q.buy1Vol > 0
      ? `${(q.buy1Vol / 1e6).toFixed(2)}万手`
      : '—';
    const sealAmt = q.isLimitUp && q.buy1Vol > 0 && q.buy1Price > 0
      ? `${(q.buy1Vol * q.buy1Price / 1e8).toFixed(2)}亿`
      : '—';
    const sealRatio = q.isLimitUp && q.buy1Vol > 0 && q.buy1Price > 0 && q.amount > 0
      ? `${(q.buy1Vol * q.buy1Price / q.amount * 100).toFixed(1)}%`
      : '—';
    const status = q.isLimitUp ? '🔒 涨停封板' : q.isLimitDown ? '🔓 跌停' : '正常';
    const name = this.escapeHtml(this.displayName(q));
    const code = this.escapeHtml(q.code.toUpperCase());

    const metricRow = (label: string, value: string) => (
      `<div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;white-space:nowrap;">` +
      `<span style="opacity:0.75;flex-shrink:0;">${label}</span>` +
      `<span style="flex-shrink:0;text-align:right;">${value}</span>` +
      `</div>`
    );

    return (
      `<div style="min-width:168px;font-size:12px;line-height:1.6;">` +
      `<div style="font-weight:600;margin-bottom:4px;white-space:nowrap;">${name} <code>${code}</code></div>` +
      `<div style="white-space:nowrap;"><strong>${q.price}</strong> ${sign}${q.updown} (${sign}${q.percent.toFixed(2)}%) ${status}</div>` +
      `<div style="margin-top:6px;font-size:11px;display:flex;flex-direction:column;gap:2px;">` +
      metricRow('今开', `${q.open}`) +
      metricRow('最高', `${q.high}`) +
      metricRow('最低', `${q.low}`) +
      metricRow('昨收', `${q.yestClose}`) +
      metricRow('成交量', `${(q.volume / 10000).toFixed(2)}万手`) +
      metricRow('成交额', `${(q.amount / 1e8).toFixed(2)}亿`) +
      metricRow('封单量', `<strong>${sealVol}</strong>`) +
      metricRow('封单金额', `<strong>${sealAmt}</strong>`) +
      metricRow('封成比', `<strong>${sealRatio}</strong>`) +
      `</div>` +
      `<div style="margin-top:8px;">${this.buildFooterRow(q.time, q.code)}</div>` +
      `</div>`
    );
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /** 底部：左侧时间，右侧「查看分时图」可点击链接 */
  private buildFooterRow(time: string, code: string): string {
    const href = `command:stockAnalysis.viewStock?${encodeURIComponent(JSON.stringify([code]))}`;
    return (
      `<table style="width:100%"><tr>` +
      `<td><span style="opacity:0.85">${time}</span></td>` +
      `<td style="text-align:right"><a href="${href}">$(link-external) 查看分时图</a></td>` +
      `</tr></table>`
    );
  }

  setLoading(): void {
    if (!this.visible) return;
    if (this.displayConfig.autoHideByMarket && !isAShareMarketOpen()) {
      this.item.hide();
      return;
    }
    this.item.text = '$(sync~spin) AI炒股看盘...';
    this.item.show();
  }

  toggle(): boolean {
    this.visible = !this.visible;
    this.visible ? this.item.show() : this.item.hide();
    return this.visible;
  }

  isVisible(): boolean {
    return this.visible;
  }
}
