import './style.css';

const app = document.querySelector('#app');
const REQUEST_TIMEOUT_MS = 5000;
const emptyDashboard = () => ({ commoditySummaries: [], draftCount: 0, entryCount: 0, openLotCount: 0 });
const emptyReconciliation = () => ({ status: 'checking', checks: [] });
const state = {
  active: 'overview', health: null, dashboard: emptyDashboard(), reconciliation: emptyReconciliation(),
  user: null, workspaces: [], workspace: null, busy: '', accessTokens: [], oneTimeToken: '', controlUndo: null,
  commodities: [], accounts: [], quotes: [], drafts: [], entries: [], holdings: [],
  statements: [], cashFlow: [], tAccounts: [], recurring: [], living: [], snapshots: [], plans: [], world: null, undo: null,
  message: '', error: '', editor: null, validation: null,
  refreshController: null, refreshGeneration: 0,
};

const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;',
}[character]));
const newId = (prefix) => `${prefix}-${crypto.randomUUID()}`;
const today = () => new Date().toISOString().slice(0, 10);
const downloadPath = (path) => `/api/v3/workspaces/${state.workspace.id}${path}`;

function clearWorkspaceData() {
  Object.assign(state, {
    dashboard: emptyDashboard(), reconciliation: emptyReconciliation(),
    commodities: [], accounts: [], quotes: [], drafts: [], entries: [], holdings: [],
    statements: [], cashFlow: [], tAccounts: [], recurring: [], living: [], snapshots: [], plans: [],
    world: null, undo: null, editor: null, validation: null,
  });
}

async function request(path, options = {}) {
  if (path.startsWith('/api/v2')) {
    if (!state.workspace) throw new Error('Create or select a workspace first.');
    path = `/api/v3/workspaces/${state.workspace.id}${path.slice('/api/v2'.length)}`;
  }
  const controller = new AbortController();
  let timedOut = false;
  const abortFromCaller = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  else options.signal?.addEventListener('abort', abortFromCaller, { once: true });
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, REQUEST_TIMEOUT_MS);
  const { signal: _callerSignal, ...fetchOptions } = options;
  let response;
  try {
    response = await fetch(path, {
      ...fetchOptions,
      signal: controller.signal,
      headers: { Accept: 'application/json', ...(fetchOptions.body ? { 'Content-Type': 'application/json' } : {}), ...fetchOptions.headers },
    });
  } catch (error) {
    if (timedOut) {
      const timeoutError = new Error(`Request ${path} exceeded ${REQUEST_TIMEOUT_MS / 1000} seconds. Check the FC backend terminal and /api/v3/health.`);
      timeoutError.code = 'REQUEST_TIMEOUT';
      throw timeoutError;
    }
    if (error.name === 'TypeError') {
      throw new Error('Cannot connect to the Finance Core backend. Check that npm.cmd run dev is running and inspect /api/v3/health.');
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener('abort', abortFromCaller);
  }
  const type = response.headers.get('content-type') || '';
  const body = type.includes('json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = body?.detail || body?.error?.message || `HTTP ${response.status}`;
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    error.status = response.status;
    error.code = body?.error?.code;
    throw error;
  }
  return body;
}

function blankDraft() {
  const commodity = state.commodities.find((item) => item.status === 'active')?.code || 'CNY';
  const accounts = state.accounts.filter((item) => item.status === 'active');
  const draftId = newId('draft');
  return {
    id: draftId, date: today(), description: '', payee: '', source: 'manual', reference: '', tags: [],
    balancingCommodityCode: commodity,
    postings: [0, 1].map((index) => ({
      id: `${draftId}-p${index + 1}`, accountId: accounts[index]?.id || '', side: index ? 'credit' : 'debit',
      units: '0', commodityCode: commodity, memo: '', cashFlowCategory: 'other', lotAllocations: [],
    })),
  };
}

const VIEW_PATHS = {
  overview: {
    health: '/api/v2/health', dashboard: '/api/v2/dashboard', reconciliation: '/api/v2/reconciliation', undo: '/api/v2/undo/latest',
  },
  transactions: {
    commodities: '/api/v2/commodities', accounts: '/api/v2/accounts', drafts: '/api/v2/journal-entry-drafts',
    entries: '/api/v2/journal-entries', undo: '/api/v2/undo/latest',
  },
  holdings: {
    holdings: '/api/v2/holdings', statements: '/api/v2/financial-statements', cashFlow: '/api/v2/cash-flow', tAccounts: '/api/v2/t-accounts',
  },
  world: {
    commodities: '/api/v2/commodities', living: '/api/v2/living-accounts', snapshots: '/api/v2/living-snapshots',
    plans: '/api/v2/monthly-plans', world: '/api/v2/world',
  },
  automation: {
    commodities: '/api/v2/commodities', accounts: '/api/v2/accounts', drafts: '/api/v2/journal-entry-drafts',
    recurring: '/api/v2/recurring-entry-rules', undo: '/api/v2/undo/latest',
  },
  master: {
    commodities: '/api/v2/commodities', accounts: '/api/v2/accounts', quotes: '/api/v2/price-quotes', undo: '/api/v2/undo/latest',
  },
  settings: {},
};

async function refresh(view = state.active) {
  if (!state.workspace) return false;
  state.refreshController?.abort();
  const controller = new AbortController();
  const generation = state.refreshGeneration + 1;
  const workspaceId = state.workspace.id;
  state.refreshController = controller;
  state.refreshGeneration = generation;
  const paths = VIEW_PATHS[view] || VIEW_PATHS.overview;
  let results;
  try {
    results = await Promise.all(Object.values(paths).map((path) => request(path, { signal: controller.signal })));
  } finally {
    if (state.refreshController === controller) state.refreshController = null;
  }
  if (generation !== state.refreshGeneration || workspaceId !== state.workspace?.id) return false;
  Object.keys(paths).forEach((key, index) => {
    state[key] = Object.prototype.hasOwnProperty.call(results[index], 'data') ? results[index].data : results[index];
  });
  if (!state.editor) state.editor = blankDraft();
  return true;
}

