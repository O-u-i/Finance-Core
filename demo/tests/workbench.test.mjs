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

test('T-accounts use one vertical container per account, with Credit before Debit', async () => {
  const { Reports } = await server.ssrLoadModule('/demo/src/pages/Dashboard.jsx');
  const html = render(Reports, { fc: { route: { view: 'taccounts' }, data: { tAccounts: [
    { accountId: 'a', accountCode: '1002', accountName: 'Bank B', commodityCode: 'USD', credit: '2', debit: '3', balance: '1' },
    { accountId: 'b', accountCode: '1001', accountName: 'Bank A', commodityCode: 'CNY', credit: '7', debit: '9', balance: '2' },
  ] } } });
  assert.equal((html.match(/class="t-account-card"/g) || []).length, 2);
  assert.ok(html.indexOf('1001') < html.indexOf('1002'));
  assert.ok(html.indexOf('>Credit<') < html.indexOf('>Debit<'));
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
  assert.match(html, /Day of month.*1–31/);
  assert.match(html, /Scheduled category totals/);
  assert.match(html, /CF inflow/);
});

test('Asset registry retains its Note separately from valuation context and explains the valuation month', async () => {
  const { AssetsLiabilities } = await server.ssrLoadModule('/demo/src/pages/PersonalFinance.jsx');
  const html = render(AssetsLiabilities, { fc: { route: { view: 'assets', tab: '2026-09', segment: 'living' }, data: {
    parties: [{ id: 'owner', name: 'Synthetic owner' }], commodities: [{ code: 'CNY', kind: 'currency', status: 'active' }],
    assets: [{ id: 'bicycle', name: 'Synthetic bicycle', assetType: 'Bicycle', currency: 'CNY', purchasedDate: '2026-01-03', purchaseCost: '120', ownershipShare: '1', ownerPartyId: 'owner', note: 'Synthetic registry context' }],
    observations: [{ id: 'value', subjectId: 'bicycle', month: '2026-09', kind: 'valuation', amount: '90', currency: 'CNY', source: 'Synthetic valuation', note: 'Synthetic valuation context', confirmed: true }],
  } } });
  assert.match(html, /Synthetic registry context/);
  assert.match(html, /Saved valuation/);
  assert.match(html, /2026-09-30/);
  assert.doesNotMatch(html, /As-of month \(balances are month-end observations\)/);
  assert.match(html, /Save valuation/);
  assert.match(html, /Record disposal/);
});

test('Journal lists expose independent searchable date and description ordering', async () => {
  const { default: Journal } = await server.ssrLoadModule('/demo/src/pages/Journal.jsx');
  const html = render(Journal, { fc: { route: { view: 'journal' }, data: { commodities: [], accounts: [], drafts: [], entries: [] } } });
  assert.match(html, /Filter Unposted drafts/);
  assert.match(html, /Filter Posted journal/);
  assert.equal((html.match(/aria-label="Sort ascending"/g) || []).length, 2);
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
