import * as vscode from 'vscode';
import { StockManager } from './stockManager';
import { StatusBarManager } from './statusBar';
import { AlertManager } from './alertManager';
import { fetchQuotes, searchStock, StockQuote } from './sinaApi';
import { openPanel, buildViewStockUrl } from './panel';

export function activate(ctx: vscode.ExtensionContext): void {
  const log = vscode.window.createOutputChannel('AI炒股看盘');
  ctx.subscriptions.push(log);
  log.appendLine('[activate] 扩展启动');

  const stockManager = new StockManager(ctx);
  const statusBar    = new StatusBarManager(ctx);
  const alertManager = new AlertManager(stockManager);

  let timer: NodeJS.Timeout | undefined;
  let lastQuotes: StockQuote[] = [];

  function cfg() {
    const c = vscode.workspace.getConfiguration('stockAnalysis');
    return {
      backendUrl:      c.get<string>('backendUrl', 'https://www.stockai.xin/'),
      refreshInterval: Math.max(3000, c.get<number>('refreshInterval', 5000)),
    };
  }

  async function refresh(): Promise<void> {
    const stocks = stockManager.getAll();
    if (stocks.length === 0) { statusBar.update([]); return; }
    try {
      const quotes = await fetchQuotes(stocks.map(s => s.code));
      if (quotes.length > 0) {
        lastQuotes = quotes;
        await stockManager.updateNames(new Map(quotes.map(q => [q.code, q.name])));
        statusBar.update(quotes);
        await alertManager.check(quotes);
      }
    } catch { /* keep last display on network error */ }
  }

  function startTimer(): void {
    if (timer) clearInterval(timer);
    const { refreshInterval } = cfg();
    statusBar.setLoading();
    refresh();
    timer = setInterval(refresh, refreshInterval);
  }

  startTimer();

  // 首次激活时在状态栏显示提示，确认扩展已启动
  vscode.window.setStatusBarMessage('$(graph-line) AI炒股看盘 已启动', 4000);

  ctx.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(e => {
      if (e.affectsConfiguration('stockAnalysis.refreshInterval')) startTimer();
    })
  );

  // ── Helpers ──────────────────────────────────────────────────────────────

  // VS Code showQuickPick 通过 IPC 序列化 items，自定义属性会丢失。
  // 所有需要回传数据的场景改用 description 字段存储 key，再从原数组反查。

  function stocksAsItems() {
    return stockManager.getAll().map(s => {
      const q = lastQuotes.find(x => x.code === s.code);
      return {
        label:       s.name,
        description: s.code.toUpperCase(),
        detail:      q ? `当前 ${q.price}  ${q.percent >= 0 ? '+' : ''}${q.percent.toFixed(2)}%` : '',
      };
    });
  }

  function codeFromItem(item: { description?: string }): string | undefined {
    return item.description?.toLowerCase();
  }

  // ── Commands ───────────────────────────────────────────────────────────────

  async function cmdAddStock(): Promise<void> {
    const input = await vscode.window.showInputBox({
      prompt: '输入股票代码（如 603678）或名称关键字（如 火炬电子）',
      placeHolder: '代码 / 名称关键字',
      validateInput: v => v.trim() ? undefined : '不能为空',
      ignoreFocusOut: true,
    });
    if (!input) return;

    const keyword = input.trim();
    let selected: { code: string; name: string } | undefined;

    if (/^\d{6}$/.test(keyword)) {
      const prefix = /^[056]/.test(keyword) ? 'sh' : 'sz';
      const results = await searchStock(keyword);
      selected = results[0] ?? { code: `${prefix}${keyword}`, name: keyword };
    } else if (/^(sh|sz|bj)\d{6}$/i.test(keyword)) {
      const results = await searchStock(keyword.slice(2));
      selected = results[0] ?? { code: keyword.toLowerCase(), name: keyword.slice(2) };
    } else {
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `搜索 "${keyword}"...`, cancellable: false },
        async () => {
          const results = await searchStock(keyword);
          if (results.length === 0) {
            vscode.window.showWarningMessage(`未找到 "${keyword}" 相关股票`);
            return;
          }
          const items = results.map(r => ({ label: r.name, description: r.code.toUpperCase() }));
          const pick = await vscode.window.showQuickPick(items, { placeHolder: '选择股票', ignoreFocusOut: true });
          if (pick) {
            const code = pick.description.toLowerCase();
            const r = results.find(x => x.code === code);
            if (r) selected = { code: r.code, name: r.name };
          }
        }
      );
    }

    if (!selected) return;
    const added = await stockManager.add(selected);
    await refresh();
    vscode.window.showInformationMessage(
      added ? `✓ 已添加: ${selected.name} (${selected.code.toUpperCase()})` : `${selected.name} 已在列表中`
    );
  }

  async function cmdViewStock(preferredCode?: string): Promise<void> {
    const stocks = stockManager.getAll();
    const code = preferredCode ?? stocks[0]?.code;
    openPanel(buildViewStockUrl(cfg().backendUrl, code));
  }

  async function cmdRemoveStock(): Promise<void> {
    const stocks = stockManager.getAll();
    if (stocks.length === 0) { vscode.window.showInformationMessage('股票列表为空'); return; }

    const picks = await vscode.window.showQuickPick(
      stocksAsItems(),
      { placeHolder: '选择要移除的股票（可多选）', canPickMany: true, ignoreFocusOut: true }
    );
    if (!picks?.length) return;

    const codes = picks.map(p => codeFromItem(p)).filter((c): c is string => !!c);
    await stockManager.remove(codes);
    await refresh();
    vscode.window.showInformationMessage(`✓ 已移除 ${picks.length} 只股票`);
  }

  async function cmdSortStocks(): Promise<void> {
    const stocks = stockManager.getAll();
    if (stocks.length < 2) { vscode.window.showInformationMessage('至少需要 2 只股票才能排序'); return; }

    const picks = await vscode.window.showQuickPick(
      stocks.map((s, i) => ({
        label: s.name,
        description: s.code.toUpperCase(),
        detail: `当前第 ${i + 1} 位`,
      })),
      { placeHolder: '按新顺序依次选中股票', canPickMany: true, ignoreFocusOut: true }
    );
    if (!picks?.length) return;

    const codes = picks.map(p => codeFromItem(p)).filter((c): c is string => !!c);
    await stockManager.reorder(codes);
    await refresh();
    vscode.window.showInformationMessage('✓ 排序已更新');
  }

  async function cmdClearStocks(): Promise<void> {
    const stocks = stockManager.getAll();
    if (stocks.length === 0) { vscode.window.showInformationMessage('股票列表已为空'); return; }

    const ok = await vscode.window.showWarningMessage(
      `确定清空全部 ${stocks.length} 只股票？`, { modal: true }, '确定清空'
    );
    if (ok !== '确定清空') return;

    await stockManager.clear();
    await refresh();
    vscode.window.showInformationMessage('✓ 已清空股票列表');
  }

  async function cmdPriceAlert(): Promise<void> {
    const stocks = stockManager.getAll();
    if (stocks.length === 0) {
      const go = await vscode.window.showInformationMessage('请先添加股票', '去添加');
      if (go) cmdAddStock();
      return;
    }

    const stockItems = stocks.map(s => {
      const q  = lastQuotes.find(x => x.code === s.code);
      const pa = s.alertPrice   ? `⏰ ${s.alertDirection === 'above' ? '↗' : '↘'} ${s.alertPrice}${s.alertTriggered ? '（已触发）' : ''}` : '—';
      const sa = s.sealAlertVol ? `🔒 ${s.sealAlertDirection === 'above' ? '>' : '<'} ${(s.sealAlertVol / 10000).toFixed(1)}万手${s.sealAlertTriggered ? '（已触发）' : ''}` : '—';
      return {
        label:       s.name,
        description: s.code.toUpperCase(),
        detail:      `价格: ${q?.price ?? '—'}   价格闹钟: ${pa}   封单预警: ${sa}`,
      };
    });
    const stockPick = await vscode.window.showQuickPick(stockItems, { placeHolder: '选择要设置预警的股票', ignoreFocusOut: true });
    if (!stockPick) return;

    const code  = codeFromItem(stockPick)!;
    const stock = stocks.find(s => s.code === code)!;
    const q     = lastQuotes.find(x => x.code === code);

    const typeItems = [
      { label: '↗ 价格高于目标时提醒',    description: 'price_above' },
      { label: '↘ 价格低于目标时提醒',    description: 'price_below' },
      { label: '🔒 封单量高于阈值时提醒', description: 'seal_above'  },
      { label: '🔓 封单量低于阈值时提醒', description: 'seal_below', detail: '封单减少预警，仅涨停时有效' },
      { label: '✕ 清除所有预警',          description: 'clear'       },
    ];
    const typePick = await vscode.window.showQuickPick(typeItems, { placeHolder: '选择预警类型', ignoreFocusOut: true });
    if (!typePick) return;

    const typeId = typePick.description;

    if (typeId === 'clear') {
      await stockManager.clearAlert(code);
      await stockManager.clearSealAlert(code);
      vscode.window.showInformationMessage(`✓ 已清除 ${stock.name} 的所有预警`);
      return;
    }

    if (typeId === 'price_above' || typeId === 'price_below') {
      const priceStr = await vscode.window.showInputBox({
        prompt: `${stock.name} 目标价格${q ? `（当前: ${q.price}）` : ''}`,
        placeHolder: '输入目标价格',
        validateInput: v => (isNaN(parseFloat(v)) || parseFloat(v) <= 0) ? '请输入有效正数价格' : undefined,
        ignoreFocusOut: true,
      });
      if (!priceStr) return;
      await stockManager.setAlert(code, parseFloat(priceStr), typeId === 'price_above' ? 'above' : 'below');
      vscode.window.showInformationMessage(`✓ ${stock.name} 价格${typeId === 'price_above' ? '高于' : '低于'} ${priceStr} 时提醒`);
      return;
    }

    const curSeal = q?.isLimitUp && q.buy1Vol > 0 ? `当前封单 ${(q.buy1Vol / 10000).toFixed(2)}万手` : '仅涨停时触发';
    const volStr = await vscode.window.showInputBox({
      prompt: `${stock.name} 封单量阈值（${curSeal}）`,
      placeHolder: '输入手数，如 50000 表示 5万手',
      validateInput: v => (isNaN(parseInt(v)) || parseInt(v) <= 0) ? '请输入正整数（单位：手）' : undefined,
      ignoreFocusOut: true,
    });
    if (!volStr) return;
    await stockManager.setSealAlert(code, parseInt(volStr), typeId === 'seal_above' ? 'above' : 'below');
    vscode.window.showInformationMessage(
      `✓ ${stock.name} 封单量${typeId === 'seal_above' ? '超过' : '低于'} ${(parseInt(volStr) / 10000).toFixed(2)}万手 时提醒`
    );
  }

  async function cmdShowMenu(): Promise<void> {
    const nowVisible = statusBar.isVisible();

    const ACTIONS: { label: string; description: string; fn: () => void }[] = [
      { label: '$(add) 添加股票',        description: '输入股票代码或名称添加',    fn: cmdAddStock    },
      { label: '$(list-flat) 查看股票',  description: '登录后打开线上分时图',        fn: cmdViewStock   },
      { label: '$(remove) 移除股票',     description: '从已添加的股票中选择移除',  fn: cmdRemoveStock },
      { label: '$(arrow-swap) 排序股票', description: '调整股票的显示顺序',        fn: cmdSortStocks  },
      { label: '$(trash) 清空股票',      description: '清空所有已添加的股票',      fn: cmdClearStocks },
      { label: '$(bell) 价格/封单预警',  description: '价格或封单量达到目标时提醒', fn: cmdPriceAlert  },
      {
        label: `$(eye${nowVisible ? '-closed' : ''}) ${nowVisible ? '隐藏' : '显示'}状态栏`,
        description: '切换状态栏股票信息显示',
        fn: () => {
          const now = statusBar.toggle();
          vscode.window.showInformationMessage(now ? '✓ 已显示状态栏' : '✓ 已隐藏状态栏');
        },
      },
      {
        label: '$(refresh) 刷新行情',
        description: '手动刷新股票行情数据',
        fn: () => { refresh(); vscode.window.showInformationMessage('✓ 行情刷新中...'); },
      },
    ];

    const items = ACTIONS.map(a => ({ label: a.label, description: a.description }));
    const pick  = await vscode.window.showQuickPick(items, {
      placeHolder: '选择操作',
      matchOnDescription: true,
      ignoreFocusOut: true,   // 防止 macOS 点击状态栏后失焦导致 QuickPick 立即关闭
    });
    if (!pick) return;

    const action = ACTIONS.find(a => a.label === pick.label);
    action?.fn();
  }

  // ── Register ───────────────────────────────────────────────────────────────

  const cmds: [string, () => void][] = [
    ['stockAnalysis.showMenu',        cmdShowMenu],
    ['stockAnalysis.addStock',        cmdAddStock],
    ['stockAnalysis.viewStock',       cmdViewStock],
    ['stockAnalysis.removeStock',     cmdRemoveStock],
    ['stockAnalysis.sortStocks',      cmdSortStocks],
    ['stockAnalysis.clearStocks',     cmdClearStocks],
    ['stockAnalysis.priceAlert',      cmdPriceAlert],
    ['stockAnalysis.toggleStatusBar', () => {
      const now = statusBar.toggle();
      vscode.window.showInformationMessage(now ? '✓ 已显示状态栏' : '✓ 已隐藏状态栏');
    }],
    ['stockAnalysis.refreshData', () => {
      refresh();
      vscode.window.showInformationMessage('✓ 行情刷新中...');
    }],
  ];

  for (const [cmd, fn] of cmds) {
    ctx.subscriptions.push(vscode.commands.registerCommand(cmd, fn));
  }
}

export function deactivate(): void {}