async function refreshControl() {
  state.workspaces = (await request('/api/v3/workspaces')).data;
  state.accessTokens = (await request('/api/v3/access-tokens')).data;
}

function nav() {
  const tabs = [
    ['overview', 'Overview'], ['transactions', 'Transactions'], ['holdings', 'Holdings & reports'],
    ['world', 'Living & plans'], ['automation', 'Automation & data'], ['master', 'Master data'], ['settings', 'Settings'],
  ];
  return `<nav>${tabs.map(([key, label]) => `<button class="tab ${state.active === key ? 'active' : ''}" data-tab="${key}">${label}</button>`).join('')}</nav>`;
}

function notice() {
  if (state.error) return `<div class="notice error">${esc(state.error)}</div>`;
  if (state.message) return `<div class="notice success">${esc(state.message)}</div>`;
  return '';
}

function overview() {
  const summary = state.dashboard.commoditySummaries || [];
  return `<section class="panel hero"><div><p class="eyebrow">LOCAL-FIRST · DETERMINISTIC · WORKSPACE-SCOPED</p><h2>${esc(state.workspace.displayName)} · Deterministic ledger status</h2><p>Finance Core runs all finance rules on the backend. This workspace is isolated from other Vaults.</p></div><div class="actions"><button id="refresh">Refresh</button><button id="undo-latest" ${state.undo ? '' : 'disabled'}>Undo latest operation</button>${state.workspace.kind === 'sandbox' ? '<button id="load-demo" class="primary">Load synthetic example</button>' : ''}</div></section>
  <section class="metrics"><article><span>Drafts</span><strong>${state.dashboard.draftCount}</strong></article><article><span>Posted</span><strong>${state.dashboard.entryCount}</strong></article><article><span>Open lots</span><strong>${state.dashboard.openLotCount}</strong></article><article><span>Reconciliation</span><strong class="${state.reconciliation.status}">${esc(state.reconciliation.status)}</strong></article></section>
  <section class="panel"><h3>Summary by commodity</h3>${summary.length ? `<div class="table-wrap"><table><thead><tr><th>Commodity</th><th>Cash</th><th>Cost</th><th>Market value</th><th>Unrealized P&L</th><th>Missing prices</th></tr></thead><tbody>${summary.map((item) => `<tr><td>${esc(item.commodityCode)}</td><td>${esc(item.cash)}</td><td>${esc(item.holdingCostBasis)}</td><td>${esc(item.marketValue)}</td><td>${esc(item.unrealizedPnL)}</td><td>${item.missingPriceCount}</td></tr>`).join('')}</tbody></table></div>` : '<p class="empty">No posted data yet.</p>'}</section>
  <section class="panel"><h3>Deterministic checks</h3><div class="check-grid">${state.reconciliation.checks.map((item) => `<article class="check ${item.status}"><strong>${esc(item.id)}</strong><span>${esc(item.detail)}</span></article>`).join('')}</div></section>`;
}

function commodityOptions(kind) {
  return state.commodities.filter((item) => item.status === 'active' && (!kind || item.kind === kind)).map((item) => `<option value="${esc(item.code)}">${esc(item.code)} · ${esc(item.name)}</option>`).join('');
}

function accountOptions(selected = '') {
  return state.accounts.filter((item) => item.status === 'active').map((item) => `<option value="${esc(item.id)}" ${item.id === selected ? 'selected' : ''}>${esc(item.code)} · ${esc(item.name)}</option>`).join('');
}

function masterData() {
  return `<div class="columns"><section class="panel"><h3>Commodity Registry</h3><form id="commodity-form" class="compact-form"><input name="code" placeholder="CNY" required><select name="kind"><option>currency</option><option>security</option><option>other</option></select><input name="scale" type="number" min="0" max="18" value="2" required><input name="name" placeholder="Name" required><button>Add</button></form><div class="list">${state.commodities.map((item) => `<article><div><strong>${esc(item.code)}</strong><small>${esc(item.kind)} · scale ${item.scale} · ${esc(item.status)}</small></div><button data-inactivate-commodity="${esc(item.code)}" ${item.status === 'inactive' ? 'disabled' : ''}>Deactivate</button></article>`).join('') || '<p class="empty">No commodities yet.</p>'}</div></section>
  <section class="panel"><h3>Typed accounts</h3><form id="account-form" class="compact-form"><input name="code" placeholder="1001" required><input name="name" placeholder="Account name" required><select name="type"><option>asset</option><option>liability</option><option>equity</option><option>income</option><option>expense</option></select><input name="subtype" placeholder="cash / investment"><select name="commodity">${commodityOptions()}</select><button>Add</button></form><div class="list">${state.accounts.map((item) => `<article><div><strong>${esc(item.code)} · ${esc(item.name)}</strong><small>${esc(item.type)}/${esc(item.subtype || 'general')} · ${esc(item.allowedCommodityCodes.join(', '))} · ${esc(item.status)}</small></div><button data-inactivate-account="${esc(item.id)}" ${item.status === 'inactive' ? 'disabled' : ''}>Deactivate</button></article>`).join('') || '<p class="empty">No accounts yet.</p>'}</div></section></div>
  <section class="panel"><h3>Explicit prices</h3><form id="quote-form" class="inline-form"><select name="commodityCode">${commodityOptions('security')}</select><select name="quoteCommodityCode">${commodityOptions('currency')}</select><input name="price" inputmode="decimal" placeholder="110.00" required><input name="asOf" type="datetime-local" required><input name="source" value="manual" required><button>Add price</button></form><div class="table-wrap"><table><thead><tr><th>Commodity</th><th>Quote commodity</th><th>Price</th><th>Time</th><th>Source</th><th></th></tr></thead><tbody>${state.quotes.map((item) => `<tr><td>${esc(item.commodityCode)}</td><td>${esc(item.quoteCommodityCode)}</td><td>${esc(item.price)}</td><td>${esc(item.asOf)}</td><td>${esc(item.source)}</td><td><button data-delete-quote="${esc(item.id)}">Delete</button></td></tr>`).join('')}</tbody></table></div></section>`;
}

