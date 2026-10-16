export const views = {
  overview: ['Overview', {}],
  journal: ['Journal', { drafts: '/journal-entry-drafts', entries: '/journal-entries', undo: '/undo/latest' }],
  taccounts: ['T-accounts', { tAccounts: '/t-accounts' }],
  positions: ['Securities & positions', {}],
  cashflow: ['Cash flow', { cashFlow: '/cash-flow' }],
  statements: ['Statements', { statements: '/financial-statements' }],
  monthlyreview: ['Monthly review', {}],
  legacyreview: ['Journal activity review', {}],
  balances: ['Accounts & balances', {}],
  assets: ['Assets & liabilities', {}],
  plans: ['Monthly plans', { plans: '/monthly-plans' }],
  livingreview: ['Monthly review', {}],
  livingdata: ['Import & export', {}],
  planning: ['Living & plans', { living: '/living-accounts', snapshots: '/living-snapshots', plans: '/monthly-plans', world: '/world' }],
  data: ['Import & export', { recurring: '/recurring-entry-rules', drafts: '/journal-entry-drafts', undo: '/undo/latest' }],
  master: ['Master data', { quotes: '/price-quotes', undo: '/undo/latest' }],
  settings: ['Settings', {}],
};
export const segmentViews = {
  investment: ['journal', 'taccounts', 'positions', 'cashflow', 'statements', 'monthlyreview', 'data'],
  living: ['balances', 'assets', 'plans', 'livingreview', 'livingdata'],
};
export const configurationViews = ['overview', 'master', 'settings'];

export function latestCompletedMonth(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit' }).formatToParts(now);
  const year = Number(parts.find(part => part.type === 'year').value), month = Number(parts.find(part => part.type === 'month').value);
  return `${month === 1 ? year - 1 : year}-${String(month === 1 ? 12 : month - 1).padStart(2, '0')}`;
}

export function selectedMonth(route, now = new Date()) {
  const month = route.month || route.tab;
  return /^[0-9]{4}-(0[1-9]|1[0-2])$/.test(month) ? month : latestCompletedMonth(now);
}

export function shanghaiDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  return ['year', 'month', 'day'].map(type => parts.find(part => part.type === type).value).join('-');
}

export function selectedRecordedMonth(route, now = new Date()) {
  const month = route.month || route.tab;
  return /^[0-9]{4}-(0[1-9]|1[0-2])$/.test(month) ? month : shanghaiDate(now).slice(0, 7);
}

export function viewPaths(view, tab = '', now = new Date(), segment = '', asOfMonth = '') {
  const month = selectedMonth({ tab, month: asOfMonth }, now);
  if (view === 'legacyreview' || (view === 'monthlyreview' && !segment)) return { monthlyReview: `/reports/${segment ? 'monthly-activity-review' : 'monthly-review'}?month=${month}` };
  const personal = { financialAccounts: '/financial-accounts', parties: '/finance-parties', financeSettings: '/personal-finance-settings' };
  const recordedMonth = selectedRecordedMonth({ tab, month: asOfMonth }, now);
  if (view === 'cashflow') return { activityCashFlow: `/reports/activity-cash-flow?month=${recordedMonth}` };
  const recorded = { balanceRecords: '/balance-records', recordedReport: `/reports/living-recorded-balances?month=${recordedMonth}` };
  if (view === 'overview') return { ...personal, entries: '/journal-entries', assets: '/non-financial-assets', observations: '/monthly-observations', personalReport: `/reports/personal-balance-sheet?month=${month}`, recordedReport: `/reports/living-recorded-balances?month=${month}` };
  if (view === 'master') return { ...views.master[1], ...personal, living: '/living-accounts', ...(tab === 'ownership' ? {
    legacyMapping: '/legacy-living-mapping', arrangements: '/investment-arrangements', personalReport: `/reports/personal-balance-sheet?month=${month}`,
  } : {}), ...(tab === 'opening' ? { openingRecords: '/opening-balances', balanceRecords: '/balance-records' } : {}) };
  if (view === 'balances') return { ...personal, ...recorded, observations: '/monthly-observations' };
  if (['assets','monthlyreview','livingreview','livingdata'].includes(view)) {
    const result = { ...views[view][1], ...personal, assets: '/non-financial-assets', observations: '/monthly-observations', arrangements: '/investment-arrangements', closes: '/monthly-closes' };
    const report = view === 'livingreview' ? 'living-monthly-review' : view === 'monthlyreview' ? 'investment-monthly-review' : 'personal-balance-sheet';
    result.personalReport = `/reports/${report}?month=${view === 'livingreview' ? recordedMonth : month}`;
    if (view === 'livingreview') Object.assign(result, recorded);
    return result;
  }
  if (view === 'planning') return { ...views.planning[1], planReport: `/reports/monthly-plans?month=${recordedMonth}` };
  if (view === 'plans') return { ...views[view][1], financialAccounts: '/financial-accounts', planReport: `/reports/monthly-plans?month=${recordedMonth}` };
  return views[view][1];
}

export function parseRoute(hash = globalThis.location?.hash || '') {
  let parts = hash.replace(/^#\/?/, '').split('/');
  const segment = ['investment','living'].includes(parts[0]) ? parts.shift() : '';
  let [view, tab, month] = parts;
  if (view === 'reports') {
    view = ({ holdings: 'positions', accounts: 'taccounts', 'cash-flow': 'cashflow', statements: 'statements' })[tab] || 'positions';
    tab = '';
  }
  const route = { view: Object.hasOwn(views, view) ? view : 'overview', tab: tab || '' };
  if (segment) route.segment = segment;
  if (month && /^[0-9]{4}-(0[1-9]|1[0-2])$/.test(month)) route.month = month;
  return route;
}

export function routeHash({ view, tab = '', segment = '', month = '' }) {
  const scoped = !configurationViews.includes(view) && segment;
  return `#/${scoped ? segment + '/' : ''}${view}${tab || month ? '/' + tab : ''}${month ? '/' + month : ''}`;
}

// Configuration readiness describes available records; financial validation stays on the backend.
export function assessSetup({ loaded, workspace, actor, commodities = [], accounts = [], financialAccounts = [] }) {
  const sessionReady = actor?.actorKind === 'session' && actor.status === 'active';
  const workspaceReady = !!workspace && ['active', 'archived'].includes(workspace.status);
  const currencies = commodities.filter(item => item.status === 'active' && item.kind === 'currency');
  const activeAccounts = accounts.filter(item => item.status === 'active');
  const usableCurrency = currencies.find(currency => activeAccounts.filter(account => account.allowedCommodityCodes?.includes(currency.code)).length >= 2 || financialAccounts.some(account => account.segment === 'living' && account.status === 'active' && account.allowedCommodityCodes?.includes(currency.code)));
  const masterReady = !!loaded && !!usableCurrency;
  return { loaded: !!loaded, sessionReady, workspaceReady, masterReady, ready: sessionReady && workspaceReady && masterReady,
    currencyCount: currencies.length, accountCount: financialAccounts.length || activeAccounts.length,
    missing: [!sessionReady && 'An authenticated owner session is required.', !workspaceReady && 'Select an available Workspace in Settings.',
      !loaded && 'Configuration has not been checked yet.', loaded && !currencies.length && 'Add at least one active currency in Master data.',
      loaded && !usableCurrency && 'Add two Investment ledger accounts for one active currency, or one registered monthly Living account.'].filter(Boolean) };
}
