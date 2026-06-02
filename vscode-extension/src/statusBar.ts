import * as vscode from 'vscode';
import { StockQuote } from './sinaApi';

export class StatusBarManager {
  private item: vscode.StatusBarItem;
  private visible = true;

  constructor(ctx: vscode.ExtensionContext) {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 1000);
    this.item.command = 'stockAnalysis.showMenu';
    ctx.subscriptions.push(this.item);
  }

  update(quotes: StockQuote[]): void {
    if (!this.visible) return;

    if (quotes.length === 0) {
      this.item.text = '🔭 AI炒股看盘';
      this.item.tooltip = '点击打开菜单（或按 Ctrl+Alt+S）';
      this.item.show();
      return;
    }

    const parts = quotes.map(q => {
      const arrow = q.percent >= 0 ? '↗' : '↘';
      const sign  = q.percent >= 0 ? '+' : '';
      const tag   = q.isLimitUp ? '[涨停]' : q.isLimitDown ? '[跌停]' : '';
      return `${q.name} ${q.price} ${arrow}${sign}${q.percent.toFixed(2)}%${tag}`;
    });

    this.item.text = `$(graph-line) ${parts.join('  |  ')}`;
    this.item.tooltip = this.buildTooltip(quotes);
    this.item.show();
  }

  private buildTooltip(quotes: StockQuote[]): vscode.MarkdownString {
    const md = new vscode.MarkdownString('', true);
    md.isTrusted = true;
    md.supportHtml = true;
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
      md.appendMarkdown(`\n${this.buildFooterRow(q.time, q.code)}\n\n---\n\n`);
    }

    return md;
  }

  /** 底部：左侧时间，右侧「查看分时图」可点击链接 */
  private buildFooterRow(time: string, code: string): string {
    const href = `command:stockAnalysis.openTimeshareBrowser?${encodeURIComponent(JSON.stringify([code]))}`;
    return (
      `<table style="width:100%"><tr>` +
      `<td><span style="opacity:0.85">${time}</span></td>` +
      `<td style="text-align:right"><a href="${href}">$(link-external) 查看分时图</a></td>` +
      `</tr></table>`
    );
  }

  setLoading(): void {
    if (!this.visible) return;
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
