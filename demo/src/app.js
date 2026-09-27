import './style.css';
import { initLanguageSwitch, translate } from './i18n.js';

const app = document.querySelector('#app');
const currentLanguage = initLanguageSwitch(app);
const ask = (message) => confirm(translate(message, currentLanguage()));
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
    if (!state.workspace) throw new Error('请先创建或选择一个数据空间。');
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
      const timeoutError = new Error(`请求 ${path} 超过 ${REQUEST_TIMEOUT_MS / 1000} 秒。请检查 FC 后端终端和 /api/v3/health。`);
      timeoutError.code = 'REQUEST_TIMEOUT';
      throw timeoutError;
    }
    if (error.name === 'TypeError') {
      throw new Error('无法连接 Finance Core 后端。请确认 npm.cmd run dev 正在运行，并检查 /api/v3/health。');
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
    ['overview', '概览'], ['transactions', '交易'], ['holdings', '持仓与报表'],
    ['world', '生活与计划'], ['automation', '自动化与数据'], ['master', '主数据'], ['settings', '设置'],
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
  return `<section class="panel hero"><div><p class="eyebrow">LOCAL-FIRST · DETERMINISTIC · WORKSPACE-SCOPED</p><h2>${esc(state.workspace.displayName)} · 确定性账本状态</h2><p>所有财务规则由 Finance Core 后端执行；当前数据空间与其他 Vault 完全隔离。</p></div><div class="actions"><button id="refresh">刷新</button><button id="undo-latest" ${state.undo ? '' : 'disabled'}>撤销上一步普通操作</button>${state.workspace.kind === 'sandbox' ? '<button id="load-demo" class="primary">装载合成示例</button>' : ''}</div></section>
  <section class="metrics"><article><span>草稿</span><strong>${state.dashboard.draftCount}</strong></article><article><span>已过账</span><strong>${state.dashboard.entryCount}</strong></article><article><span>Open lots</span><strong>${state.dashboard.openLotCount}</strong></article><article><span>对账</span><strong class="${state.reconciliation.status}">${esc(state.reconciliation.status)}</strong></article></section>
  <section class="panel"><h3>按计价商品汇总</h3>${summary.length ? `<div class="table-wrap"><table><thead><tr><th>商品</th><th>现金</th><th>成本</th><th>市值</th><th>未实现盈亏</th><th>缺价</th></tr></thead><tbody>${summary.map((item) => `<tr><td>${esc(item.commodityCode)}</td><td>${esc(item.cash)}</td><td>${esc(item.holdingCostBasis)}</td><td>${esc(item.marketValue)}</td><td>${esc(item.unrealizedPnL)}</td><td>${item.missingPriceCount}</td></tr>`).join('')}</tbody></table></div>` : '<p class="empty">尚无已过账数据。</p>'}</section>
  <section class="panel"><h3>确定性检查</h3><div class="check-grid">${state.reconciliation.checks.map((item) => `<article class="check ${item.status}"><strong>${esc(item.id)}</strong><span>${esc(item.detail)}</span></article>`).join('')}</div></section>`;
}

function commodityOptions(kind) {
  return state.commodities.filter((item) => item.status === 'active' && (!kind || item.kind === kind)).map((item) => `<option value="${esc(item.code)}">${esc(item.code)} · ${esc(item.name)}</option>`).join('');
}

function accountOptions(selected = '') {
  return state.accounts.filter((item) => item.status === 'active').map((item) => `<option value="${esc(item.id)}" ${item.id === selected ? 'selected' : ''}>${esc(item.code)} · ${esc(item.name)}</option>`).join('');
}

function masterData() {
  return `<div class="columns"><section class="panel"><h3>Commodity Registry</h3><form id="commodity-form" class="compact-form"><input name="code" placeholder="CNY" required><select name="kind"><option>currency</option><option>security</option><option>other</option></select><input name="scale" type="number" min="0" max="18" value="2" required><input name="name" placeholder="名称" required><button>新增</button></form><div class="list">${state.commodities.map((item) => `<article><div><strong>${esc(item.code)}</strong><small>${esc(item.kind)} · scale ${item.scale} · ${esc(item.status)}</small></div><button data-inactivate-commodity="${esc(item.code)}" ${item.status === 'inactive' ? 'disabled' : ''}>停用</button></article>`).join('') || '<p class="empty">暂无 commodity。</p>'}</div></section>
  <section class="panel"><h3>类型化账户</h3><form id="account-form" class="compact-form"><input name="code" placeholder="1001" required><input name="name" placeholder="账户名" required><select name="type"><option>asset</option><option>liability</option><option>equity</option><option>income</option><option>expense</option></select><input name="subtype" placeholder="cash / investment"><select name="commodity">${commodityOptions()}</select><button>新增</button></form><div class="list">${state.accounts.map((item) => `<article><div><strong>${esc(item.code)} · ${esc(item.name)}</strong><small>${esc(item.type)}/${esc(item.subtype || 'general')} · ${esc(item.allowedCommodityCodes.join(', '))} · ${esc(item.status)}</small></div><button data-inactivate-account="${esc(item.id)}" ${item.status === 'inactive' ? 'disabled' : ''}>停用</button></article>`).join('') || '<p class="empty">暂无账户。</p>'}</div></section></div>
  <section class="panel"><h3>显式价格</h3><form id="quote-form" class="inline-form"><select name="commodityCode">${commodityOptions('security')}</select><select name="quoteCommodityCode">${commodityOptions('currency')}</select><input name="price" inputmode="decimal" placeholder="110.00" required><input name="asOf" type="datetime-local" required><input name="source" value="manual" required><button>新增价格</button></form><div class="table-wrap"><table><thead><tr><th>商品</th><th>报价商品</th><th>价格</th><th>时间</th><th>来源</th><th></th></tr></thead><tbody>${state.quotes.map((item) => `<tr><td>${esc(item.commodityCode)}</td><td>${esc(item.quoteCommodityCode)}</td><td>${esc(item.price)}</td><td>${esc(item.asOf)}</td><td>${esc(item.source)}</td><td><button data-delete-quote="${esc(item.id)}">删除</button></td></tr>`).join('')}</tbody></table></div></section>`;
}