function postingRow(item, index) {
  return `<tr data-posting="${index}"><td><select data-field="accountId">${accountOptions(item.accountId)}</select></td><td><select data-field="side"><option ${item.side === 'debit' ? 'selected' : ''}>debit</option><option ${item.side === 'credit' ? 'selected' : ''}>credit</option></select></td><td><input data-field="units" value="${esc(item.units)}" inputmode="decimal"></td><td><select data-field="commodityCode">${state.commodities.filter((value) => value.status === 'active').map((value) => `<option ${value.code === item.commodityCode ? 'selected' : ''}>${esc(value.code)}</option>`).join('')}</select></td><td><input data-field="valuationRate" value="${esc(item.valuationRate || '')}" inputmode="decimal" placeholder="base=1"></td><td><select data-field="rateType"><option value="">Automatic</option>${['exchange', 'price', 'cost'].map((value) => `<option ${value === item.rateType ? 'selected' : ''}>${value}</option>`).join('')}</select></td><td><select data-field="cashFlowCategory">${['income', 'expense', 'investment', 'financing', 'transfer', 'other'].map((value) => `<option ${value === item.cashFlowCategory ? 'selected' : ''}>${value}</option>`).join('')}</select></td><td><select data-field="lotAction"><option value="">None</option><option value="acquire" ${item.lotAction === 'acquire' ? 'selected' : ''}>acquire</option><option value="dispose" ${item.lotAction === 'dispose' ? 'selected' : ''}>dispose</option></select><input data-field="lotId" value="${esc(item.lotId || '')}" placeholder="acquire lotId"><input data-field="lotAllocations" value="${esc((item.lotAllocations || []).map((value) => `${value.lotId}:${value.units}`).join(','))}" placeholder="lotId:units"></td><td><button type="button" data-remove-posting="${index}">Remove</button></td></tr>`;
}

function drafts() {
  const editor = state.editor || blankDraft();
  const validation = state.validation;
  return `<section class="panel"><div class="section-title"><div><h3>JournalEntry Draft</h3><p>Drafts do not enter the ledger or reports. Decimal strings are sent unchanged to the backend.</p></div><button id="new-draft">New draft</button></div><form id="draft-form"><div class="form-grid"><label>ID<input name="id" value="${esc(editor.id)}" required></label><label>Date<input name="date" type="date" value="${esc(editor.date)}" required></label><label>Description<input name="description" value="${esc(editor.description)}" required></label><label>Payee<input name="payee" value="${esc(editor.payee)}"></label><label>Source<input name="source" value="${esc(editor.source)}"></label><label>Reference<input name="reference" value="${esc(editor.reference)}"></label><label>Balancing commodity<select name="balancingCommodityCode">${state.commodities.map((item) => `<option ${item.code === editor.balancingCommodityCode ? 'selected' : ''}>${esc(item.code)}</option>`).join('')}</select></label><label>Tags<input name="tags" value="${esc((editor.tags || []).join(', '))}"></label></div><div class="table-wrap postings"><table><thead><tr><th>Account</th><th>Side</th><th>Units</th><th>Commodity</th><th>Valuation rate</th><th>Type</th><th>Cash flow</th><th>Lot</th><th></th></tr></thead><tbody>${editor.postings.map(postingRow).join('')}</tbody></table></div><div class="actions"><button type="button" id="add-posting">Add posting</button><button type="submit">Save draft</button><button type="button" id="validate-draft">Validate on backend</button><button type="button" id="post-draft" class="primary">Confirm and post</button></div></form>${validation ? `<div class="validation ${validation.valid ? 'valid' : 'invalid'}"><strong>${validation.valid ? 'Validation passed' : 'Validation failed'}</strong>${validation.preview ? `<span>Debit ${esc(validation.preview.debitTotal)} · Credit ${esc(validation.preview.creditTotal)} · Difference ${esc(validation.preview.difference)}</span>` : ''}${(validation.issues || []).map((item) => `<p><code>${esc(item.code)}</code> ${esc(item.path)} — ${esc(item.message)}</p>`).join('')}</div>` : ''}</section>
  <section class="panel"><h3>Unposted drafts</h3><div class="list">${state.drafts.map((item) => `<article><div><strong>${esc(item.draft.date)} · ${esc(item.draft.description)}</strong><small>${esc(item.draft.id)} · ${item.draft.postings.length} postings</small></div><div class="actions"><button data-edit-draft="${esc(item.draft.id)}">Edit</button><button data-validate-stored="${esc(item.draft.id)}">Validate</button><button data-post-stored="${esc(item.draft.id)}">Post</button><button data-delete-draft="${esc(item.draft.id)}">Delete</button></div></article>`).join('') || '<p class="empty">No drafts yet.</p>'}</div></section>`;
}

function entries() {
  return `<section class="panel"><h3>Immutable Journal Entries</h3><p>Posted facts cannot be changed or deleted. Corrections require a linked reversal.</p><div class="list entries">${state.entries.map((entry) => `<article><div><strong>${esc(entry.date)} · ${esc(entry.description)}</strong><small>${esc(entry.id)} · ${esc(entry.balancingCommodityCode)} · ${entry.postings.length} postings ${entry.reversalOf ? `· reversal of ${esc(entry.reversalOf)}` : ''}</small><details><summary>View postings</summary><pre>${esc(JSON.stringify(entry.postings, null, 2))}</pre></details></div>${entry.reversalOf ? '' : `<button data-reverse-entry="${esc(entry.id)}">Reverse</button>`}</article>`).join('') || '<p class="empty">No posted entries yet.</p>'}</div></section>`;
}

function transactions() {
  return `<div class="workflow"><div class="workflow-step"><span>1</span>Draft and validate</div><div class="workflow-step"><span>2</span>Confirm posting</div><div class="workflow-step"><span>3</span>Immutable ledger</div></div>${drafts()}${entries()}`;
}

