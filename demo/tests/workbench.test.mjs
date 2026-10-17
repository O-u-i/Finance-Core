import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server, components;
before(async () => {
  server = await createServer({ configFile: false, cacheDir: '.tmp/ui-render-cache', optimizeDeps: { noDiscovery: true, entries: [] }, server: { middlewareMode: true, watch: null, hmr: false } });
  components = await server.ssrLoadModule('/demo/src/components.jsx');
});
after(async () => { await server?.close(); });
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));

test('ready identity can be FINCR-only without changing the full authentication Logo', () => {
  assert.match(render(components.Logo, {}), /Finance Core/);
  const ready = render(components.Logo, { markOnly:true, small:true });
  assert.match(ready, /alt="FINCR"/);
  assert.doesNotMatch(ready, /Finance Core|Local finance/);
});

test('shared record rows keep exact amounts, metadata, semantic state and fixed action slots', () => {
  const html = render(components.RecordRow, { title:'Synthetic account', meta:'2026-09-12', amount:'9007199254740993.12', currency:'CNY',
    status:React.createElement(components.Status,{state:'warning'},'Pending'), actions:React.createElement('button',{},'Details') });
  for(const slot of ['record-identity','record-primary','record-actions']) assert.match(html,new RegExp(slot));
  assert.match(html,/9007199254740993.12/); assert.match(html,/data-state="warning"/);
  assert.ok(html.indexOf('record-identity')<html.indexOf('record-primary')&&html.indexOf('record-primary')<html.indexOf('record-actions'));
});

test('ordinary panel explanations use help while irreversible notices remain visible', () => {
  const html = render(components.Panel, { title:'Synthetic operation', description:'Ordinary calculation explanation.', notice:'No ordinary undo.' });
  assert.match(html, /class="help-trigger"/); assert.doesNotMatch(html, /<p>Ordinary calculation/);
  assert.match(html, /<p class="notice">No ordinary undo\.<\/p>/);
});

test('branched navigation exposes page headings as controlled second-level destinations', async () => {
  const { default: Sidebar } = await server.ssrLoadModule('/demo/src/BranchedMenu.jsx');
  const html = render(Sidebar, { items:[{key:'journal',label:'Journal'},{key:'review',label:'Monthly review',children:[{key:'review-body',label:'Investment monthly review'},{key:'close',label:'Immutable month close'}]}], activeKey:'review',activeSection:'close' });
  assert.match(html, /aria-expanded="true"/);
  assert.match(html, /Investment monthly review/); assert.match(html, /Immutable month close/);
  assert.match(html, /aria-current="location"/);
  assert.match(html, /<svg/);
});

test('branched navigation retains multiple independently open groups instead of a route-only accordion', async () => {
  const { default: Menu } = await server.ssrLoadModule('/demo/src/BranchedMenu.jsx');
  const html = render(Menu, { items:[{key:'journal',label:'Journal',children:[{key:'drafts',label:'Unposted drafts'},{key:'entries',label:'Posted journal'}]},
    {key:'review',label:'Monthly review',children:[{key:'review-body',label:'Investment monthly review'},{key:'close',label:'Immutable month close'}]}], activeKey:'review',defaultOpen:['journal','review'] });
  assert.equal((html.match(/aria-expanded="true"/g)||[]).length,2);
  assert.doesNotMatch(html,/hidden=""/);
});

test('single-section pages do not repeat their heading as a branch; folded groups stay inert for a CSS transition', async () => {
  const { default: Menu } = await server.ssrLoadModule('/demo/src/BranchedMenu.jsx');
  const html = render(Menu,{items:[{key:'positions',label:'Securities & positions',children:[{key:'one',label:'Securities & positions'}]},
    {key:'journal',label:'Journal',children:[{key:'drafts',label:'Unposted drafts'},{key:'entries',label:'Posted journal'}]}],activeKey:'positions'});
  assert.equal((html.match(/Securities &amp; positions/g)||[]).length,1);
  assert.match(html,/branched-menu__fold/); assert.match(html,/inert=""/);
  assert.doesNotMatch(html,/ hidden=""/);
});

test('legacy review has compact controls and stable sections even without activity, with completeness visible', async () => {
  const { default: Review } = await server.ssrLoadModule('/demo/src/pages/MonthlyReview.jsx');
  const html = render(Review,{fc:{route:{view:'monthlyreview'},data:{monthlyReview:{month:'2026-09',status:'ready',months:[{month:'2026-09',currencies:[]}],windowStart:'2026-07-01',windowEndExclusive:'2026-10-01',calculationVersion:'monthly-activity-v1',openingEntryIds:[]}}}});
  assert.match(html,/Three-month comparison/); assert.match(html,/Corrections and coverage/);
  assert.match(html,/External completeness unknown/); assert.match(html,/Calculation and source revision/);
  assert.doesNotMatch(html,/Your month, in context|CLOSED-MONTH REVIEW/);
});