function postingRow(item, index) {
  return `<tr data-posting="${index}"><td><select data-field="accountId">${accountOptions(item.accountId)}</select></td><td><select data-field="side"><option ${item.side === 'debit' ? 'selected' : ''}>debit</option><option ${item.side === 'credit' ? 'selected' : ''}>credit</option></select></td><td><input data-field="units" value="${esc(item.units)}" inputmode="decimal"></td><td><select data-field="commodityCode">${state.commodities.filter((value) => value.status === 'active').map((value) => `<option ${value.code === item.commodityCode ? 'selected' : ''}>${esc(value.code)}</option>`).join('')}</select></td><td><input data-field="valuationRate" value="${esc(item.valuationRate || '')}" inputmode="decimal" placeholder="base=1"></td><td><select data-field="rateType"><option value="">自动</option>${['exchange', 'price', 'cost'].map((value) => `<option ${value === item.rateType ? 'selected' : ''}>${value}</option>`).join('')}</select></td><td><select data-field="cashFlowCategory">${['income', 'expense', 'investment', 'financing', 'transfer', 'other'].map((value) => `<option ${value === item.cashFlowCategory ? 'selected' : ''}>${value}</option>`).join('')}</select></td><td><select data-field="lotAction"><option value="">无</option><option value="acquire" ${item.lotAction === 'acquire' ? 'selected' : ''}>acquire</option><option value="dispose" ${item.lotAction === 'dispose' ? 'selected' : ''}>dispose</option></select><input data-field="lotId" value="${esc(item.lotId || '')}" placeholder="acquire lotId"><input data-field="lotAllocations" value="${esc((item.lotAllocations || []).map((value) => `${value.lotId}:${value.units}`).join(','))}" placeholder="lotId:units"></td><td><button type="button" data-remove-posting="${index}">移除</button></td></tr>`;
}

function drafts() {
  const editor = state.editor || blankDraft();
  const validation = state.validation;
  return `<section class="panel"><div class="section-title"><div><h3>JournalEntry Draft</h3><p>草稿不会进入账本或报表；Decimal 字符串原样提交给后端。</p></div><button id="new-draft">新草稿</button></div><form id="draft-form"><div class="form-grid"><label>ID<input name="id" value="${esc(editor.id)}" required></label><label>日期<input name="date" type="date" value="${esc(editor.date)}" required></label><label>描述<input name="description" value="${esc(editor.description)}" required></label><label>Payee<input name="payee" value="${esc(editor.payee)}"></label><label>来源<input name="source" value="${esc(editor.source)}"></label><label>Reference<input name="reference" value="${esc(editor.reference)}"></label><label>计价商品<select name="balancingCommodityCode">${state.commodities.map((item) => `<option ${item.code === editor.balancingCommodityCode ? 'selected' : ''}>${esc(item.code)}</option>`).join('')}</select></label><label>Tags<input name="tags" value="${esc((editor.tags || []).join(', '))}"></label></div><div class="table-wrap postings"><table><thead><tr><th>账户</th><th>方向</th><th>Units</th><th>商品</th><th>估值率</th><th>类型</th><th>现金流</th><th>Lot</th><th></th></tr></thead><tbody>${editor.postings.map(postingRow).join('')}</tbody></table></div><div class="actions"><button type="button" id="add-posting">增加 posting</button><button type="submit">保存草稿</button><button type="button" id="validate-draft">后端验证</button><button type="button" id="post-draft" class="primary">确认并过账</button></div></form>${validation ? `<div class="validation ${validation.valid ? 'valid' : 'invalid'}"><strong>${validation.valid ? '验证通过' : '验证失败'}</strong>${validation.preview ? `<span>Debit ${esc(validation.preview.debitTotal)} · Credit ${esc(validation.preview.creditTotal)} · Difference ${esc(validation.preview.difference)}</span>` : ''}${(validation.issues || []).map((item) => `<p><code>${esc(item.code)}</code> ${esc(item.path)} — ${esc(item.message)}</p>`).join('')}</div>` : ''}</section>
  <section class="panel"><h3>未过账草稿</h3><div class="list">${state.drafts.map((item) => `<article><div><strong>${esc(item.draft.date)} · ${esc(item.draft.description)}</strong><small>${esc(item.draft.id)} · ${item.draft.postings.length} postings</small></div><div class="actions"><button data-edit-draft="${esc(item.draft.id)}">编辑</button><button data-validate-stored="${esc(item.draft.id)}">验证</button><button data-post-stored="${esc(item.draft.id)}">过账</button><button data-delete-draft="${esc(item.draft.id)}">删除</button></div></article>`).join('') || '<p class="empty">暂无草稿。</p>'}</div></section>`;
}