function holdingsView() {
  return `<section class="panel"><h3>Open lots / derived holdings</h3><div class="table-wrap"><table><thead><tr><th>Lot</th><th>Account</th><th>Commodity</th><th>Remaining units</th><th>Remaining cost</th><th>Latest price</th><th>Market value</th><th>Unrealized P&L</th></tr></thead><tbody>${state.holdings.map((item) => `<tr><td>${esc(item.lotId)}</td><td>${esc(item.accountId)}</td><td>${esc(item.commodityCode)}</td><td>${esc(item.remainingUnits)}</td><td>${esc(item.remainingCost)} ${esc(item.costCommodityCode)}</td><td>${esc(item.latestPrice ?? 'Missing')}</td><td>${esc(item.marketValue ?? '—')}</td><td>${esc(item.unrealizedPnL ?? '—')}</td></tr>`).join('')}</tbody></table></div></section><section class="panel"><h3>T-accounts</h3><div class="table-wrap"><table><thead><tr><th>Account</th><th>Commodity</th><th>Debit</th><th>Credit</th><th>Normal balance</th></tr></thead><tbody>${state.tAccounts.map((item) => `<tr><td>${esc(item.accountCode)} · ${esc(item.accountName)}</td><td>${esc(item.commodityCode)}</td><td>${esc(item.debit)}</td><td>${esc(item.credit)}</td><td>${esc(item.balance)}</td></tr>`).join('')}</tbody></table></div></section><div class="columns"><section class="panel"><h3>Financial statements</h3><pre>${esc(JSON.stringify(state.statements, null, 2))}</pre></section><section class="panel"><h3>Cash flow categories</h3><pre>${esc(JSON.stringify(state.cashFlow, null, 2))}</pre></section></div>`;
}

function worldView() {
  return `<div class="columns"><section class="panel"><h3>Living Accounts</h3><form id="living-form" class="compact-form"><input name="name" placeholder="Living account name" required><select name="commodityCode">${commodityOptions('currency')}</select><input name="balance" value="0" inputmode="decimal" required><input name="note" placeholder="Note"><button>Add living account</button></form><div class="list">${state.living.map((item) => `<article><div><strong>${esc(item.name)}</strong><small>${esc(item.balance)} ${esc(item.commodityCode)} · ${esc(item.updatedAt)}</small></div><div class="actions"><input data-balance-input="${esc(item.id)}" value="${esc(item.balance)}" inputmode="decimal"><button data-record-balance="${esc(item.id)}">Record balance</button></div></article>`).join('') || '<p class="empty">No living accounts yet.</p>'}</div></section>
  <section class="panel"><h3>Monthly Plans</h3><form id="plan-form" class="compact-form"><select name="kind"><option>income</option><option>expense</option></select><input name="name" placeholder="Plan name" required><input name="amount" value="0" inputmode="decimal"><select name="commodityCode">${commodityOptions('currency')}</select><input name="category" value="other"><input name="dayOfMonth" type="number" min="1" max="31" value="1"><input name="startDate" type="date" value="${today()}"><button>Add plan</button></form><div class="list">${state.plans.map((item) => `<article><div><strong>${esc(item.kind)} · ${esc(item.name)}</strong><small>${esc(item.amount)} ${esc(item.commodityCode)} · day ${item.dayOfMonth}</small></div><button data-delete-plan="${esc(item.id)}">Delete</button></article>`).join('') || '<p class="empty">No plans yet.</p>'}</div></section></div>
  <section class="panel"><h3>World deterministic summary</h3><pre>${esc(JSON.stringify(state.world, null, 2))}</pre></section>`;
}

function automation() {
  return `<div class="columns"><section class="panel"><h3>Recurring templates</h3><p>Save the current draft editor as a template. Due dates create drafts only.</p><form id="recurring-form" class="compact-form"><input name="id" value="monthly-rule" required><input name="name" value="Monthly rule" required><input name="dayOfMonth" type="number" min="1" max="31" value="15"><input name="startDate" type="date" value="${today()}"><button>Save draft template</button></form><button id="generate-due">Generate due drafts for this month</button><div class="list">${state.recurring.map((item) => `<article><div><strong>${esc(item.name)}</strong><small>${esc(item.id)} · ${item.enabled ? 'enabled' : 'disabled'} · day ${item.dayOfMonth} · ${esc(item.generatedPeriods.join(', '))}</small></div><div class="actions"><button data-toggle-rule="${esc(item.id)}">${item.enabled ? 'Deactivate' : 'Enable'}</button><button data-delete-rule="${esc(item.id)}">Delete</button></div></article>`).join('')}</div></section><section class="panel"><h3>Draft Import</h3><p>JSON input <code>{"drafts":[...]}</code>; only drafts are created after batch validation.</p><textarea id="import-json" rows="9" placeholder='{"drafts": [...]}'></textarea><button id="import-drafts">Validate and import JSON</button><hr><p>CSV uses public columns such as entryId, postingId, accountId, side and units.</p><input id="import-csv" type="file" accept=".csv,text/csv"><button id="import-drafts-csv">Validate and import CSV</button></section></div><div class="columns"><section class="panel"><h3>Atomic Mutable Batch</h3><p>Only commodities, accounts, priceQuotes and drafts are allowed. Posting and reversal cannot be bypassed.</p><textarea id="batch-json" rows="8" placeholder='{"commodities":[],"accounts":[],"drafts":[]}'></textarea><button id="run-batch">Run atomic batch</button></section><section class="panel"><h3>Export and versioned backup</h3><div class="actions"><a class="button" href="${downloadPath('/export')}" target="_blank">Open v3 JSON export</a><a class="button" href="${downloadPath('/export/journal-entries.csv')}">Download postings CSV</a><a class="button" href="${downloadPath('/backup')}" target="_blank">Open SHA-256 backup</a></div><p>Full backup restore requires an empty ledger and validates format, schema and hash. Undo is available afterward.</p><input id="backup-file" type="file" accept=".json,application/json"><button id="restore-backup">Validate and restore to empty ledger</button></section></div>`;
}

