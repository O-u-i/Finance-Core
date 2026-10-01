export const views = {
  overview: ['Overview', { dashboard: '/dashboard', reconciliation: '/reconciliation', undo: '/undo/latest' }],
  journal: ['Journal', { drafts: '/journal-entry-drafts', entries: '/journal-entries', undo: '/undo/latest' }],
  taccounts: ['T-accounts', { tAccounts: '/t-accounts' }],
  positions: ['Securities & positions', { holdings: '/holdings' }],
  cashflow: ['Cash flow', { cashFlow: '/cash-flow' }],
  statements: ['Statements', { statements: '/financial-statements' }],
  planning: ['Living & plans', { living: '/living-accounts', snapshots: '/living-snapshots', plans: '/monthly-plans', world: '/world' }],
  data: ['Import & export', { recurring: '/recurring-entry-rules', drafts: '/journal-entry-drafts', undo: '/undo/latest' }],
  master: ['Master data', { quotes: '/price-quotes', undo: '/undo/latest' }],
  settings: ['Settings', {}],
};
export const mainViews = ['overview', 'journal', 'taccounts', 'positions', 'cashflow', 'statements', 'planning', 'data'];
export const configurationViews = ['master', 'settings'];

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