function entries() {
  return `<section class="panel"><h3>不可变 Journal Entries</h3><p>已过账事实不可 PATCH/DELETE；更正必须创建 linked reversal。</p><div class="list entries">${state.entries.map((entry) => `<article><div><strong>${esc(entry.date)} · ${esc(entry.description)}</strong><small>${esc(entry.id)} · ${esc(entry.balancingCommodityCode)} · ${entry.postings.length} postings ${entry.reversalOf ? `· reversal of ${esc(entry.reversalOf)}` : ''}</small><details><summary>查看 postings</summary><pre>${esc(JSON.stringify(entry.postings, null, 2))}</pre></details></div>${entry.reversalOf ? '' : `<button data-reverse-entry="${esc(entry.id)}">冲销</button>`}</article>`).join('') || '<p class="empty">暂无已过账交易。</p>'}</div></section>`;
}

function transactions() {
  return `<div class="workflow"><div class="workflow-step"><span>1</span>草稿与验证</div><div class="workflow-step"><span>2</span>确认过账</div><div class="workflow-step"><span>3</span>不可变账本</div></div>${drafts()}${entries()}`;
}

function holdingsView() {
  return `<section class="panel"><h3>Open lots / 派生持仓</h3><div class="table-wrap"><table><thead><tr><th>Lot</th><th>账户</th><th>商品</th><th>剩余数量</th><th>剩余成本</th><th>最新价</th><th>市值</th><th>未实现盈亏</th></tr></thead><tbody>${state.holdings.map((item) => `<tr><td>${esc(item.lotId)}</td><td>${esc(item.accountId)}</td><td>${esc(item.commodityCode)}</td><td>${esc(item.remainingUnits)}</td><td>${esc(item.remainingCost)} ${esc(item.costCommodityCode)}</td><td>${esc(item.latestPrice ?? '缺失')}</td><td>${esc(item.marketValue ?? '—')}</td><td>${esc(item.unrealizedPnL ?? '—')}</td></tr>`).join('')}</tbody></table></div></section><section class="panel"><h3>T-accounts</h3><div class="table-wrap"><table><thead><tr><th>账户</th><th>商品</th><th>Debit</th><th>Credit</th><th>Normal balance</th></tr></thead><tbody>${state.tAccounts.map((item) => `<tr><td>${esc(item.accountCode)} · ${esc(item.accountName)}</td><td>${esc(item.commodityCode)}</td><td>${esc(item.debit)}</td><td>${esc(item.credit)}</td><td>${esc(item.balance)}</td></tr>`).join('')}</tbody></table></div></section><div class="columns"><section class="panel"><h3>财务报表</h3><pre>${esc(JSON.stringify(state.statements, null, 2))}</pre></section><section class="panel"><h3>现金流分类</h3><pre>${esc(JSON.stringify(state.cashFlow, null, 2))}</pre></section></div>`;
}

function worldView() {
  return `<div class="columns"><section class="panel"><h3>Living Accounts</h3><form id="living-form" class="compact-form"><input name="name" placeholder="生活账户名称" required><select name="commodityCode">${commodityOptions('currency')}</select><input name="balance" value="0" inputmode="decimal" required><input name="note" placeholder="备注"><button>新增生活账户</button></form><div class="list">${state.living.map((item) => `<article><div><strong>${esc(item.name)}</strong><small>${esc(item.balance)} ${esc(item.commodityCode)} · ${esc(item.updatedAt)}</small></div><div class="actions"><input data-balance-input="${esc(item.id)}" value="${esc(item.balance)}" inputmode="decimal"><button data-record-balance="${esc(item.id)}">记录余额</button></div></article>`).join('') || '<p class="empty">暂无生活账户。</p>'}</div></section>
  <section class="panel"><h3>Monthly Plans</h3><form id="plan-form" class="compact-form"><select name="kind"><option>income</option><option>expense</option></select><input name="name" placeholder="计划名称" required><input name="amount" value="0" inputmode="decimal"><select name="commodityCode">${commodityOptions('currency')}</select><input name="category" value="other"><input name="dayOfMonth" type="number" min="1" max="31" value="1"><input name="startDate" type="date" value="${today()}"><button>新增计划</button></form><div class="list">${state.plans.map((item) => `<article><div><strong>${esc(item.kind)} · ${esc(item.name)}</strong><small>${esc(item.amount)} ${esc(item.commodityCode)} · day ${item.dayOfMonth}</small></div><button data-delete-plan="${esc(item.id)}">删除</button></article>`).join('') || '<p class="empty">暂无计划。</p>'}</div></section></div>
  <section class="panel"><h3>World 确定性汇总</h3><pre>${esc(JSON.stringify(state.world, null, 2))}</pre></section>`;
}

