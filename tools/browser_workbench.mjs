// Public UI and Workspace HTTP checks only; never attach to a user's browser or Vault.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';

const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + sep));
const fixture = JSON.parse(readFileSync(join(run, 'fixture.json'), 'utf8'));
assert.equal(fixture.syntheticOnly, true);
assert.equal(fixture.api, 'http://127.0.0.1:8791');
assert.equal(fixture.ui, 'http://localhost:5174');
assert(process.env.FC_AGENT_BROWSER && process.env.AGENT_BROWSER_SESSION && process.env.AGENT_BROWSER_NAMESPACE);
const stage = process.argv[2] || 'assets';
assert(['assets-before', 'assets', 'overview', 'plans', 'builders', 'layout', 'comparison', 'all'].includes(stage));
const evidence = join(run, `workbench-${stage}-${Date.now()}`);
mkdirSync(evidence);
const checks = [];
const command = (...args) => {
  const result = JSON.parse(execFileSync(process.env.FC_AGENT_BROWSER, ['--json', ...args], { encoding: 'utf8', timeout: 45000 }));
  assert.equal(result.success, true, result.error || 'Browser operation failed');
  return result.data;
};
const evaluate = source => command('eval', source).result;
const wait = condition => command('wait', '--fn', condition);
const settled = () => wait("!!document.querySelector('.app-shell') && !document.querySelector('.loading-line') && !document.querySelector('[aria-busy=true]')");
const navigate = (path, heading) => {
  evaluate(`location.hash=${JSON.stringify(path)}`);
  wait(`document.querySelector('main h1')?.textContent===${JSON.stringify(heading)} || (location.hash==='#/overview' && !!document.querySelector('.financial-overview'))`);
  settled();
};
const request = (path, options = {}) => evaluate(`fetch('/api/v3/workspaces/'+${JSON.stringify(fixture.workspaceId)}+${JSON.stringify(path)},${JSON.stringify(options)}).then(async response=>({status:response.status,payload:await response.json()}))`);
const records = path => { const result = request(path); assert.equal(result.status, 200); return result.payload.data; };
const click = name => command('find', 'role', 'button', 'click', '--name', name, '--exact');
const acceptConfirmation = async () => {
  for (let attempt = 0; attempt < 20; attempt++) {
    if (command('dialog', 'status').hasDialog) { command('dialog', 'accept'); return; }
    await new Promise(resolve => setTimeout(resolve, 30));
  }
  throw new Error('The destructive/create action did not request confirmation.');
};
const choose = (selector, label) => {
  evaluate(`(()=>{document.querySelectorAll('[data-test-select]').forEach(el=>el.removeAttribute('data-test-select'));document.querySelector(${JSON.stringify(selector)}).setAttribute('data-test-select','true');})()`);
  command('click', selector);
  wait("!!document.querySelector('[role=listbox]')");
  const index = evaluate(`[...document.querySelectorAll('[role=listbox] [role=option]')].findIndex(option=>option.querySelector('span')?.textContent===${JSON.stringify(label)})`);
  assert(index >= 0, 'Visible option: ' + label);
  command('press', 'Home');
  for (let i = 0; i < index; i++) command('press', 'ArrowDown');
  command('press', 'Enter');
  wait(`document.querySelector('[data-test-select]')?.textContent.trim()===${JSON.stringify(label)}`);
  evaluate("document.querySelector('[data-test-select]').removeAttribute('data-test-select')");
};
const tagRow = text => evaluate(`(()=>{document.querySelectorAll('[data-test-row]').forEach(row=>row.removeAttribute('data-test-row'));const row=[...document.querySelectorAll('tbody tr')].find(row=>row.textContent.includes(${JSON.stringify(text)}));if(row)row.setAttribute('data-test-row','true');return !!row;})()`);
// Windows' localized date control does not reliably accept the CLI's text fill.
const date = (selector, value) => evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));return input.value;})()`);
const capture = name => {
  evaluate('window.scrollTo(0,0);document.activeElement?.blur()');
  wait("[...document.querySelectorAll('.step-content')].every(outer=>Math.abs(outer.getBoundingClientRect().height-outer.firstElementChild.getBoundingClientRect().height)<2)");
  command('screenshot', join(evidence, name), '--full');
};

try {
  command('open', fixture.ui + '/__synthetic_marker');
  assert.equal(evaluate('document.body.textContent'), 'fc-ui-workbench-synthetic-only');
  command('set', 'viewport', '1440', '1000');
  command('open', fixture.ui + '/#/living/assets');
  wait("!!document.querySelector('input[name=adminToken]') || !!document.querySelector('.app-shell')");
  if (evaluate("!!document.querySelector('input[name=adminToken]')")) {
    command('fill', 'input[name=adminToken]', 'synthetic-workbench-admin'); click('Enter Finance Core');
  }
  settled();
  if (evaluate("document.querySelector('.workspace-tools select').value") !== fixture.workspaceId) command('select', '.workspace-tools select', fixture.workspaceId);
  settled();
  navigate('#/living/assets', 'Assets & liabilities');
  if (stage === 'assets-before') {
    for (const [name, value] of Object.entries({ name: 'Synthetic bicycle', assetType: 'Bicycle', purchaseCost: '120', note: 'Synthetic registry note\nStored context is not a valuation.' })) command('fill', `.resource-form [name=${name}]`, value);
    assert.equal(date('.resource-form [name=purchasedDate]', '2026-01-03'), '2026-01-03');
    click('Register asset'); settled();
    assert(records('/non-financial-assets').some(item => item.name === 'Synthetic bicycle' && item.note.includes('Synthetic registry note')));
    command('screenshot', join(evidence, 'assets-before.png'), '--full');
    assert(evaluate("document.querySelector('main').textContent.includes('Synthetic registry note')"), 'A saved registry Note must remain visible outside the cleared registration form.');
  }
  if (['assets', 'all'].includes(stage)) {
    if (!records('/non-financial-assets').some(item => item.name === 'Synthetic bicycle')) {
      for (const [name, value] of Object.entries({ name: 'Synthetic bicycle', assetType: 'Bicycle', purchaseCost: '120', note: 'Synthetic registry note\nStored context is not a valuation.' })) command('fill', `.resource-form [name=${name}]`, value);
      date('.resource-form [name=purchasedDate]', '2026-01-03');
      click('Register asset'); settled();
    }
    const asset = records('/non-financial-assets').find(item => item.name === 'Synthetic bicycle');
    assert(asset?.note.includes('Synthetic registry note'));
    assert(evaluate("document.querySelector('.asset-card .saved-note').textContent.includes('Synthetic registry note')"));
    assert(evaluate("document.querySelector('main').textContent.includes('Valuation month (value at month end)')"));
    const month = evaluate("[...document.querySelectorAll('input[type=month]')][0].value");
    const entries = records('/journal-entries');
    const observations = () => records('/monthly-observations').filter(item => item.subjectId === asset.id && item.month === month);
    if (!asset.disposedMonth) {
      command('fill', '.asset-card input[name=amount]', '-1');
      command('fill', '.asset-card input[name=source]', 'Synthetic market estimate');
      command('fill', '.asset-card textarea[name=note]', 'Synthetic valuation note');
      if (evaluate("!!document.querySelector('.asset-card input[name=reason]')")) command('fill', '.asset-card input[name=reason]', 'Synthetic repeat correction');
      command('check', '.asset-card input[type=checkbox]'); click('Save valuation'); settled();
      assert(evaluate("!!document.querySelector('.asset-card [role=alert]')"), 'Show a rejected valuation next to the form, not only at the page top.');
      command('fill', '.asset-card input[name=amount]', '90');
      assert(evaluate("document.querySelector('.asset-card input[type=checkbox]').checked===false"), 'Changing the valuation requires renewed confirmation.');
      command('check', '.asset-card input[type=checkbox]'); click('Save valuation'); settled();
      assert(observations().some(item => item.amount === '90' && item.note === 'Synthetic valuation note'));
      assert(evaluate("document.querySelector('.asset-card .record-details').textContent.includes('Synthetic valuation note')"));
      command('fill', '.asset-card input[name=amount]', '90.01');
      command('fill', '.asset-card input[name=reason]', 'Synthetic corrected estimate');
      command('check', '.asset-card input[type=checkbox]'); click('Save valuation'); settled();
      assert(observations().some(item => item.amount === '90.01' && item.supersedes && item.reason === 'Synthetic corrected estimate'));
      assert(observations().some(item => item.amount === '90'), 'Corrections retain the original valuation.');
      command('screenshot', join(evidence, 'asset-saved-valuation.png'), '--full');
      click('Record disposal'); wait("!!document.querySelector('dialog[open]')");
      click('Save disposal'); settled(); wait("!document.querySelector('dialog[open]')");
      assert.equal(records('/non-financial-assets').find(item => item.id === asset.id).disposedMonth, month);
      assert(evaluate("document.querySelector('.asset-card').textContent.includes('Disposal recorded:')"));
    }
    assert.deepEqual(records('/journal-entries'), entries, 'Asset valuation/disposal must not silently create a Journal entry.');
    navigate('#/overview', ''); navigate('#/living/assets', 'Assets & liabilities');
    assert(evaluate("document.querySelector('.asset-card .saved-note').textContent.includes('Synthetic registry note')"));
    assert(evaluate("document.querySelector('.asset-card .record-details').textContent.includes('Synthetic valuation note')"));
    command('screenshot', join(evidence, 'assets-after.png'), '--full');
    checks.push('Asset Note survives reload; valuation success/error/correction and disposal persist through scoped HTTP without Journal writes');
  }
  if (['overview', 'all'].includes(stage)) {
    navigate('#/living/balances', 'Accounts & balances');
    if (!records('/balance-records').some(item => item.note === 'Synthetic workbench balance context')) {
      date('.recorded-balance-form input[name=observedDate]', '2026-10-15');
      command('fill', '.recorded-balance-form input[name=amount]', '0.43');
      command('fill', '.recorded-balance-form input[name=source]', 'Synthetic browser statement');
      command('fill', '.recorded-balance-form textarea[name=note]', 'Synthetic workbench balance context');
      command('check', '.recorded-balance-form input[type=checkbox]'); click('Record balance'); settled();
    }
    const balance = records('/reports/living-recorded-balances?month=2026-10').accounts.find(item => item.accountId === 'L1');
    assert.equal(balance.observedDate, '2026-10-15'); assert.equal(balance.amount, '0.43');
    assert.equal(balance.previousAmount, '0.3'); assert.equal(balance.change, '0.13');
    navigate('#/overview', '');
    assert(!evaluate("document.querySelector('.financial-overview').textContent.includes('OPENING_BASELINE_UNCONFIRMED')"));
    command('click', '.coverage-summary button'); wait("!!document.querySelector('dialog[open]')");
    assert(evaluate("document.querySelector('dialog').textContent.includes('Opening baseline not confirmed')"));
    choose('dialog .list-controls .select-custom button', 'Check');
    command('fill', 'dialog input[type=search]', 'opening');
    assert(evaluate("document.querySelectorAll('dialog tbody tr').length>0"));
    command('screenshot', join(evidence, 'overview-checks-dialog.png'));
    command('focus', 'dialog .dialog-heading button'); command('press', 'Escape'); wait("!document.querySelector('dialog[open]')");
    assert(evaluate("document.activeElement===document.querySelector('.coverage-summary button')"), 'Closing the dialog restores focus to its trigger.');
    assert(tagRow('L1 ·')); command('click', '[data-test-row] button');
    wait("!!document.querySelector('dialog[open]')");
    assert(evaluate("document.querySelector('dialog').textContent.includes('0.13') && document.querySelector('dialog').textContent.includes('2026-10-10')"));
    command('press', 'Escape'); wait("!document.querySelector('dialog[open]')");
    command('screenshot', join(evidence, 'overview-after.png'), '--full');
    navigate('#/investment/taccounts', 'T-accounts');
    assert.equal(evaluate("document.querySelectorAll('.t-account-card').length"), 2);
    assert.deepEqual(evaluate("[...document.querySelector('.t-account-card thead tr').cells].map(cell=>cell.textContent)"), ['Currency', 'Credit', 'Debit', 'Normal balance', 'Posting count']);
    command('click', '.list-controls .sort-direction');
    assert(evaluate("document.querySelector('.t-account-card h3').textContent.startsWith('3001')"));
    command('fill', '.list-controls input[type=search]', '1001');
    assert.equal(evaluate("document.querySelectorAll('.t-account-card').length"), 1);
    command('screenshot', join(evidence, 't-accounts-after.png'), '--full');
    navigate('#/investment/positions', 'Securities & positions');
    assert(evaluate("!!document.querySelector('.integration-placeholder') && !document.querySelector('main table')"));
    checks.push('Actual-date balance write/read/change are exact; Overview detail dialogs, focus restoration, T-account ordering and securities placeholder work');
  }
  if (['plans', 'all'].includes(stage)) {
    navigate('#/living/plans', 'Monthly plans');
    const expected = records('/reports/monthly-plans?month=2026-10');
    assert.deepEqual(expected.categories.find(item => item.category === 'Work' && item.currency === 'CNY'), { category: 'Work', currency: 'CNY', inflow: '0.3', outflow: '0', net: '0.3', count: 2 });
    assert.equal(expected.occurrences.find(item => item.planId === 'salary').dueDate, '2026-10-13');
    const name = 'Synthetic browser plan ' + Date.now();
    command('fill', '.monthly-plan-form input[name=name]', name);
    command('fill', '.monthly-plan-form input[name=amount]', '0.11');
    choose('.monthly-plan-form .select-field:has(select[name=kind]) .select-custom button', 'CF inflow');
    choose('.monthly-plan-form .select-field:has(select:not([name])) .select-custom button', 'Work');
    command('fill', '.monthly-plan-form input[name=dayOfMonth]', '13');
    date('.monthly-plan-form input[name=startDate]', '2026-01-01');
    command('fill', '.monthly-plan-form textarea[name=note]', 'Synthetic optional plan context');
    click('Add plan'); settled();
    const created = records('/monthly-plans').find(item => item.name === name);
    assert(created && created.category === 'Work' && created.dayOfMonth === 13 && created.note === 'Synthetic optional plan context');
    assert.equal(records('/reports/monthly-plans?month=2026-10').categories.find(item => item.category === 'Work' && item.currency === 'CNY').inflow, '0.41');
    assert(tagRow(name)); command('click', '[data-test-row] button:first-child');
    wait("document.querySelector('.monthly-plan-form button[type=submit]')?.textContent==='Save plan'");
    command('fill', '.monthly-plan-form input[name=amount]', '0.12'); click('Save plan'); settled();
    assert.equal(records('/monthly-plans').find(item => item.id === created.id).amount, '0.12');
    choose('.plan-filters .select-field:first-child .select-custom button', 'Work');
    assert(!evaluate("[...document.querySelectorAll('caption')].find(item=>item.textContent==='Monthly plans').closest('table').textContent.includes('Synthetic rent')"));
    const controls = "[aria-label='Monthly plans filters']";
    choose(`${controls} .select-custom button`, 'Planned amount');
    command('click', `${controls} .sort-direction`);
    command('fill', `${controls} input[type=search]`, name);
    assert.equal(evaluate("[...document.querySelectorAll('caption')].find(item=>item.textContent==='Monthly plans').closest('table').querySelectorAll('tbody tr').length"), 1);
    command('screenshot', join(evidence, 'monthly-plans-after.png'), '--full');
    assert(tagRow(name)); command('click', '[data-test-row] button:last-child'); await acceptConfirmation(); settled();
    assert(!records('/monthly-plans').some(item => item.id === created.id));
    assert.equal(records('/reports/monthly-plans?month=2026-10').categories.find(item => item.category === 'Work' && item.currency === 'CNY').inflow, '0.3');
    checks.push('Plan create/edit/delete, reused category glide select, day 13, category/search/direction filters and exact separate-currency backend totals work');
  }
  if (['builders', 'all'].includes(stage)) {
    navigate('#/master/ownership', 'Master data');
    if (!records('/investment-arrangements').some(item => item.currency === 'CNY')) {
      click('New agreement'); wait("!!document.querySelector('.agreement-editor')");
      assert.equal(evaluate("document.querySelectorAll('.agreement-editor textarea').length"), 1, 'Only a human-readable reason is entered, not a JSON contract.');
      const parties = ['Synthetic owner', 'Synthetic investor-a', 'Synthetic investor-b'];
      click('Add beneficiary share'); click('Add beneficiary share');
      for (const [index, share] of ['0.5', '0.3', '0.3'].entries()) {
        choose(`.agreement-editor > fieldset > .builder-row:nth-of-type(${index + 1}) .select-custom button`, parties[index]);
        command('fill', `.agreement-editor > fieldset > .builder-row:nth-of-type(${index + 1}) input`, share);
      }
      command('fill', '.agreement-editor textarea', 'Synthetic generic ownership configuration');
      click('Validate and append agreement'); settled();
      assert(evaluate("!!document.querySelector('.global-notice.error') && !!document.querySelector('.agreement-editor')"), 'Invalid shares remain editable and are rejected by FC.');
      command('fill', '.agreement-editor > fieldset > .builder-row:nth-of-type(3) input', '0.2');
      click('Validate and append agreement'); settled();
      assert(!evaluate("!!document.querySelector('.agreement-editor')"));
      assert.deepEqual(records('/investment-arrangements').find(item => item.currency === 'CNY').residualShares, [{ partyId: 'owner', share: '0.5' }, { partyId: 'investor-a', share: '0.3' }, { partyId: 'investor-b', share: '0.2' }]);
    }
    const agreement = records('/investment-arrangements').find(item => item.currency === 'CNY');
    const rejected = request('/investment-arrangements', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...agreement, version: agreement.version + 1, fromMonth: '2026-10', residualShares: [{ partyId: 'owner', share: '0.6' }, { partyId: 'investor-a', share: '0.3' }, { partyId: 'investor-b', share: '0.2' }] }) });
    assert.equal(rejected.status, 422, 'Shares totalling 1.1 are rejected without creating a new version.');
    command('screenshot', join(evidence, 'structured-agreements.png'), '--full');
    navigate('#/investment/data/batch', 'Import & export');
    assert(!evaluate("!!document.querySelector('main textarea')"), 'Atomic batch entry must not require JSON.');
    const code = 'SYN' + Date.now();
    command('fill', '.resource-form input[name=code]', code);
    command('fill', '.resource-form input[name=name]', 'Synthetic batch-created unit'); click('Stage new record');
    choose('.panel > .select-field .select-custom button', 'New Investment account');
    command('fill', '.resource-form input[name=code]', 'B' + code);
    command('fill', '.resource-form input[name=name]', 'Synthetic batch account ' + code); click('Stage new record');
    choose('.panel > .select-field .select-custom button', 'New explicit price');
    choose('.resource-form .select-field:has(select[name=quoteCommodityCode]) .select-custom button', 'USD');
    command('fill', '.resource-form input[name=price]', '0.5');
    date('.resource-form input[name=asOf]', '2026-09-20T12:00'); click('Stage new record');
    choose('.panel > .select-field .select-custom button', 'New draft from a saved template');
    command('fill', '.resource-form input[name=description]', 'Synthetic batch clone ' + code);
    date('.resource-form input[name=date]', '2026-09-21'); click('Stage new record');
    const entriesBeforeBatch = records('/journal-entries');
    wait("[...document.querySelectorAll('main button')].some(button=>button.textContent==='Validate and create batch'&&!button.disabled) && [...document.querySelectorAll('.step-content')].every(outer=>Math.abs(outer.getBoundingClientRect().height-outer.firstElementChild.getBoundingClientRect().height)<2)");
    click('Validate and create batch'); await acceptConfirmation(); settled();
    assert.equal(records('/commodities').find(item => item.code === code)?.name, 'Synthetic batch-created unit');
    assert(records('/financial-accounts').some(item => item.code === 'B' + code && item.segment === 'investment'));
    assert(records('/price-quotes').some(item => item.price === '0.5' && item.quoteCommodityCode === 'USD'));
    const cloned = records('/journal-entry-drafts').find(item => item.draft.description === 'Synthetic batch clone ' + code)?.draft;
    assert(cloned && cloned.date === '2026-09-21' && cloned.postings.every(item => item.id.startsWith(cloned.id)));
    assert.deepEqual(records('/journal-entries'), entriesBeforeBatch, 'Batch drafts stay unposted.');
    navigate('#/investment/data/recurring', 'Import & export');
    command('fill', '.resource-form input[name=name]', 'Synthetic disposable rule');
    command('fill', '.resource-form input[name=dayOfMonth]', '13');
    date('.resource-form input[name=startDate]', '2026-01-01'); click('Save template'); settled();
    const rule = records('/recurring-entry-rules').find(item => item.name === 'Synthetic disposable rule');
    assert(rule); assert(tagRow('Synthetic disposable rule'));
    command('click', '[data-test-row] button:last-child'); await acceptConfirmation(); settled();
    assert(!records('/recurring-entry-rules').some(item => item.id === rule.id));
    checks.push('Structured beneficiary agreement rejects invalid shares and saves a generic three-party example; atomic batch and recurring-rule safe deletion work without JSON entry');
  }
  if (['layout', 'all'].includes(stage)) {
    navigate('#/master/accounts', 'Master data');
    choose('.resource-form .select-field:has(select[name=segment]) .select-custom button', 'Living');
    const codes = () => evaluate("[...document.querySelectorAll('.account-filters + .record-list tbody tr')].map(row=>row.cells[0].textContent)");
    assert.deepEqual(codes(), ['L1', 'L2', 'L10']);
    command('click', "[aria-label='Account order filters'] .sort-direction");
    assert.deepEqual(codes(), ['L10', 'L2', 'L1']);
    command('fill', 'input[name=accountSearch]', 'wallet L2'); assert.deepEqual(codes(), ['L2']);
    click('Clear filters'); assert.deepEqual(codes(), ['L1', 'L2', 'L10']);
    choose('.resource-form .select-field:has(select[name=segment]) .select-custom button', 'Investment');
    assert(!codes().some(code => code.startsWith('L')), 'Investment must never show Living accounts.');
    evaluate('window.scrollTo(0,250)'); const scroll = evaluate('scrollY');
    command('click', '.subnav button:first-child'); settled();
    assert(Math.abs(evaluate('scrollY') - scroll) < 3, 'Master data tabs should not reset page scroll.');
    navigate('#/investment/journal', 'Journal');
    evaluate("[...document.querySelectorAll('.posting .field')].find(field=>field.querySelector('label')?.textContent==='Note').querySelector('input').focus()");
    assert(evaluate(`(()=>{const el=document.activeElement,style=getComputedStyle(el),rect=el.getBoundingClientRect(),extra=Math.max(0,parseFloat(style.outlineWidth)+parseFloat(style.outlineOffset));for(let p=el.parentElement;p;p=p.parentElement){const css=getComputedStyle(p),r=p.getBoundingClientRect();if(['clip','hidden'].includes(css.overflowX)&&(rect.left-extra<r.left-1||rect.right+extra>r.right+1))return false;}return parseFloat(style.outlineWidth)>=2;})()`));
    const layouts = [['#/overview', '', 'overview'], ['#/living/plans', 'Monthly plans', 'monthly-plans'], ['#/living/assets', 'Assets & liabilities', 'assets']];
    for (const [route, heading, label] of layouts) {
      navigate(route, heading);
      for (const width of [1440, 1100, 390]) {
        command('set', 'viewport', String(width), '1000');
        assert(evaluate('document.documentElement.scrollWidth<=innerWidth+1'), `No page-level horizontal overflow: ${label} ${width}`);
        capture(`${label}-${width}.png`);
      }
      command('set', 'viewport', '1440', '1000');
    }
    navigate('#/overview', ''); command('click', '.coverage-summary button'); wait("!!document.querySelector('dialog[open]')");
    assert(evaluate("document.querySelector('dialog .table-wrap').scrollWidth<=document.querySelector('dialog .table-wrap').clientWidth+1"), 'Narrative report checks wrap inside the dialog.');
    command('screenshot', join(evidence, 'checks-readable.png')); click('Close Month-end data checks');
    checks.push('Account filters and sort reset together without segment leakage; tabs preserve scroll; Journal focus is unclipped; 1440/1100 desktop and 390 narrow layouts have no page overflow');
  }
  if (['comparison', 'all'].includes(stage)) {
    if (!records('/personal-finance-settings')) {
      assert.equal(request('/personal-finance-settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cutoverMonth: '2026-09', reportingPartyId: 'owner', baselineConfirmed: false, baselineEvidence: 'Synthetic incomplete-input demonstration only' }) }).status, 200);
    }
    const report = records('/reports/personal-balance-sheet?month=2026-09');
    assert.equal(report.currencies.find(item => item.currency === 'CNY').ownerships.find(item => item.partyId === 'owner').economicValue, '3.5');
    assert(report.issues.some(item => item.code === 'CLOSING_BALANCE_MISSING'), 'Later actual-date records must not silently fill earlier month-end balances.');
    for (const baseline of [true, false]) {
      // The owned dev helper transforms HEAD sources in memory, never edits the worktree.
      const mode = await fetch(fixture.ui + '/__synthetic_baseline?enabled=' + baseline).then(response => response.json());
      assert.equal(mode.syntheticOnly, true); assert.equal(mode.baseline, baseline);
      for (const [route, heading, label] of [['#/overview', '', 'overview'], ['#/living/assets', 'Assets & liabilities', 'assets']]) {
        command('open', fixture.ui + '/' + route); settled();
        if (heading) wait(`document.querySelector('main h1')?.textContent===${JSON.stringify(heading)}`);
        capture(`${label}-${baseline ? 'before' : 'after'}.png`);
      }
    }
    checks.push('Before/after screenshots compare identical synthetic data against HEAD and current UI; backend three-party ownership is exact and missing month-end inputs stay unknown');
  }
  writeFileSync(join(evidence, 'result.json'), JSON.stringify({ passed: true, syntheticOnly: true, checks }, null, 2));
  console.log(JSON.stringify({ passed: true, checks, evidence }));
} catch (error) {
  if (['comparison', 'all'].includes(stage)) await fetch(fixture.ui + '/__synthetic_baseline?enabled=false').catch(() => {});
  writeFileSync(join(evidence, 'result.json'), JSON.stringify({ passed: false, syntheticOnly: true, checks, error: error.message }, null, 2));
  throw error;
}