test('record tables expose sort direction and order decimal strings without losing precision', () => {
  const html = render(components.Table, { caption: 'Synthetic balances', columns: [['amount', 'Amount']],
    rows: [{ amount: '9007199254740993.12' }, { amount: '-2' }, { amount: '0.09' }, { amount: '0.1' }] });
  assert.match(html, /Sort by/);
  assert.match(html, /Sort descending/);
  assert.ok(html.indexOf('>-2<') < html.indexOf('>0.09<'));
  assert.ok(html.indexOf('>0.09<') < html.indexOf('>0.1<'));
  assert.ok(html.indexOf('>0.1<') < html.indexOf('>9007199254740993.12<'));
});

test('Overview keeps reconciliation checks available without dumping technical IDs into the page', async () => {
  const { PersonalOverview } = await server.ssrLoadModule('/demo/src/pages/PersonalFinance.jsx');
  const html = render(PersonalOverview, { fc: { route: {}, data: { commodities: [], financialAccounts: [], personalReport: {
    asOf: '2026-09-30', coverage: { complete: false }, currencies: [],
    issues: [{ code: 'OPENING_BALANCE_MISSING', subjectId: 'synthetic-account-id', message: 'Missing input.' }],
  } } } });
  assert.match(html, /Review data checks/);
  assert.doesNotMatch(html, /synthetic-account-id/);
  assert.match(html, /2026-09-30/);
});

test('T-accounts show exact server balances in clickable account/currency summary cards', async () => {
  const { Reports } = await server.ssrLoadModule('/demo/src/pages/Dashboard.jsx');
  const html = render(Reports, { fc: { route: { view: 'taccounts' }, data: { tAccounts: [
    { accountId: 'a', accountCode: '1002', accountName: 'Bank B', commodityCode: 'USD', credit: '2', debit: '3', balance: '1' },
    { accountId: 'b', accountCode: '1001', accountName: 'Bank A', commodityCode: 'CNY', credit: '7', debit: '9', balance: '2' },
  ] } } });
  assert.equal((html.match(/class="t-account-card"/g) || []).length, 2);
  assert.ok(html.indexOf('1001') < html.indexOf('1002'));
  assert.match(html, /class="t-account-grid"/);
  assert.match(html, /View postings for 1001 Bank A, CNY/);
  assert.match(html, />Balance</);
  assert.doesNotMatch(html, />Difference<|>Normal balance<|>Posting count<|<table/);
  assert.match(html, />Debit</); assert.match(html, />Credit</);
});

test('Monthly plans expose category, edit, delete, due-date wording and backend category totals', async () => {
  const { default: Planning } = await server.ssrLoadModule('/demo/src/pages/Planning.jsx');
  const html = render(Planning, { fc: { route: { view: 'plans' }, data: { commodities: [{ code: 'CNY', kind: 'currency', status: 'active' }],
    plans: [{ id: 'salary', name: 'Synthetic salary', category: 'Work', kind: 'income', amount: '0.3', commodityCode: 'CNY', dayOfMonth: 13, startDate: '2026-01-01', recurringMonthly: true }],
    planReport: { month: '2026-02', currencies: [], occurrences: [], categories: [{ category: 'Work', currency: 'CNY', inflow: '0.3', outflow: '0', net: '0.3', count: 1 }] },
  } } });
  assert.match(html, />Category</);
  assert.match(html, />Edit</);
  assert.match(html, />Delete</);
  assert.match(html, /Due day.*1–31/);
  assert.match(html, /Scheduled category totals/);
  assert.match(html, /CF inflow/);
});

test('cash-flow plans offer monthly, quarterly, semi-annual, annual and one-time schedules with contextual help', async () => {
  const { default: Plans } = await server.ssrLoadModule('/demo/src/pages/MonthlyPlans.jsx');
  const html = render(Plans, { fc: { route: { view: 'plans' }, data: { commodities: [{ code:'CNY',kind:'currency',status:'active' }], plans:[] } } });
  for (const label of ['Monthly', 'Quarterly', 'Semi-annual', 'Annual', 'One time', 'Repeat interval', 'Due day']) assert.match(html, new RegExp(label));
  assert.match(html, /start month/);
  assert.doesNotMatch(html, />Frequency<|Monthly cash-flow plans/);
});

test('shared date, month and file controls have English application-owned affordances', () => {
  for (const type of ['date', 'month', 'datetime-local', 'file']) {
    const html = render(components.Field, { label: 'Synthetic '+type, children: React.createElement('input', { type, name: 'synthetic', required: true }) });
    if (type === 'file') { assert.match(html, /Choose file/); assert.match(html, /No file selected/); }
    else { assert.match(html, /type="text"/); assert.match(html, /YYYY-MM/); }
  }
  assert.doesNotMatch(render(components.Field,{label:'Journal date',type:'date',required:true}),/type="date"/);
});