function automation() {
  return `<div class="columns"><section class="panel"><h3>周期模板</h3><p>保存当前草稿编辑器内容为模板；到期只生成 draft。</p><form id="recurring-form" class="compact-form"><input name="id" value="monthly-rule" required><input name="name" value="Monthly rule" required><input name="dayOfMonth" type="number" min="1" max="31" value="15"><input name="startDate" type="date" value="${today()}"><button>保存当前草稿模板</button></form><button id="generate-due">生成本月到期草稿</button><div class="list">${state.recurring.map((item) => `<article><div><strong>${esc(item.name)}</strong><small>${esc(item.id)} · ${item.enabled ? 'enabled' : 'disabled'} · day ${item.dayOfMonth} · ${esc(item.generatedPeriods.join(', '))}</small></div><div class="actions"><button data-toggle-rule="${esc(item.id)}">${item.enabled ? '停用' : '启用'}</button><button data-delete-rule="${esc(item.id)}">删除</button></div></article>`).join('')}</div></section><section class="panel"><h3>Draft Import</h3><p>JSON 输入 <code>{"drafts":[...]}</code>；整批验证通过后只创建草稿。</p><textarea id="import-json" rows="9" placeholder='{"drafts": [...]}'></textarea><button id="import-drafts">验证并导入 JSON</button><hr><p>CSV 使用 entryId/postingId/accountId/side/units 等公开列。</p><input id="import-csv" type="file" accept=".csv,text/csv"><button id="import-drafts-csv">验证并导入 CSV</button></section></div><div class="columns"><section class="panel"><h3>Atomic Mutable Batch</h3><p>只允许 commodities、accounts、priceQuotes、drafts；不能绕过 post/reversal。</p><textarea id="batch-json" rows="8" placeholder='{"commodities":[],"accounts":[],"drafts":[]}'></textarea><button id="run-batch">原子执行</button></section><section class="panel"><h3>导出与版本化备份</h3><div class="actions"><a class="button" href="${downloadPath('/export')}" target="_blank">打开 v3 JSON export</a><a class="button" href="${downloadPath('/export/journal-entries.csv')}">下载 postings CSV</a><a class="button" href="${downloadPath('/backup')}" target="_blank">打开 SHA-256 备份</a></div><p>完整备份恢复只允许空 ledger，并验证 format/schema/hash；成功后提供 undo。</p><input id="backup-file" type="file" accept=".json,application/json"><button id="restore-backup">验证并恢复到空账本</button></section></div>`;
}

function settingsView() {
  const workspaceRows = state.workspaces.map((item) => `<article><div><strong>${esc(item.displayName)}</strong><small>${esc(item.slug)} · ${esc(item.kind)} · ${esc(item.status)}</small></div><div class="actions">${item.status === 'active' ? `<button data-archive-workspace="${esc(item.id)}">归档</button>` : item.status === 'archived' ? `<button data-restore-workspace="${esc(item.id)}">恢复</button>` : ''}${item.status !== 'quarantined' ? `<button data-quarantine-workspace="${esc(item.id)}">移入可恢复隔离区</button>` : ''}</div></article>`).join('');
  const workspaceOptions = state.workspaces.filter((item) => item.status === 'active').map((item) => `<option value="${esc(item.id)}">${esc(item.displayName)}</option>`).join('');
  return `<div class="columns"><section class="panel"><h3>数据空间</h3><form id="create-workspace-form" class="compact-form"><input name="displayName" placeholder="新数据空间名称" required><select name="kind"><option value="personal">personal</option><option value="sandbox">sandbox</option></select><button class="primary">创建</button></form><div class="list">${workspaceRows}</div>${state.controlUndo ? `<div class="notice success">可撤销：${esc(state.controlUndo.operationType)} <button id="undo-control">撤销</button></div>` : ''}</section><section class="panel"><h3>API Access Token</h3><p>token 明文只显示一次；不要复制到浏览器代码或日志。</p><form id="token-form" class="compact-form"><input name="name" placeholder="例如：FRAG local" required><select name="workspaceId">${workspaceOptions}</select><select name="scope"><option value="ledger:read">只读</option><option value="ledger:write">读写</option></select><button>创建 token</button></form>${state.oneTimeToken ? `<div class="token-once"><strong>仅显示一次</strong><code>${esc(state.oneTimeToken)}</code></div>` : ''}<div class="list">${state.accessTokens.map((item) => `<article><div><strong>${esc(item.name)}</strong><small>${esc(item.scopes.join(', '))} · ${item.revokedAt ? 'revoked' : 'active'}</small></div>${item.revokedAt ? '' : `<button data-revoke-token="${esc(item.id)}">撤销 token</button>`}</article>`).join('') || '<p class="empty">尚无 access token。</p>'}</div></section></div><section class="panel"><h3>关于 Finance Core 3.1.1</h3><p>API ${esc(state.health.apiVersion)} · Ledger schema ${state.health.ledgerSchemaVersion} · Registry schema ${state.health.registrySchemaVersion}。v1/v2 已停止注册；历史说明和 Horizon 文档不占用主导航。</p></section>`;
}