function settingsView() {
  const workspaceRows = state.workspaces.map((item) => `<article><div><strong>${esc(item.displayName)}</strong><small>${esc(item.slug)} · ${esc(item.kind)} · ${esc(item.status)}</small></div><div class="actions">${item.status === 'active' ? `<button data-archive-workspace="${esc(item.id)}">Archive</button>` : item.status === 'archived' ? `<button data-restore-workspace="${esc(item.id)}">Restore</button>` : ''}${item.status !== 'quarantined' ? `<button data-quarantine-workspace="${esc(item.id)}">Move to recoverable quarantine</button>` : ''}</div></article>`).join('');
  const workspaceOptions = state.workspaces.filter((item) => item.status === 'active').map((item) => `<option value="${esc(item.id)}">${esc(item.displayName)}</option>`).join('');
  return `<div class="columns"><section class="panel"><h3>Workspace</h3><form id="create-workspace-form" class="compact-form"><input name="displayName" placeholder="New workspace name" required><select name="kind"><option value="personal">personal</option><option value="sandbox">sandbox</option></select><button class="primary">Create</button></form><div class="list">${workspaceRows}</div>${state.controlUndo ? `<div class="notice success">Undo available: ${esc(state.controlUndo.operationType)} <button id="undo-control">Undo</button></div>` : ''}</section><section class="panel"><h3>API Access Token</h3><p>The token is shown only once. Do not copy it into browser code or logs.</p><form id="token-form" class="compact-form"><input name="name" placeholder="For example: local client" required><select name="workspaceId">${workspaceOptions}</select><select name="scope"><option value="ledger:read">Read only</option><option value="ledger:write">Read and write</option></select><button>Create token</button></form>${state.oneTimeToken ? `<div class="token-once"><strong>Shown once</strong><code>${esc(state.oneTimeToken)}</code></div>` : ''}<div class="list">${state.accessTokens.map((item) => `<article><div><strong>${esc(item.name)}</strong><small>${esc(item.scopes.join(', '))} · ${item.revokedAt ? 'revoked' : 'active'}</small></div>${item.revokedAt ? '' : `<button data-revoke-token="${esc(item.id)}">Revoke token</button>`}</article>`).join('') || '<p class="empty">No access tokens yet.</p>'}</div></section></div><section class="panel"><h3>About Finance Core 3.1.1</h3><p>API ${esc(state.health.apiVersion)} · Ledger schema ${state.health.ledgerSchemaVersion} · Registry schema ${state.health.registrySchemaVersion}. v1/v2 are no longer registered. Historical notes and Horizon documents are outside the main navigation.</p></section>`;
}

function render() {
  const views = { overview, master: masterData, transactions, holdings: holdingsView, world: worldView, automation, settings: settingsView };
  const options = state.workspaces.filter((item) => item.status !== 'quarantined').map((item) => `<option value="${esc(item.id)}" ${item.id === state.workspace.id ? 'selected' : ''}>${esc(item.displayName)} · ${item.kind}</option>`).join('');
  app.innerHTML = `<header class="app-header"><div><p class="eyebrow">FINANCE CORE 3.1</p><h1>Personal Finance Core</h1></div><div class="workspace-tools"><label>Workspace<select id="workspace-switch">${options}</select></label><span class="badge ${state.workspace.kind}">${esc(state.workspace.kind.toUpperCase())}</span><span class="badge">API ${esc(state.health.apiVersion)} · Ledger ${state.health.ledgerSchemaVersion}</span><button id="sign-out">Sign out</button></div></header>${nav()}${notice()}${state.busy ? `<div class="busy-bar"><span class="loader"></span>${esc(state.busy)}</div>` : ''}<div class="view" ${state.busy ? 'aria-busy="true"' : ''}>${views[state.active]()}</div><footer>Local first · deterministic finance · no bank, broker, LLM or live market connection</footer>`;
  bind();
}

function readEditor() {
  const form = document.querySelector('#draft-form');
  if (!form) return state.editor;
  const data = new FormData(form);
  const postings = [...form.querySelectorAll('[data-posting]')].map((row, index) => {
    const value = (field) => row.querySelector(`[data-field="${field}"]`).value.trim();
    const lotAction = value('lotAction') || undefined;
    const allocations = value('lotAllocations').split(',').map((part) => part.trim()).filter(Boolean).map((part) => { const [lotId, units] = part.split(':'); return { lotId, units }; });
    return { id: state.editor.postings[index]?.id || newId('posting'), accountId: value('accountId'), side: value('side'), units: value('units'), commodityCode: value('commodityCode'), ...(value('valuationRate') ? { valuationRate: value('valuationRate') } : {}), ...(value('rateType') ? { rateType: value('rateType') } : {}), cashFlowCategory: value('cashFlowCategory'), memo: '', ...(lotAction ? { lotAction } : {}), ...(lotAction === 'acquire' ? { lotId: value('lotId') } : {}), ...(lotAction === 'dispose' ? { lotAllocations: allocations } : {}) };
  });
  return { id: data.get('id').trim(), date: data.get('date'), description: data.get('description').trim(), payee: data.get('payee').trim(), source: data.get('source').trim(), reference: data.get('reference').trim(), tags: data.get('tags').split(',').map((item) => item.trim()).filter(Boolean), balancingCommodityCode: data.get('balancingCommodityCode'), postings };
}

async function act(work, message) {
  state.error = ''; state.message = ''; state.busy = message || 'Working…'; render();
  try {
    await work(); state.message = message || 'Operation completed.';
    if (state.workspace) await refresh();
    else { state.busy = ''; renderWorkspaceWizard(); return; }
  } catch (error) { state.error = error.message; }
  state.busy = '';
  render();
}

