// Actual rendered UI and Workspace API only; never use a real Vault/browser profile.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';

const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + sep));
const fixture = JSON.parse(readFileSync(join(run, 'fixture.json'), 'utf8'));
assert.equal(fixture.syntheticOnly, true);
assert(process.env.FC_AGENT_BROWSER && process.env.AGENT_BROWSER_SESSION && process.env.AGENT_BROWSER_NAMESPACE);
const evidence = join(run, 'recorded-ui');
mkdirSync(evidence, { recursive: true });
const command = (...args) => {
  const result = JSON.parse(execFileSync(process.env.FC_AGENT_BROWSER, ['--json', ...args], { encoding: 'utf8', timeout: 40000 }));
  assert.equal(result.success, true, result.error || 'Browser command failed');
  return result.data;
};
const evaluate = expression => command('eval', expression).result;
const settled = () => command('wait', '--fn', "!!document.querySelector('.app-shell') && !document.querySelector('.loading-line') && !document.querySelector('[aria-busy=true]')");
const navigate = path => { evaluate(`location.hash=${JSON.stringify(path)}`); settled(); };
const api = path => evaluate(`(async()=>{const response=await fetch('/api/v3/workspaces/'+${JSON.stringify(fixture.workspaceId)}+${JSON.stringify(path)});if(!response.ok)throw Error('Synthetic read failed: '+response.status);return (await response.json()).data;})()`);
const rows = caption => evaluate(`[...document.querySelector(${JSON.stringify(`[aria-label="${caption}"]`)}).querySelectorAll('tbody tr')].map(row=>[...row.cells].map(cell=>cell.textContent.trim()))`);
const checks = [];
const code = 'DATE' + Date.now(), wallet = 'ui-' + code, walletName = code + ' synthetic wallet';
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
  settled(); evaluate('window.confirm=()=>true');
  command('select', '.workspace-tools select', fixture.workspaceId); settled();
  evaluate(`(async()=>{
    const prefix='/api/v3/workspaces/'+${JSON.stringify(fixture.workspaceId)};
    const accounts=(await (await fetch(prefix+'/financial-accounts')).json()).data;
    if(!accounts.some(item=>item.id===${JSON.stringify(wallet)})){
      const response=await fetch(prefix+'/financial-accounts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:${JSON.stringify(wallet)},code:${JSON.stringify(code)},name:${JSON.stringify(walletName)},type:'asset',subtype:'cash',segment:'living',balanceSource:'monthly_snapshot',ownerPartyId:'owner',allowedCommodityCodes:['CNY']})});
      if(!response.ok)throw Error('Synthetic account setup failed');
    }
  })()`);
  navigate('#/living/balances');
  assert(evaluate("!!document.querySelector('.recorded-balance-form input[name=observedDate][type=date]')"), 'Living accepts an actual date, not a month-end input.');
  const before = api('/balance-records').filter(item => item.subjectId === wallet);
  command('click', '.recorded-balance-form .select-field button'); command('wait', '[role=listbox]');
  evaluate(`[...document.querySelectorAll('[role=option]')].find(item=>item.textContent.includes(${JSON.stringify(code)})).click()`);
  assert(evaluate("document.querySelector('.recorded-balance-form .select-custom button').getBoundingClientRect().right <= document.querySelector('.recorded-balance-form input[name=observedDate]').getBoundingClientRect().left"), 'Long account labels must not overlap the actual-date input.');
  for (const [day, amount] of [['2026-08-12','100.1'], ['2026-08-12','120.25'], ['2026-08-13','121.35'], ['2026-08-05','80']]) {
    // Chrome date widgets need input + change; observe only public DOM, never React state.
    evaluate(`(()=>{const input=document.querySelector('.recorded-balance-form input[name=observedDate]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(day)});input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    assert(evaluate(`document.querySelector('.recorded-balance-form').textContent.includes(${JSON.stringify(day)})`));
    command('fill', '.recorded-balance-form input[name=amount]', amount);
    command('fill', '.recorded-balance-form input[name=source]', 'Synthetic actual-date statement');
    command('check', '.recorded-balance-form input[type=checkbox]');
    command('click', '.recorded-balance-form button[type=submit]'); settled();
  }
  const recorded = api('/balance-records').filter(item => item.subjectId === wallet);
  assert.equal(recorded.length, before.length + 4, 'Same-day values append rather than replace the earlier record.');
  assert.deepEqual(recorded.slice(-4).map(item => item.observedDate), ['2026-08-12','2026-08-12','2026-08-13','2026-08-05']);
  command('click', '.snapshot-toolbar .select-field button'); command('wait', '[role=listbox]');
  evaluate(`[...document.querySelectorAll('[role=option]')].find(item=>item.textContent.includes(${JSON.stringify(walletName)})).click()`);
  const latest = rows('Latest balance snapshots').find(row => row[0] === walletName);
  assert(latest.includes('121.35') && latest.includes('2026-08-13'), 'Backfilled earlier dates must not replace the actual latest balance.');
  assert.equal(evaluate("document.querySelector('.snapshot-history').open"), false);
  command('click', '.snapshot-history > summary');
  assert(rows('Snapshot history').some(row => row.includes('2026-08-05')));
  checks.push('Actual-date entry, same-day append, chronological latest and folded history');
  navigate('#/living/livingreview/2026-08');
  const review = rows('Dated monthly balance review').find(row => row[0].includes(code));
  assert(review.includes('2026-08-13') && review.includes('121.35') && review.includes('2026-08-12') && review.includes('1.1'));
  assert(evaluate("document.querySelector('.recorded-review').textContent.includes('not income or spending')"));
  const legacy = api('/monthly-observations').filter(item => !item.observedDate);
  assert(legacy.length > 0, 'The fixture retains old observations separately.');
  assert.equal(evaluate("document.querySelector('.legacy-reconciliation').open"), false);
  checks.push('Monthly selection shows both actual comparison dates, exact backend delta and explicit legacy reconciliation');
  navigate('#/living/livingreview/2026-09');
  const empty = rows('Dated monthly balance review').find(row => row[0].includes(code));
  assert(empty.includes('Unknown') && !empty.includes('0') && !empty.includes('121.35'), 'Missing month never becomes zero or a carried balance.');
  checks.push('A missing month is Unknown without carry-forward or fabricated zero');
  navigate('#/living/balances');
  command('click', '.snapshot-toolbar .select-field button'); command('wait', '[role=listbox]');
  evaluate(`[...document.querySelectorAll('[role=option]')].find(item=>item.textContent.includes(${JSON.stringify(walletName)})).click()`);
  assert.equal(rows('Latest balance snapshots').length, 1);
  checks.push('Account filter applies to latest and historical balance rows');
  for (const width of [1024,1440,1920]) {
    command('set','viewport',String(width),'1000');
    evaluate('document.activeElement?.blur(); window.scrollTo({top:0,behavior:"instant"})');
    evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    assert(evaluate('document.documentElement.scrollWidth <= innerWidth'), `No page overflow at ${width}.`);
    assert(evaluate("document.querySelector('.recorded-balance-form .select-custom button').getBoundingClientRect().right <= document.querySelector('.recorded-balance-form input[name=observedDate]').getBoundingClientRect().left"), `Account and date fields do not overlap at ${width}.`);
    if (width === 1024) assert.equal(evaluate("getComputedStyle(document.querySelector('.recorded-balance-form .form-grid')).gridTemplateColumns.split(' ').length"), 2, 'The four balance inputs form two balanced rows on a narrower desktop.');
    command('screenshot',join(evidence,`dated-balances-${width}.png`),'--full');
  }
  navigate('#/living/livingreview/2026-08');
  command('set','viewport','1440','1000');
  evaluate('document.activeElement?.blur(); window.scrollTo({top:0,behavior:"instant"})');
  evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  command('screenshot',join(evidence,'dated-review-1440.png'),'--full');
  writeFileSync(join(evidence,'receipt.json'),JSON.stringify({syntheticOnly:true,checks,desktopWidths:[1024,1440,1920],productionMigration:false},null,2));
  console.log(`Passed ${checks.length} dated balance UI/API checks.`);
} catch(error) {
  writeFileSync(join(evidence,'failure.txt'),error.stack || String(error));
  throw error;
}
