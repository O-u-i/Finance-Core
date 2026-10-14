// Public rendered UI / HTTP only. An owned synthetic marker is mandatory before authentication.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + sep));
const fixture = JSON.parse(readFileSync(join(run, 'fixture.json'), 'utf8'));
assert.equal(fixture.syntheticOnly, true);
assert(process.env.FC_AGENT_BROWSER && process.env.AGENT_BROWSER_SESSION && process.env.AGENT_BROWSER_NAMESPACE);
const stage = process.argv[2] || 'startup';
assert(['startup', 'focus', 'plans', 'balances', 'opening', 'all'].includes(stage));
const evidence = join(run, 'opening-ui-' + stage + '-' + Date.now());
mkdirSync(evidence, { recursive: true });
const command = (...args) => {
  const result = JSON.parse(execFileSync(process.env.FC_AGENT_BROWSER, ['--json', ...args], { encoding: 'utf8', timeout: 40000 }));
  assert.equal(result.success, true, result.error || 'Browser command failed');
  return result.data;
};
const evaluate = source => command('eval', source).result;
const settled = () => command('wait', '--fn', "!!document.querySelector('.app-shell') && !document.querySelector('.loading-line') && !document.querySelector('[aria-busy=true]')");
const navigate = path => { evaluate(`location.hash=${JSON.stringify(path)}`); settled(); };
const checks = [];
try {
  command('open', 'http://localhost:5174/__synthetic_marker');
  assert.equal(evaluate('document.body.textContent'), 'fc-ui-account-fixes-synthetic-only');
  command('set', 'viewport', '1440', '1000');
  if (stage === 'startup') {
    evaluate("fetch('/api/v3/session',{method:'DELETE'})");
    evaluate("fetch('/api/__test_health_gate?hold=true').then(response=>response.json())");
    command('open', 'http://localhost:5174/#/investment/journal');
    command('wait', '--fn', "document.querySelector('#app')?.children.length > 0");
    command('screenshot', join(evidence, 'login-before-health.png'));
    assert(evaluate("!!document.querySelector('input[name=adminToken]')"), 'Display the sign-in form without waiting for a slow health probe.');
    assert.equal(evaluate("performance.getEntriesByType('resource').some(item=>item.name.includes('/pages/Journal.jsx'))"), false, 'Do not load Journal and other workspace-only modules before sign-in.');
    checks.push('Sign-in visible before health; workspace pages deferred');
  }
  if (stage !== 'startup') {
    command('open', 'http://localhost:5174/#/investment/journal');
    command('wait', '--load', 'networkidle');
    command('wait', '--fn', "!!document.querySelector('input[name=adminToken]') || !!document.querySelector('.app-shell')");
    if (evaluate("!!document.querySelector('input[name=adminToken]')")) {
      command('fill', 'input[name=adminToken]', 'synthetic-browser-admin'); command('click', 'button[type=submit]');
    }
    settled(); command('select', '.workspace-tools select', fixture.workspaceId); settled();
    let workspaceId = fixture.workspaceId;
    const request = path => evaluate(`fetch('/api/v3/workspaces/'+${JSON.stringify(workspaceId)}+${JSON.stringify(path)}).then(response=>response.json()).then(payload=>payload.data)`);
    if (['focus', 'all'].includes(stage)) {
      navigate('#/investment/journal');
      evaluate("[...document.querySelectorAll('.posting .field')].find(field=>['Memo','Note'].includes(field.querySelector('label')?.textContent)).querySelector('input').focus()");
      command('screenshot', join(evidence, 'journal-focused.png'), '--full');
      const focus = evaluate(`(()=>{
        const input=document.activeElement, style=getComputedStyle(input), rect=input.getBoundingClientRect();
        const margin=Math.max(0,parseFloat(style.outlineWidth)+parseFloat(style.outlineOffset));
        let clipped=false;
        for(let parent=input.parentElement;parent;parent=parent.parentElement){
          const css=getComputedStyle(parent), box=parent.getBoundingClientRect();
          if(['clip','hidden'].includes(css.overflowX) && (rect.left-margin<box.left-1 || rect.right+margin>box.right+1)) clipped=true;
          if(['clip','hidden'].includes(css.overflowY) && (rect.top-margin<box.top-1 || rect.bottom+margin>box.bottom+1)) clipped=true;
        }
        return {width:parseFloat(style.outlineWidth),clipped};
      })()`);
      assert(focus.width >= 2 && !focus.clipped, 'The complete visible focus perimeter must fit inside clipping ancestors.');
      assert.equal(evaluate("[...document.querySelectorAll('#journal-editor label')].filter(label=>label.textContent.startsWith('Tags')).length"), 1, 'Do not render duplicate Tags fields.');
      checks.push('Journal complete focus ring and one Tags field');
    }
    if (['plans', 'all'].includes(stage)) {
      navigate('#/living/plans');
      assert(evaluate("!!document.querySelector('textarea[name=note]') && !document.querySelector('textarea[name=note]').required"), 'Monthly plans have an optional Note.');
      const name = 'Synthetic plan ' + Date.now(), note = 'Planning context <script>not executable</script>\nNo actual income is implied.';
      command('fill', 'input[name=name]', name); command('fill', 'input[name=amount]', '123.45');
      command('fill', 'textarea[name=note]', note); command('find', 'role', 'button', 'click', '--name', 'Add plan', '--exact'); settled();
      assert.equal(request('/monthly-plans').find(item=>item.name===name).note, note);
      checks.push('Monthly plan optional Note persists as inert context');
    }
    if (['balances', 'all'].includes(stage)) {
      navigate('#/living/balances');
      assert(evaluate("!!document.querySelector('.recorded-balance-form textarea[name=note]') && !document.querySelector('textarea[name=note]').required"), 'Accounts & balances has an optional Note.');
      const note = 'Synthetic observed balance context <b>plain text</b>\nNot income or spending.';
      command('fill', '.recorded-balance-form input[name=amount]', '125');
      command('fill', '.recorded-balance-form input[name=source]', 'Synthetic browser observation');
      command('fill', '.recorded-balance-form textarea[name=note]', note);
      command('check', '.recorded-balance-form input[type=checkbox]');
      command('find', 'role', 'button', 'click', '--name', 'Record balance', '--exact'); settled();
      assert(request('/balance-records').some(record=>record.note===note && record.amount==='125'));
      command('click', '.snapshot-history > summary');
      command('click', '.snapshot-metadata > summary');
      assert(evaluate(`document.querySelector('.snapshot-history').textContent.includes(${JSON.stringify(note)})`));
      command('screenshot', join(evidence, 'balance-note-history.png'), '--full');
      checks.push('Actual-date balance Note persists and remains folded in history');
      navigate('#/master/accounts');
      assert(evaluate("!!document.querySelector('.resource-form textarea[name=note]') && !document.querySelector('textarea[name=note]').required"), 'Registered accounts have an optional Note.');
    }
    if (['opening', 'all'].includes(stage)) {
      navigate('#/master');
      assert(evaluate("[...document.querySelectorAll('.subnav button')].some(button=>button.textContent==='Opening balances')"), 'Master data provides a dedicated Opening balances entry.');
      const suffix = Date.now(), cashId = 'opening-browser-cash-' + suffix, equityId = 'opening-browser-equity-' + suffix;
      workspaceId = evaluate(`fetch('/api/v3/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({displayName:'Synthetic opening '+${suffix},kind:'sandbox'})}).then(response=>response.json()).then(result=>result.data.id)`);
      assert.equal(evaluate(`fetch('/api/v3/workspaces/'+${JSON.stringify(workspaceId)}+'/commodities',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:'CNY',name:'Synthetic currency',kind:'currency',scale:2})}).then(response=>response.status)`), 201);
      const addAccount = (identity, type) => evaluate(`fetch('/api/v3/workspaces/'+${JSON.stringify(workspaceId)}+'/financial-accounts',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:${JSON.stringify(identity)},code:${JSON.stringify(type==='asset'?'O1001':'O3001')},name:'Synthetic opening '+${JSON.stringify(type)},type:${JSON.stringify(type)},subtype:${JSON.stringify(type==='asset'?'cash':'')},allowedCommodityCodes:['CNY'],segment:'investment',balanceSource:'ledger'})}).then(response=>response.status)`);
      assert.equal(addAccount(cashId, 'asset'), 201); assert.equal(addAccount(equityId, 'equity'), 201);
      command('open', 'http://localhost:5174/#/master'); command('reload'); command('wait', '--load', 'networkidle'); settled();
      command('select', '.workspace-tools select', workspaceId); settled(); navigate('#/master');
      command('find', 'role', 'button', 'click', '--name', 'Opening balances', '--exact'); settled();
      command('select', '.opening-form select[name=equityAccountId]', equityId);
      command('select', '.opening-form select[name=accountId]', cashId);
      evaluate("(()=>{const node=document.querySelector('.opening-form input[name=date]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(node,'2026-08-01');node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));})()");
      command('fill', '.opening-form input[name=source]', 'Synthetic opening statement');
      command('fill', '.opening-form input[name=amount]', '100');
      command('fill', '.opening-form textarea[name=note]', 'Synthetic opening stock, not period income.');
      command('screenshot', join(evidence, 'opening-before-save.png'), '--full');
      command('find', 'role', 'button', 'click', '--name', 'Save opening draft', '--exact'); settled();
      assert(evaluate("!!document.querySelector('.opening-preview')"));
      assert.equal(evaluate("document.querySelector('.opening-preview button[type=submit]')?.disabled"), true, 'Posting requires validation and a separate human confirmation.');
      command('find', 'role', 'button', 'click', '--name', 'Validate opening draft', '--exact'); settled();
      command('check', '.opening-preview input[type=checkbox]');
      command('find', 'role', 'button', 'click', '--name', 'Post opening balances', '--exact'); settled();
      const opening = request('/opening-balances').entries.find(entry=>entry.postings.some(posting=>posting.accountId===cashId));
      assert(opening && opening.date==='2026-08-01');
      assert.equal(request('/reports/activity-cash-flow?month=2026-08').openingEffects.find(row=>row.commodityCode==='CNY').amount, '100');
      assert.equal(opening.postings.find(row=>row.accountId===cashId).memo, 'Synthetic opening stock, not period income.');
      for (const width of [1024, 1440, 1920]) {
        command('set', 'viewport', String(width), '1000');
        assert(evaluate('document.documentElement.scrollWidth<=innerWidth+1'));
        command('screenshot', join(evidence, 'opening-' + width + '.png'), '--full');
      }
      navigate('#/investment/cashflow/2026-08');
      assert(evaluate("!!document.querySelector('.opening-effects') && document.querySelector('input[type=month]').value==='2026-08'"), 'Cash flow has an explicit period and separates opening effects from activity.');
      navigate('#/investment/legacyreview/2026-08');
      assert(evaluate("document.querySelector('.monthly-review').textContent.includes('opening stock and linked opening reversals are excluded')"));
      evaluate("(()=>{const node=document.querySelector('.monthly-review input[type=month]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(node,'2026-09');node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));})()");
      command('find', 'role', 'button', 'click', '--name', 'Review month', '--exact'); settled();
      assert.equal(evaluate('location.hash'), '#/investment/legacyreview/2026-09', 'Changing the activity month retains this report rather than opening a different review.');
      const owner = 'opening-browser-owner-' + suffix, livingId = 'opening-browser-living-' + suffix;
      assert.equal(evaluate(`fetch('/api/v3/workspaces/'+${JSON.stringify(workspaceId)}+'/finance-parties/'+${JSON.stringify(owner)}, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:${JSON.stringify(owner)},name:'Synthetic opening owner'})}).then(response=>response.status)`), 200);
      assert.equal(evaluate(`fetch('/api/v3/workspaces/'+${JSON.stringify(workspaceId)}+'/financial-accounts', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:${JSON.stringify(livingId)},code:'L1001',name:'Synthetic opening wallet',type:'asset',subtype:'cash',allowedCommodityCodes:['CNY'],segment:'living',balanceSource:'monthly_snapshot',ownerPartyId:${JSON.stringify(owner)}})}).then(response=>response.status)`), 201);
      const journalBefore = request('/journal-entries');
      navigate('#/master/opening'); command('click', '.opening-balances .subnav button:nth-child(2)');
      command('fill', '.recorded-balance-form input[name=amount]', '0');
      command('fill', '.recorded-balance-form input[name=source]', 'Synthetic dated opening source');
      command('fill', '.recorded-balance-form textarea[name=note]', 'An observed zero, not a month-end estimate.');
      command('check', '.recorded-balance-form input[type=checkbox]');
      command('find', 'role', 'button', 'click', '--name', 'Record opening balance', '--exact'); settled();
      assert.deepEqual(request('/journal-entries'), journalBefore, 'Living opening never creates a Journal entry.');
      assert(request('/balance-records').some(record=>record.subjectId===livingId && record.amount==='0' && record.note==='An observed zero, not a month-end estimate.'));
      evaluate('document.activeElement?.blur();scrollTo(0,0)');
      command('screenshot', join(evidence, 'living-opening.png'), '--full');
      checks.push('Dedicated opening draft → validation → confirmed posting; stock not activity');
    }
  }
  writeFileSync(join(evidence, 'result.json'), JSON.stringify({ syntheticOnly: true, status: 'pass', checks }, null, 2));
  console.log(`PASS: ${checks.length} opening / notes / startup scenario groups.`);
} catch (error) {
  writeFileSync(join(evidence, 'result.json'), JSON.stringify({ syntheticOnly: true, status: 'failed', checks, error: String(error) }, null, 2));
  throw error;
} finally {
  evaluate("fetch('/api/__test_health_gate?hold=false').then(response=>response.json())");
}