test('Asset rows prioritize server valuation and status; Note and forms are secondary dialog content', async () => {
  const { AssetsLiabilities } = await server.ssrLoadModule('/demo/src/pages/PersonalFinance.jsx');
  const html = render(AssetsLiabilities, { fc: { route: { view: 'assets', tab: '2026-09', segment: 'living' }, data: {
    parties: [{ id: 'owner', name: 'Synthetic owner' }], commodities: [{ code: 'CNY', kind: 'currency', status: 'active' }],
    assets: [{ id: 'bicycle', name: 'Synthetic bicycle', assetType: 'Bicycle', currency: 'CNY', purchasedDate: '2026-01-03', purchaseCost: '120', ownershipShare: '1', ownerPartyId: 'owner', note: 'Synthetic registry context' }],
    observations: [{ id: 'value', subjectId: 'bicycle', month: '2026-09', kind: 'valuation', amount: '90', currency: 'CNY', source: 'Synthetic valuation', note: 'Synthetic valuation context', confirmed: true }],
  } } });
  assert.match(html, /asset-record/);
  assert.match(html, />90<span class="record-currency">CNY/);
  assert.match(html, />Confirmed</);
  assert.doesNotMatch(html, /Synthetic registry context|Synthetic valuation context|<form|<textarea/);
  assert.match(html, /2026-09-30/);
  assert.doesNotMatch(html, /As-of month \(balances are month-end observations\)/);
  assert.match(html, /Edit valuation/);
  assert.match(html, /Details/);
});

test('Journal lists expose independent searchable date and description ordering', async () => {
  const { default: Journal } = await server.ssrLoadModule('/demo/src/pages/Journal.jsx');
  const html = render(Journal, { fc: { route: { view: 'journal' }, data: { commodities: [], accounts: [], drafts: [], entries: [] } } });
  assert.match(html, /Filter Unposted drafts/);
  assert.match(html, /Filter Posted journal/);
  assert.equal((html.match(/aria-label="Sort ascending"/g) || []).length, 2);
});

test('Overview presents both segments without empty charts or combining financial amounts', async () => {
  const { FinanceOverview } = await server.ssrLoadModule('/demo/src/pages/RecordedBalances.jsx');
  const html = render(FinanceOverview, {fc:{route:{view:'overview',month:'2026-09'},data:{
    entries:[{id:'entry',date:'2026-09-12',description:'Synthetic posted record',balancingCommodityCode:'CNY',postings:[]}],
    recordedReport:{accounts:[{accountId:'living',code:'L001',name:'Synthetic Living record',observedDate:'2026-09-14',amount:'0.13',currency:'CNY',status:'confirmed'}]},
    assets:[],
  }}});
  assert.match(html,/Synthetic posted record/); assert.match(html,/Synthetic Living record/);
  assert.match(html,/Investment · Journal/); assert.match(html,/Living · L001/);
  assert.match(html,/0.13/); assert.doesNotMatch(html,/<canvas|chart-placeholder/);
  assert.match(html,/Record mix/); assert.match(html,/Record states/);
  assert.match(html,/Record counts, not financial totals/);
});

test('review account cards retain exact balances, unknown states and independent currencies', async () => {
  const { RecordedBalanceReadout } = await server.ssrLoadModule('/demo/src/pages/RecordedBalances.jsx');
  const html = render(RecordedBalanceReadout, { report:{month:'2026-09',accounts:[
    {accountId:'one',code:'L1',name:'Synthetic one',currency:'CNY',amount:'9007199254740993.12',status:'confirmed'},
    {accountId:'two',code:'L2',name:'Synthetic two',currency:'USD',amount:null,status:'unknown'},
  ]} });
  assert.match(html,/summary-card-grid/); assert.match(html,/9007199254740993.12/);
  assert.match(html,/USD/); assert.match(html,/Unknown/); assert.doesNotMatch(html,/<table/);
});

test('Batch creation and ownership agreements offer structured fields instead of required JSON input', async () => {
  const { default: Batch } = await server.ssrLoadModule('/demo/src/pages/AtomicBatch.jsx');
  const { default: Agreement } = await server.ssrLoadModule('/demo/src/pages/AgreementEditor.jsx');
  const fc = { data: { commodities: [{ code: 'CNY', kind: 'currency', status: 'active' }], parties: [{ id: 'owner', name: 'Synthetic owner' }], financialAccounts: [], drafts: [] } };
  const batch = render(Batch, { fc });
  assert.match(batch, /New code/); assert.match(batch, /Stage new record/);
  assert.match(batch, /cannot edit existing records/); assert.doesNotMatch(batch, /<textarea/);
  const agreement = render(Agreement, { fc, initial: { id: 'agreement', version: 1, currency: 'CNY', fromMonth: '2026-09', residualShares: [{ partyId: 'owner', share: '1' }], claims: [], interestAgreements: [], reason: '' } });
  assert.match(agreement, /Residual share \(0–1\)/); assert.match(agreement, /Add beneficiary share/);
  assert.match(agreement, /Beneficiary claims/); assert.doesNotMatch(agreement, /JSON contract/);
});