function bind() {
  document.querySelector('#workspace-switch')?.addEventListener('change', async (event) => {
    state.workspace = state.workspaces.find((item) => item.id === event.target.value);
    const workspaceId = state.workspace.id;
    clearWorkspaceData();
    state.active = 'overview'; state.error = ''; state.message = ''; state.busy = 'Switching workspace and loading overview…'; render();
    try { await refresh(); } catch (error) { if (error.name !== 'AbortError') state.error = error.message; }
    if (state.workspace?.id === workspaceId) { state.busy = ''; render(); }
  });
  document.querySelector('#sign-out')?.addEventListener('click', async () => {
    await request('/api/v3/session', { method: 'DELETE' }); state.user = null; state.workspace = null; renderLogin();
  });
  document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', async () => {
    const view = button.dataset.tab;
    state.active = view; state.error = ''; state.message = ''; state.busy = `Loading ${button.textContent}…`; render();
    try {
      if (view === 'settings') await refreshControl();
      else await refresh(view);
    } catch (error) {
      if (error.name !== 'AbortError') state.error = error.message;
    }
    if (state.active === view) { state.busy = ''; render(); }
  }));
  document.querySelector('#create-workspace-form')?.addEventListener('submit', (event) => {
    event.preventDefault(); const data = new FormData(event.target);
    act(async () => { const result = await request('/api/v3/workspaces', { method: 'POST', body: JSON.stringify({ displayName: data.get('displayName'), kind: data.get('kind') }) }); state.controlUndo = result.undo; await refreshControl(); }, 'Workspace created.');
  });
  document.querySelectorAll('[data-archive-workspace]').forEach((button) => button.addEventListener('click', () => act(async () => { const result = await request(`/api/v3/workspaces/${button.dataset.archiveWorkspace}`, { method: 'PATCH', body: JSON.stringify({ status: 'archived' }) }); state.controlUndo = result.undo; await refreshControl(); }, 'Workspace archived.')));
  document.querySelectorAll('[data-restore-workspace]').forEach((button) => button.addEventListener('click', () => act(async () => { const result = await request(`/api/v3/workspaces/${button.dataset.restoreWorkspace}`, { method: 'PATCH', body: JSON.stringify({ status: 'active' }) }); state.controlUndo = result.undo; await refreshControl(); }, 'Workspace restored.')));
  document.querySelectorAll('[data-quarantine-workspace]').forEach((button) => button.addEventListener('click', () => {
    if (!confirm('Move this Vault to the 30-day recoverable quarantine?')) return;
    act(async () => { const result = await request(`/api/v3/workspaces/${button.dataset.quarantineWorkspace}`, { method: 'DELETE' }); state.controlUndo = result.undo; const removedCurrent = state.workspace.id === button.dataset.quarantineWorkspace; await refreshControl(); if (removedCurrent) state.workspace = state.workspaces.find((item) => item.status === 'active') || null; }, 'Vault moved to recoverable quarantine.');
  }));
  document.querySelector('#undo-control')?.addEventListener('click', () => act(async () => { await request('/api/v3/undo', { method: 'POST', body: JSON.stringify({ undoToken: state.controlUndo.undoToken }) }); state.controlUndo = null; await refreshControl(); }, 'Control operation undone.'));
  document.querySelector('#token-form')?.addEventListener('submit', (event) => {
    event.preventDefault(); const data = new FormData(event.target); const scope = data.get('scope');
    act(async () => { const result = await request('/api/v3/access-tokens', { method: 'POST', body: JSON.stringify({ name: data.get('name'), workspaceIds: [data.get('workspaceId')], scopes: scope === 'ledger:write' ? ['ledger:read', 'ledger:write'] : ['ledger:read'] }) }); state.oneTimeToken = result.token; await refreshControl(); }, 'Access token created.');
  });
  document.querySelectorAll('[data-revoke-token]').forEach((button) => button.addEventListener('click', () => act(async () => { await request(`/api/v3/access-tokens/${button.dataset.revokeToken}/revoke`, { method: 'POST' }); await refreshControl(); }, 'Access token revoked.')));
  document.querySelector('#refresh')?.addEventListener('click', () => act(async () => {}, 'Refreshed.'));
  document.querySelector('#undo-latest')?.addEventListener('click', () => act(() => request('/api/v3/undo', { method: 'POST', body: JSON.stringify({ undoToken: state.undo.undoToken, workspaceId: state.workspace.id }) }), 'Latest operation undone.'));
  document.querySelector('#load-demo')?.addEventListener('click', () => act(() => request('/api/v2/demo/load-synthetic', { method: 'POST' }), 'Synthetic master data and opening draft loaded.'));
  document.querySelector('#commodity-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/commodities', { method: 'POST', body: JSON.stringify({ code: data.get('code'), kind: data.get('kind'), scale: Number(data.get('scale')), name: data.get('name'), status: 'active' }) }), 'Commodity added.'); });
  document.querySelector('#account-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/accounts', { method: 'POST', body: JSON.stringify({ id: newId('account'), code: data.get('code'), name: data.get('name'), type: data.get('type'), subtype: data.get('subtype'), allowedCommodityCodes: [data.get('commodity')], status: 'active' }) }), 'Account added.'); });
  document.querySelector('#quote-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/price-quotes', { method: 'POST', body: JSON.stringify({ id: newId('quote'), commodityCode: data.get('commodityCode'), quoteCommodityCode: data.get('quoteCommodityCode'), price: data.get('price'), asOf: new Date(data.get('asOf')).toISOString(), source: data.get('source') }) }), 'Price added.'); });
  document.querySelectorAll('[data-inactivate-commodity]').forEach((button) => button.addEventListener('click', () => { const item = state.commodities.find((value) => value.code === button.dataset.inactivateCommodity); act(() => request(`/api/v2/commodities/${item.code}`, { method: 'PUT', body: JSON.stringify({ ...item, status: 'inactive' }) }), 'Commodity deactivated.'); }));
  document.querySelectorAll('[data-inactivate-account]').forEach((button) => button.addEventListener('click', () => { const item = state.accounts.find((value) => value.id === button.dataset.inactivateAccount); act(() => request(`/api/v2/accounts/${item.id}`, { method: 'PUT', body: JSON.stringify({ ...item, status: 'inactive' }) }), 'Account deactivated.'); }));
  document.querySelectorAll('[data-delete-quote]').forEach((button) => button.addEventListener('click', () => act(() => request(`/api/v2/price-quotes/${button.dataset.deleteQuote}`, { method: 'DELETE' }), 'Price deleted.')));
  document.querySelector('#new-draft')?.addEventListener('click', () => { state.editor = blankDraft(); state.validation = null; render(); });
  document.querySelector('#add-posting')?.addEventListener('click', () => { state.editor = readEditor(); state.editor.postings.push({ id: newId('posting'), accountId: state.accounts[0]?.id || '', side: 'debit', units: '0', commodityCode: state.editor.balancingCommodityCode, cashFlowCategory: 'other', lotAllocations: [] }); render(); });
  document.querySelectorAll('[data-remove-posting]').forEach((button) => button.addEventListener('click', () => { state.editor = readEditor(); state.editor.postings.splice(Number(button.dataset.removePosting), 1); render(); }));
  document.querySelector('#draft-form')?.addEventListener('submit', (event) => { event.preventDefault(); state.editor = readEditor(); const exists = state.drafts.some((item) => item.draft.id === state.editor.id); act(() => request(`/api/v2/journal-entry-drafts${exists ? `/${state.editor.id}` : ''}`, { method: exists ? 'PUT' : 'POST', body: JSON.stringify(state.editor) }), 'Draft saved.'); });
  document.querySelector('#validate-draft')?.addEventListener('click', () => { state.editor = readEditor(); const exists = state.drafts.some((item) => item.draft.id === state.editor.id); act(async () => { if (!exists) await request('/api/v2/journal-entry-drafts', { method: 'POST', body: JSON.stringify(state.editor) }); else await request(`/api/v2/journal-entry-drafts/${state.editor.id}`, { method: 'PUT', body: JSON.stringify(state.editor) }); state.validation = await request(`/api/v2/journal-entry-drafts/${state.editor.id}/validate`, { method: 'POST' }); }, 'Validation completed.'); });
  document.querySelector('#post-draft')?.addEventListener('click', () => { state.editor = readEditor(); if (!confirm('Post this complete aggregate to the immutable ledger?')) return; act(async () => { const exists = state.drafts.some((item) => item.draft.id === state.editor.id); if (!exists) await request('/api/v2/journal-entry-drafts', { method: 'POST', body: JSON.stringify(state.editor) }); else await request(`/api/v2/journal-entry-drafts/${state.editor.id}`, { method: 'PUT', body: JSON.stringify(state.editor) }); await request(`/api/v2/journal-entry-drafts/${state.editor.id}/post`, { method: 'POST' }); state.editor = blankDraft(); state.validation = null; }, 'Entry posted.'); });
  document.querySelectorAll('[data-edit-draft]').forEach((button) => button.addEventListener('click', () => { state.editor = structuredClone(state.drafts.find((item) => item.draft.id === button.dataset.editDraft).draft); state.validation = null; render(); }));
  document.querySelectorAll('[data-validate-stored]').forEach((button) => button.addEventListener('click', () => act(async () => { state.validation = await request(`/api/v2/journal-entry-drafts/${button.dataset.validateStored}/validate`, { method: 'POST' }); state.editor = structuredClone(state.drafts.find((item) => item.draft.id === button.dataset.validateStored).draft); }, 'Validation completed.')));
  document.querySelectorAll('[data-post-stored]').forEach((button) => button.addEventListener('click', () => { if (confirm('Post this draft?')) act(() => request(`/api/v2/journal-entry-drafts/${button.dataset.postStored}/post`, { method: 'POST' }), 'Entry posted.'); }));
  document.querySelectorAll('[data-delete-draft]').forEach((button) => button.addEventListener('click', () => act(() => request(`/api/v2/journal-entry-drafts/${button.dataset.deleteDraft}`, { method: 'DELETE' }), 'Draft deleted.')));
  document.querySelectorAll('[data-reverse-entry]').forEach((button) => button.addEventListener('click', () => { if (confirm('Create a linked reversal? The original entry remains.')) act(() => request(`/api/v2/journal-entries/${button.dataset.reverseEntry}/reverse`, { method: 'POST' }), 'Reversal created.'); }));
  document.querySelector('#living-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/living-accounts', { method: 'POST', body: JSON.stringify({ id: newId('living'), name: data.get('name'), commodityCode: data.get('commodityCode'), balance: data.get('balance'), note: data.get('note'), updatedAt: new Date().toISOString() }) }), 'Living account added.'); });
  document.querySelectorAll('[data-record-balance]').forEach((button) => button.addEventListener('click', () => { const input = document.querySelector(`[data-balance-input="${button.dataset.recordBalance}"]`); act(() => request(`/api/v2/living-accounts/${button.dataset.recordBalance}/record-balance`, { method: 'POST', body: JSON.stringify({ balance: input.value }) }), 'Balance and snapshot recorded atomically.'); }));
  document.querySelector('#plan-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/monthly-plans', { method: 'POST', body: JSON.stringify({ id: newId('plan'), kind: data.get('kind'), name: data.get('name'), amount: data.get('amount'), commodityCode: data.get('commodityCode'), category: data.get('category'), recurringMonthly: true, dayOfMonth: Number(data.get('dayOfMonth')), startDate: data.get('startDate'), note: '' }) }), 'Monthly plan added.'); });
  document.querySelectorAll('[data-delete-plan]').forEach((button) => button.addEventListener('click', () => act(() => request(`/api/v2/monthly-plans/${button.dataset.deletePlan}`, { method: 'DELETE' }), 'Monthly plan deleted.')));
  document.querySelector('#recurring-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); const template = structuredClone(state.editor); template.id = `${data.get('id')}-template`; template.postings = template.postings.map((item, index) => ({ ...item, id: `${template.id}-p${index + 1}` })); act(() => request('/api/v2/recurring-entry-rules', { method: 'POST', body: JSON.stringify({ id: data.get('id'), name: data.get('name'), enabled: true, frequency: 'monthly', dayOfMonth: Number(data.get('dayOfMonth')), startDate: data.get('startDate'), template, generatedPeriods: [] }) }), 'Recurring template saved.'); });
  document.querySelector('#generate-due')?.addEventListener('click', () => act(() => request('/api/v2/recurring-entry-rules/generate-due', { method: 'POST', body: JSON.stringify({ asOf: today() }) }), 'Due drafts generated.'));
  document.querySelectorAll('[data-toggle-rule]').forEach((button) => button.addEventListener('click', () => { const item = state.recurring.find((value) => value.id === button.dataset.toggleRule); act(() => request(`/api/v2/recurring-entry-rules/${item.id}`, { method: 'PUT', body: JSON.stringify({ ...item, enabled: !item.enabled }) }), 'Recurring rule status updated.'); }));
  document.querySelectorAll('[data-delete-rule]').forEach((button) => button.addEventListener('click', () => act(() => request(`/api/v2/recurring-entry-rules/${button.dataset.deleteRule}`, { method: 'DELETE' }), 'Recurring rule deleted.')));
  document.querySelector('#import-drafts')?.addEventListener('click', () => act(() => request('/api/v2/import/drafts', { method: 'POST', body: document.querySelector('#import-json').value }), 'Drafts validated and imported.'));
  document.querySelector('#import-drafts-csv')?.addEventListener('click', () => act(async () => { const file = document.querySelector('#import-csv').files[0]; if (!file) throw new Error('Select a CSV file first.'); await request('/api/v2/import/drafts.csv', { method: 'POST', body: await file.text(), headers: { 'Content-Type': 'text/csv' } }); }, 'CSV drafts validated and imported.'));
  document.querySelector('#run-batch')?.addEventListener('click', () => act(() => request('/api/v2/batch', { method: 'POST', body: document.querySelector('#batch-json').value }), 'Mutable batch executed atomically.'));
  document.querySelector('#restore-backup')?.addEventListener('click', () => { if (!confirm('Restore requires an empty ledger. Validate and restore this backup?')) return; act(async () => { const file = document.querySelector('#backup-file').files[0]; if (!file) throw new Error('Select a JSON backup first.'); const wrapper = JSON.parse(await file.text()); await request('/api/v2/backup/restore', { method: 'POST', body: JSON.stringify(wrapper.data || wrapper) }); }, 'Backup validated and restored.'); });
}

