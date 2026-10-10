export const views = {
  overview: ['Overview', { dashboard: '/dashboard', reconciliation: '/reconciliation', undo: '/undo/latest' }],
  journal: ['Journal', { drafts: '/journal-entry-drafts', entries: '/journal-entries', undo: '/undo/latest' }],
  taccounts: ['T-accounts', { tAccounts: '/t-accounts' }],
  positions: ['Securities & positions', { holdings: '/holdings' }],
  cashflow: ['Cash flow', { cashFlow: '/cash-flow' }],
  statements: ['Statements', { statements: '/financial-statements' }],
  monthlyreview: ['Monthly review', {}],
  planning: ['Living & plans', { living: '/living-accounts', snapshots: '/living-snapshots', plans: '/monthly-plans', world: '/world' }],
  data: ['Import & export', { recurring: '/recurring-entry-rules', drafts: '/journal-entry-drafts', undo: '/undo/latest' }],
  master: ['Master data', { quotes: '/price-quotes', undo: '/undo/latest' }],
  settings: ['Settings', {}],
};
export const mainViews = ['overview', 'journal', 'taccounts', 'positions', 'cashflow', 'statements', 'monthlyreview', 'planning', 'data'];
export const configurationViews = ['master', 'settings'];

export function latestCompletedMonth(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit' }).formatToParts(now);
  const year = Number(parts.find(part => part.type === 'year').value), month = Number(parts.find(part => part.type === 'month').value);
  return `${month === 1 ? year - 1 : year}-${String(month === 1 ? 12 : month - 1).padStart(2, '0')}`;
}

export function viewPaths(view, tab = '', now = new Date()) {
  if (view !== 'monthlyreview') return views[view][1];
  const month = /^[0-9]{4}-(0[1-9]|1[0-2])$/.test(tab) ? tab : latestCompletedMonth(now);
  return { monthlyReview: `/reports/monthly-review?month=${month}` };
}

export function parseRoute(hash = globalThis.location?.hash || '') {
  let [view, tab] = hash.replace(/^#\/?/, '').split('/');
  if (view === 'reports') {
    view = ({ holdings: 'positions', accounts: 'taccounts', 'cash-flow': 'cashflow', statements: 'statements' })[tab] || 'positions';
    tab = '';
  }
  return { view: Object.hasOwn(views, view) ? view : 'overview', tab: tab || '' };
}

// Configuration readiness describes available records; financial validation stays on the backend.
export function assessSetup({ loaded, workspace, actor, commodities = [], accounts = [] }) {
  const sessionReady = actor?.actorKind === 'session' && actor.status === 'active';
  const workspaceReady = !!workspace && ['active', 'archived'].includes(workspace.status);
  const currencies = commodities.filter(item => item.status === 'active' && item.kind === 'currency');
  const activeAccounts = accounts.filter(item => item.status === 'active');
  const usableCurrency = currencies.find(currency => activeAccounts.filter(account => account.allowedCommodityCodes?.includes(currency.code)).length >= 2);
  const masterReady = !!loaded && !!usableCurrency;
  return { loaded: !!loaded, sessionReady, workspaceReady, masterReady, ready: sessionReady && workspaceReady && masterReady,
    currencyCount: currencies.length, accountCount: activeAccounts.length,
    missing: [!sessionReady && 'An authenticated owner session is required.', !workspaceReady && 'Select an available Workspace in Settings.',
      !loaded && 'Configuration has not been checked yet.', loaded && !currencies.length && 'Add at least one active currency in Master data.',
      loaded && !usableCurrency && 'Add at least two active accounts that support the same active currency.'].filter(Boolean) };
}