function render() {
  const views = { overview, master: masterData, transactions, holdings: holdingsView, world: worldView, automation, settings: settingsView };
  const options = state.workspaces.filter((item) => item.status !== 'quarantined').map((item) => `<option value="${esc(item.id)}" ${item.id === state.workspace.id ? 'selected' : ''}>${esc(item.displayName)} · ${item.kind}</option>`).join('');
  app.innerHTML = `<header class="app-header"><div><p class="eyebrow">FINANCE CORE 3.1</p><h1>Personal Finance Core</h1></div><div class="workspace-tools"><label>数据空间<select id="workspace-switch">${options}</select></label><span class="badge ${state.workspace.kind}">${esc(state.workspace.kind.toUpperCase())}</span><span class="badge">API ${esc(state.health.apiVersion)} · Ledger ${state.health.ledgerSchemaVersion}</span><button id="sign-out">退出</button></div></header>${nav()}${notice()}${state.busy ? `<div class="busy-bar"><span class="loader"></span>${esc(state.busy)}</div>` : ''}<div class="view" ${state.busy ? 'aria-busy="true"' : ''}>${views[state.active]()}</div><footer>本地优先 · 确定性财务系统 · 不连接银行、券商、LLM 或实时行情</footer>`;
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
  state.error = ''; state.message = ''; state.busy = message || '正在处理…'; render();
  try {
    await work(); state.message = message || '操作成功。';
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
    state.active = 'overview'; state.error = ''; state.message = ''; state.busy = '正在切换数据空间并加载概览…'; render();
    try { await refresh(); } catch (error) { if (error.name !== 'AbortError') state.error = error.message; }
    if (state.workspace?.id === workspaceId) { state.busy = ''; render(); }
  });
  document.querySelector('#sign-out')?.addEventListener('click', async () => {
    await request('/api/v3/session', { method: 'DELETE' }); state.user = null; state.workspace = null; renderLogin();
  });
  document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', async () => {
    const view = button.dataset.tab;
    state.active = view; state.error = ''; state.message = ''; state.busy = `正在加载${button.textContent}…`; render();
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
    act(async () => { const result = await request('/api/v3/workspaces', { method: 'POST', body: JSON.stringify({ displayName: data.get('displayName'), kind: data.get('kind') }) }); state.controlUndo = result.undo; await refreshControl(); }, '数据空间已创建。');
  });
  document.querySelectorAll('[data-archive-workspace]').forEach((button) => button.addEventListener('click', () => act(async () => { const result = await request(`/api/v3/workspaces/${button.dataset.archiveWorkspace}`, { method: 'PATCH', body: JSON.stringify({ status: 'archived' }) }); state.controlUndo = result.undo; await refreshControl(); }, '数据空间已归档。')));
  document.querySelectorAll('[data-restore-workspace]').forEach((button) => button.addEventListener('click', () => act(async () => { const result = await request(`/api/v3/workspaces/${button.dataset.restoreWorkspace}`, { method: 'PATCH', body: JSON.stringify({ status: 'active' }) }); state.controlUndo = result.undo; await refreshControl(); }, '数据空间已恢复。')));
  document.querySelectorAll('[data-quarantine-workspace]').forEach((button) => button.addEventListener('click', () => {
    if (!ask('确认将此 Vault 移入 30 天可恢复隔离区？')) return;
    act(async () => { const result = await request(`/api/v3/workspaces/${button.dataset.quarantineWorkspace}`, { method: 'DELETE' }); state.controlUndo = result.undo; const removedCurrent = state.workspace.id === button.dataset.quarantineWorkspace; await refreshControl(); if (removedCurrent) state.workspace = state.workspaces.find((item) => item.status === 'active') || null; }, 'Vault 已移入可恢复隔离区。');
  }));
  document.querySelector('#undo-control')?.addEventListener('click', () => act(async () => { await request('/api/v3/undo', { method: 'POST', body: JSON.stringify({ undoToken: state.controlUndo.undoToken }) }); state.controlUndo = null; await refreshControl(); }, '控制层操作已撤销。'));
  document.querySelector('#token-form')?.addEventListener('submit', (event) => {
    event.preventDefault(); const data = new FormData(event.target); const scope = data.get('scope');
    act(async () => { const result = await request('/api/v3/access-tokens', { method: 'POST', body: JSON.stringify({ name: data.get('name'), workspaceIds: [data.get('workspaceId')], scopes: scope === 'ledger:write' ? ['ledger:read', 'ledger:write'] : ['ledger:read'] }) }); state.oneTimeToken = result.token; await refreshControl(); }, 'Access token 已创建。');
  });
  document.querySelectorAll('[data-revoke-token]').forEach((button) => button.addEventListener('click', () => act(async () => { await request(`/api/v3/access-tokens/${button.dataset.revokeToken}/revoke`, { method: 'POST' }); await refreshControl(); }, 'Access token 已撤销。')));
  document.querySelector('#refresh')?.addEventListener('click', () => act(async () => {}, '已刷新。'));
  document.querySelector('#undo-latest')?.addEventListener('click', () => act(() => request('/api/v3/undo', { method: 'POST', body: JSON.stringify({ undoToken: state.undo.undoToken, workspaceId: state.workspace.id }) }), '上一步普通操作已撤销。'));
  document.querySelector('#load-demo')?.addEventListener('click', () => act(() => request('/api/v2/demo/load-synthetic', { method: 'POST' }), '合成主数据和 opening draft 已装载。'));
  document.querySelector('#commodity-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/commodities', { method: 'POST', body: JSON.stringify({ code: data.get('code'), kind: data.get('kind'), scale: Number(data.get('scale')), name: data.get('name'), status: 'active' }) }), 'Commodity 已新增。'); });
  document.querySelector('#account-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/accounts', { method: 'POST', body: JSON.stringify({ id: newId('account'), code: data.get('code'), name: data.get('name'), type: data.get('type'), subtype: data.get('subtype'), allowedCommodityCodes: [data.get('commodity')], status: 'active' }) }), '账户已新增。'); });
  document.querySelector('#quote-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/price-quotes', { method: 'POST', body: JSON.stringify({ id: newId('quote'), commodityCode: data.get('commodityCode'), quoteCommodityCode: data.get('quoteCommodityCode'), price: data.get('price'), asOf: new Date(data.get('asOf')).toISOString(), source: data.get('source') }) }), '价格已新增。'); });
  document.querySelectorAll('[data-inactivate-commodity]').forEach((button) => button.addEventListener('click', () => { const item = state.commodities.find((value) => value.code === button.dataset.inactivateCommodity); act(() => request(`/api/v2/commodities/${item.code}`, { method: 'PUT', body: JSON.stringify({ ...item, status: 'inactive' }) }), 'Commodity 已停用。'); }));
  document.querySelectorAll('[data-inactivate-account]').forEach((button) => button.addEventListener('click', () => { const item = state.accounts.find((value) => value.id === button.dataset.inactivateAccount); act(() => request(`/api/v2/accounts/${item.id}`, { method: 'PUT', body: JSON.stringify({ ...item, status: 'inactive' }) }), '账户已停用。'); }));
  document.querySelectorAll('[data-delete-quote]').forEach((button) => button.addEventListener('click', () => act(() => request(`/api/v2/price-quotes/${button.dataset.deleteQuote}`, { method: 'DELETE' }), '价格已删除。')));
  document.querySelector('#new-draft')?.addEventListener('click', () => { state.editor = blankDraft(); state.validation = null; render(); });
  document.querySelector('#add-posting')?.addEventListener('click', () => { state.editor = readEditor(); state.editor.postings.push({ id: newId('posting'), accountId: state.accounts[0]?.id || '', side: 'debit', units: '0', commodityCode: state.editor.balancingCommodityCode, cashFlowCategory: 'other', lotAllocations: [] }); render(); });
  document.querySelectorAll('[data-remove-posting]').forEach((button) => button.addEventListener('click', () => { state.editor = readEditor(); state.editor.postings.splice(Number(button.dataset.removePosting), 1); render(); }));
  document.querySelector('#draft-form')?.addEventListener('submit', (event) => { event.preventDefault(); state.editor = readEditor(); const exists = state.drafts.some((item) => item.draft.id === state.editor.id); act(() => request(`/api/v2/journal-entry-drafts${exists ? `/${state.editor.id}` : ''}`, { method: exists ? 'PUT' : 'POST', body: JSON.stringify(state.editor) }), '草稿已保存。'); });
  document.querySelector('#validate-draft')?.addEventListener('click', () => { state.editor = readEditor(); const exists = state.drafts.some((item) => item.draft.id === state.editor.id); act(async () => { if (!exists) await request('/api/v2/journal-entry-drafts', { method: 'POST', body: JSON.stringify(state.editor) }); else await request(`/api/v2/journal-entry-drafts/${state.editor.id}`, { method: 'PUT', body: JSON.stringify(state.editor) }); state.validation = await request(`/api/v2/journal-entry-drafts/${state.editor.id}/validate`, { method: 'POST' }); }, '验证完成。'); });
  document.querySelector('#post-draft')?.addEventListener('click', () => { state.editor = readEditor(); if (!ask('确认将此完整聚合写入不可变账本？')) return; act(async () => { const exists = state.drafts.some((item) => item.draft.id === state.editor.id); if (!exists) await request('/api/v2/journal-entry-drafts', { method: 'POST', body: JSON.stringify(state.editor) }); else await request(`/api/v2/journal-entry-drafts/${state.editor.id}`, { method: 'PUT', body: JSON.stringify(state.editor) }); await request(`/api/v2/journal-entry-drafts/${state.editor.id}/post`, { method: 'POST' }); state.editor = blankDraft(); state.validation = null; }, '交易已过账。'); });
  document.querySelectorAll('[data-edit-draft]').forEach((button) => button.addEventListener('click', () => { state.editor = structuredClone(state.drafts.find((item) => item.draft.id === button.dataset.editDraft).draft); state.validation = null; render(); }));
  document.querySelectorAll('[data-validate-stored]').forEach((button) => button.addEventListener('click', () => act(async () => { state.validation = await request(`/api/v2/journal-entry-drafts/${button.dataset.validateStored}/validate`, { method: 'POST' }); state.editor = structuredClone(state.drafts.find((item) => item.draft.id === button.dataset.validateStored).draft); }, '验证完成。')));
  document.querySelectorAll('[data-post-stored]').forEach((button) => button.addEventListener('click', () => { if (ask('确认过账此草稿？')) act(() => request(`/api/v2/journal-entry-drafts/${button.dataset.postStored}/post`, { method: 'POST' }), '交易已过账。'); }));
  document.querySelectorAll('[data-delete-draft]').forEach((button) => button.addEventListener('click', () => act(() => request(`/api/v2/journal-entry-drafts/${button.dataset.deleteDraft}`, { method: 'DELETE' }), '草稿已删除。')));
  document.querySelectorAll('[data-reverse-entry]').forEach((button) => button.addEventListener('click', () => { if (ask('确认创建 linked reversal？原交易不会被删除。')) act(() => request(`/api/v2/journal-entries/${button.dataset.reverseEntry}/reverse`, { method: 'POST' }), '冲销交易已创建。'); }));
  document.querySelector('#living-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/living-accounts', { method: 'POST', body: JSON.stringify({ id: newId('living'), name: data.get('name'), commodityCode: data.get('commodityCode'), balance: data.get('balance'), note: data.get('note'), updatedAt: new Date().toISOString() }) }), '生活账户已新增。'); });
  document.querySelectorAll('[data-record-balance]').forEach((button) => button.addEventListener('click', () => { const input = document.querySelector(`[data-balance-input="${button.dataset.recordBalance}"]`); act(() => request(`/api/v2/living-accounts/${button.dataset.recordBalance}/record-balance`, { method: 'POST', body: JSON.stringify({ balance: input.value }) }), '余额与快照已原子记录。'); }));
  document.querySelector('#plan-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); act(() => request('/api/v2/monthly-plans', { method: 'POST', body: JSON.stringify({ id: newId('plan'), kind: data.get('kind'), name: data.get('name'), amount: data.get('amount'), commodityCode: data.get('commodityCode'), category: data.get('category'), recurringMonthly: true, dayOfMonth: Number(data.get('dayOfMonth')), startDate: data.get('startDate'), note: '' }) }), '月度计划已新增。'); });
  document.querySelectorAll('[data-delete-plan]').forEach((button) => button.addEventListener('click', () => act(() => request(`/api/v2/monthly-plans/${button.dataset.deletePlan}`, { method: 'DELETE' }), '月度计划已删除。')));
  document.querySelector('#recurring-form')?.addEventListener('submit', (event) => { event.preventDefault(); const data = new FormData(event.target); const template = structuredClone(state.editor); template.id = `${data.get('id')}-template`; template.postings = template.postings.map((item, index) => ({ ...item, id: `${template.id}-p${index + 1}` })); act(() => request('/api/v2/recurring-entry-rules', { method: 'POST', body: JSON.stringify({ id: data.get('id'), name: data.get('name'), enabled: true, frequency: 'monthly', dayOfMonth: Number(data.get('dayOfMonth')), startDate: data.get('startDate'), template, generatedPeriods: [] }) }), '周期模板已保存。'); });
  document.querySelector('#generate-due')?.addEventListener('click', () => act(() => request('/api/v2/recurring-entry-rules/generate-due', { method: 'POST', body: JSON.stringify({ asOf: today() }) }), '到期草稿已生成。'));
  document.querySelectorAll('[data-toggle-rule]').forEach((button) => button.addEventListener('click', () => { const item = state.recurring.find((value) => value.id === button.dataset.toggleRule); act(() => request(`/api/v2/recurring-entry-rules/${item.id}`, { method: 'PUT', body: JSON.stringify({ ...item, enabled: !item.enabled }) }), '周期规则状态已更新。'); }));
  document.querySelectorAll('[data-delete-rule]').forEach((button) => button.addEventListener('click', () => act(() => request(`/api/v2/recurring-entry-rules/${button.dataset.deleteRule}`, { method: 'DELETE' }), '周期规则已删除。')));
  document.querySelector('#import-drafts')?.addEventListener('click', () => act(() => request('/api/v2/import/drafts', { method: 'POST', body: document.querySelector('#import-json').value }), 'Drafts 已验证并导入。'));
  document.querySelector('#import-drafts-csv')?.addEventListener('click', () => act(async () => { const file = document.querySelector('#import-csv').files[0]; if (!file) throw new Error('请先选择 CSV 文件。'); await request('/api/v2/import/drafts.csv', { method: 'POST', body: await file.text(), headers: { 'Content-Type': 'text/csv' } }); }, 'CSV Drafts 已验证并导入。'));
  document.querySelector('#run-batch')?.addEventListener('click', () => act(() => request('/api/v2/batch', { method: 'POST', body: document.querySelector('#batch-json').value }), 'Mutable batch 已原子执行。'));
  document.querySelector('#restore-backup')?.addEventListener('click', () => { if (!ask('恢复只适用于空 v2 ledger。确认验证并恢复此备份？')) return; act(async () => { const file = document.querySelector('#backup-file').files[0]; if (!file) throw new Error('请先选择 JSON 备份。'); const wrapper = JSON.parse(await file.text()); await request('/api/v2/backup/restore', { method: 'POST', body: JSON.stringify(wrapper.data || wrapper) }); }, '备份已验证并恢复。'); });
}