function renderLogin(error = '') {
  app.innerHTML = `<section class="status auth-card"><p class="eyebrow">FINANCE CORE 3.1</p><h1>Enter your local finance system</h1><p>The admin token creates a local HttpOnly session. It is not stored in the browser.</p>${error ? `<div class="notice error">${esc(error)}</div>` : ''}<form id="login-form"><label>Admin token<input name="adminToken" type="password" autocomplete="current-password" required></label><button class="primary" type="submit">Enter Finance Core</button></form></section>`;
  document.querySelector('#login-form').addEventListener('submit', async (event) => {
    event.preventDefault(); const data = new FormData(event.target);
    try { await request('/api/v3/session', { method: 'POST', body: JSON.stringify({ adminToken: data.get('adminToken') }) }); await load(); } catch (loginError) { renderLogin(loginError.message); }
  });
}

function renderWorkspaceWizard(error = '') {
  const archived = state.workspaces.filter((item) => item.status === 'archived').map((item) => `<button data-wizard-restore="${esc(item.id)}">Restore ${esc(item.displayName)}</button>`).join('');
  app.innerHTML = `<section class="status wizard"><p class="eyebrow">NO ACTIVE VAULT</p><h1>Create your first workspace</h1><p>Each workspace has its own database for commodities, accounts, drafts, ledger, holdings and plans.</p>${error ? `<div class="notice error">${esc(error)}</div>` : ''}${archived ? `<div class="archived-options"><strong>Restore an archived workspace</strong>${archived}</div>` : ''}<form id="workspace-form"><label>Name<input name="displayName" placeholder="For example: Main Workspace" required maxlength="120"></label><label>Type<select name="kind"><option value="personal">Personal · private data</option><option value="sandbox">Sandbox · test data</option></select></label><button class="primary" type="submit">Create and enter</button></form></section>`;
  document.querySelectorAll('[data-wizard-restore]').forEach((button) => button.addEventListener('click', async () => {
    try { await request(`/api/v3/workspaces/${button.dataset.wizardRestore}`, { method: 'PATCH', body: JSON.stringify({ status: 'active' }) }); await load(); } catch (restoreError) { renderWorkspaceWizard(restoreError.message); }
  }));
  document.querySelector('#workspace-form').addEventListener('submit', async (event) => {
    event.preventDefault(); const data = new FormData(event.target);
    try {
      await request('/api/v3/workspaces', { method: 'POST', body: JSON.stringify({ displayName: data.get('displayName'), kind: data.get('kind') }) });
      await load();
    } catch (createError) { renderWorkspaceWizard(createError.message); }
  });
}

async function load() {
  app.innerHTML = '<section class="status"><span class="loader" aria-hidden="true"></span>Connecting to Finance Core 3.1…</section>';
  try {
    state.health = await request('/api/v3/health');
    state.user = (await request('/api/v3/me')).data;
    state.workspaces = (await request('/api/v3/workspaces')).data;
    const active = state.workspaces.filter((item) => item.status === 'active');
    if (!active.length) { renderWorkspaceWizard(); return; }
    state.workspace = active.find((item) => item.id === state.workspace?.id) || active[0];
    clearWorkspaceData();
    state.active = 'overview'; state.busy = 'Connected. Loading overview…'; render();
    await refresh('overview'); state.busy = ''; render();
  } catch (error) {
    if (error.status === 401) { renderLogin(); return; }
    app.innerHTML = `<section class="status error"><h1>Finance Core is unavailable</h1><p>${esc(error.message)}</p><button id="retry">Retry</button></section>`;
    document.querySelector('#retry').addEventListener('click', load);
  }
}

void load();
