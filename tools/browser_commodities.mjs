// Public UI + Workspace API only, on caller-owned synthetic servers and browser profile.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';

const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + sep));
const fixture = JSON.parse(readFileSync(join(run, 'fixture.json'), 'utf8'));
assert.equal(fixture.syntheticOnly, true);
assert(process.env.FC_AGENT_BROWSER && process.env.AGENT_BROWSER_SESSION && process.env.AGENT_BROWSER_NAMESPACE);
const stage = process.argv[2] || 'all';
assert(['overview', 'delete', 'all'].includes(stage));
const evidence = join(run, 'commodity-' + stage);
mkdirSync(evidence, { recursive: true });
const command = (...args) => {
  const result = JSON.parse(execFileSync(process.env.FC_AGENT_BROWSER, ['--json', ...args], { encoding: 'utf8', timeout: 40000 }));
  assert.equal(result.success, true, result.error || 'Browser command failed');
  return result.data;
};
const evaluate = expression => command('eval', expression).result;
const settled = () => command('wait', '--fn', "!!document.querySelector('.app-shell') && !document.querySelector('.loading-line') && !document.querySelector('[aria-busy=true]')");
const navigate = path => { evaluate(`location.hash=${JSON.stringify(path)}`); settled(); };
const currencyRows = () => evaluate("[...document.querySelectorAll('main tbody tr')].map(row=>row.cells[0]?.textContent.trim())");
const row = code => `[...document.querySelectorAll('main tbody tr')].find(row=>row.cells[0].textContent.trim()===${JSON.stringify(code)})`;
const screenshot = name => {
  if (evaluate("!!document.querySelector('[aria-label=\"Dismiss notification\"]')")) command('click', '[aria-label="Dismiss notification"]');
  evaluate("document.activeElement?.blur();window.scrollTo({top:0,behavior:'instant'});new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))");
  command('screenshot', join(evidence, name), '--full');
};
const checks = [];
try {
  command('open', 'http://localhost:5174/__synthetic_marker');
  assert.equal(evaluate('document.body.textContent'), 'fc-ui-account-fixes-synthetic-only');
  command('set', 'viewport', '1440', '1000');
  command('open', 'http://localhost:5174/#/overview');
  command('wait', '--fn', "!!document.querySelector('input[name=adminToken]') || !!document.querySelector('.app-shell')");
  if (evaluate("!!document.querySelector('input[name=adminToken]')")) {
    command('fill', 'input[name=adminToken]', 'synthetic-browser-admin');
    command('click', 'button[type=submit]');
  }
  settled();
  for (const [workspaceId, legacy] of [[fixture.workspaceId, false], [fixture.legacyWorkspaceId, true]]) {
    command('select', '.workspace-tools select', workspaceId); settled();
    const prefix = '/api/v3/workspaces/' + workspaceId;
    const request = (path, method = 'GET', body) => evaluate(`(async()=>{
      const response=await fetch(${JSON.stringify(prefix + path)},{method:${JSON.stringify(method)},headers:{'Content-Type':'application/json'},${body === undefined ? '' : 'body:JSON.stringify(' + JSON.stringify(body) + ')'}});
      const payload=await response.json();return {status:response.status,...payload};
    })()`);
    for (const code of ['1', '2', 'EMPTY', 'ZUSED']) {
      const existing = request('/commodities').data.find(item => item.code === code);
      if (!existing) {
        assert.equal(request('/commodities', 'POST', { code, name: 'Synthetic ' + code, kind: 'currency', scale: 2 }).status, 201);
      } else if (code === 'EMPTY') assert.equal(request('/commodities/EMPTY', 'PUT', { ...existing, status: 'active' }).status, 200);
    }
    const accountPath = legacy ? '/accounts' : '/financial-accounts';
    if (!request(accountPath).data.some(item => item.id === 'commodity-used')) {
      const account = { id: 'commodity-used', code: 'USED', name: 'Synthetic retained account', type: 'asset', allowedCommodityCodes: ['ZUSED'] };
      if (!legacy) Object.assign(account, { segment: 'living', balanceSource: 'monthly_snapshot', ownerPartyId: 'owner' });
      assert.equal(request(accountPath, 'POST', account).status, 201);
    }
    for (const code of ['1', '2', 'ZUSED']) {
      const item = request('/commodities').data.find(item => item.code === code);
      assert.equal(request('/commodities/' + code, 'PUT', { ...item, status: 'inactive' }).status, 200);
    }
    navigate('#/master'); navigate('#/overview');
    if (stage !== 'delete') {
      const path = legacy ? '/dashboard' : '/reports/personal-balance-sheet?month=2026-08';
      const report = request(path).data;
      screenshot(`${legacy ? 'legacy' : 'current'}-overview.png`);
      assert(!currencyRows().includes('1') && !currencyRows().includes('2'), 'Inactive unused currencies must not clutter Overview.');
      if (!legacy) {
        assert(currencyRows().includes('EMPTY'), 'Active registered currencies remain visible, including zero values.');
        assert(currencyRows().includes('ZUSED'), 'Inactive referenced currencies, including unknown balances, must remain visible.');
      } else assert(currencyRows().includes('CNY'), 'Legacy reports retain their original used-currency rows.');
      if (!legacy) assert(evaluate("[...document.querySelectorAll('.financial-overview')].filter(panel=>panel.querySelector('h2')?.textContent.includes('beneficial ownership')).every(panel=>panel.querySelector('tbody tr'))"), 'Do not render empty ownership cards.');
      assert.deepEqual(request(path).data, report, 'Display filtering must not alter financial calculations, revisions or API reports.');
      checks.push(`${legacy ? 'Schema 2' : 'Schema 3'} safe Overview visibility and unchanged report`);
    }
    if (stage !== 'overview') {
      navigate('#/master');
      assert(evaluate(`${row('1')}?.textContent.includes('Delete unused')`), 'An unused commodity has a deletion action.');
      assert.equal(evaluate(`${row('ZUSED')}.querySelector('button.danger').disabled`), true, 'Referenced commodities cannot be deleted.');
      assert.equal(request('/commodities/ZUSED', 'DELETE').status, 422, 'The backend must independently reject deletion.');
      const before = request('/commodities').data;
      evaluate('window.confirm=()=>false');
      evaluate(`${row('1')}.querySelector('button.danger').click()`); settled();
      assert.deepEqual(request('/commodities').data, before, 'Cancelling deletion makes no mutation.');
      evaluate('window.confirm=()=>true');
      const recent = { id: 'recent-reference', code: 'RECENT', name: 'Synthetic concurrent reference', type: 'asset', allowedCommodityCodes: ['1'] };
      if (!legacy) Object.assign(recent, { segment: 'investment', balanceSource: 'ledger' });
      assert.equal(request(accountPath, 'POST', recent).status, 201);
      evaluate(`${row('1')}.querySelector('button.danger').click()`); settled();
      assert(request('/commodities').data.some(item => item.code === '1'), 'A newly referenced code survives deletion from a stale screen.');
      assert(evaluate("document.querySelector('[role=alert]')?.textContent.includes('history or references')"), 'A refused deletion explains the reference conflict.');
      assert.equal(request(accountPath + '/' + recent.id, 'DELETE').status, 200);
      checks.push(`${legacy ? 'Schema 2' : 'Schema 3'} stale-screen deletion refuses newly added references`);
      evaluate(`${row('EMPTY')}.querySelectorAll('button')[1].click()`); settled();
      assert.equal(request('/commodities').data.find(item => item.code === 'EMPTY').status, 'inactive');
      evaluate(`${row('EMPTY')}.querySelector('button').click()`);
      command('fill', 'input[name=name]', 'Synthetic edited empty currency');
      command('find', 'role', 'button', 'click', '--name', 'Save commodity', '--exact'); settled();
      assert.equal(request('/commodities').data.find(item => item.code === 'EMPTY').name, 'Synthetic edited empty currency');
      assert.equal(request('/commodities').data.find(item => item.code === 'EMPTY').status, 'inactive', 'Editing preserves status and does not send read-only usage flags.');
      checks.push(`${legacy ? 'Schema 2' : 'Schema 3'} deactivate and edit with read-only reference metadata`);
      for (const code of ['1', '2']) {
        evaluate(`${row(code)}.querySelector('button.danger').click()`); settled();
        assert(!request('/commodities').data.some(item => item.code === code));
        assert(!currencyRows().includes(code), 'Deleted rows disappear immediately.');
      }
      screenshot(`${legacy ? 'legacy' : 'current'}-registry.png`);
      navigate('#/overview');
      assert(!currencyRows().includes('1') && !currencyRows().includes('2'));
      assert(!currencyRows().includes('EMPTY'), 'A newly deactivated unused currency disappears on refresh.');
      screenshot(`${legacy ? 'legacy' : 'current'}-overview-after.png`);
      checks.push(`${legacy ? 'Schema 2' : 'Schema 3'} cancel, unused deletion, reference guard and refresh`);
    }
  }
  for (const width of [1024, 1920]) {
    command('set', 'viewport', String(width), '1000'); navigate('#/master');
    assert.equal(evaluate('document.documentElement.scrollWidth <= innerWidth'), true, 'No desktop page overflow.');
    screenshot('registry-' + width + '.png');
  }
  writeFileSync(join(evidence, 'result.json'), JSON.stringify({ syntheticOnly: true, status: 'pass', checks }, null, 2));
  console.log(`PASS: ${checks.length} commodity UI/API scenario groups.`);
} catch (error) {
  writeFileSync(join(evidence, 'result.json'), JSON.stringify({ syntheticOnly: true, status: 'failed', checks, error: String(error) }, null, 2));
  throw error;
}