function renderLogin(error = '') {
  app.innerHTML = `<section class="status auth-card"><p class="eyebrow">FINANCE CORE 3.1</p><h1>进入本地财务系统</h1><p>管理令牌只用于换取本机 HttpOnly 会话，不会写入浏览器存储。</p>${error ? `<div class="notice error">${esc(error)}</div>` : ''}<form id="login-form"><label>管理令牌<input name="adminToken" type="password" autocomplete="current-password" required></label><button class="primary" type="submit">进入 Finance Core</button></form></section>`;
  document.querySelector('#login-form').addEventListener('submit', async (event) => {
    event.preventDefault(); const data = new FormData(event.target);
    try { await request('/api/v3/session', { method: 'POST', body: JSON.stringify({ adminToken: data.get('adminToken') }) }); await load(); } catch (loginError) { renderLogin(loginError.message); }
  });
}

function renderWorkspaceWizard(error = '') {
  const archived = state.workspaces.filter((item) => item.status === 'archived').map((item) => `<button data-wizard-restore="${esc(item.id)}">恢复 ${esc(item.displayName)}</button>`).join('');
  app.innerHTML = `<section class="status wizard"><p class="eyebrow">NO ACTIVE VAULT</p><h1>创建第一个数据空间</h1><p>每个数据空间拥有独立的 Commodity、账户、草稿、账本、持仓和计划数据库。</p>${error ? `<div class="notice error">${esc(error)}</div>` : ''}${archived ? `<div class="archived-options"><strong>恢复已归档数据空间</strong>${archived}</div>` : ''}<form id="workspace-form"><label>名称<input name="displayName" placeholder="例如：Soren Personal" required maxlength="120"></label><label>类型<select name="kind"><option value="personal">Personal · 个人数据</option><option value="sandbox">Sandbox · 测试数据</option></select></label><button class="primary" type="submit">创建并进入</button></form></section>`;
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
  app.innerHTML = '<section class="status"><span class="loader" aria-hidden="true"></span>正在连接 Finance Core 3.1…</section>';
  try {
    state.health = await request('/api/v3/health');
    state.user = (await request('/api/v3/me')).data;
    state.workspaces = (await request('/api/v3/workspaces')).data;
    const active = state.workspaces.filter((item) => item.status === 'active');
    if (!active.length) { renderWorkspaceWizard(); return; }
    state.workspace = active.find((item) => item.id === state.workspace?.id) || active[0];
    clearWorkspaceData();
    state.active = 'overview'; state.busy = '已连接，正在加载概览…'; render();
    await refresh('overview'); state.busy = ''; render();
  } catch (error) {
    if (error.status === 401) { renderLogin(); return; }
    app.innerHTML = `<section class="status error"><h1>Finance Core 暂不可用</h1><p>${esc(error.message)}</p><button id="retry">重试</button></section>`;
    document.querySelector('#retry').addEventListener('click', load);
  }
}

void load();
