// UI regressions through the actual browser + Workspace API, using owned synthetic fixtures only.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + '\\'), 'Select an owned .tmp run.');
const fixture = JSON.parse(readFileSync(join(run, 'fixture.json'), 'utf8'));
assert.equal(fixture.syntheticOnly, true);
const caseName = process.argv[2] || 'all';
assert(/^[a-z0-9-]+$/i.test(caseName), 'Use a simple in-run evidence label.');
const evidence = join(run, 'browser-' + caseName);
mkdirSync(evidence, { recursive: true });
process.env.TEMP = join(evidence, 'profiles'); process.env.TMP = process.env.TEMP;
mkdirSync(process.env.TEMP, { recursive: true });
assert(process.env.ARCHIFY_SKILL_ROOT, 'Use the existing approved Chrome tooling.');
const { ChromeVisualBrowser, findChrome } = await import(pathToFileURL(join(process.env.ARCHIFY_SKILL_ROOT, 'bin/visual-check.mjs')));
const browser = new ChromeVisualBrowser(findChrome()), session = await browser.sessionPromise;
const send = (method, params = {}) => browser.cdp.send(method, params, session);
const evaluate = async expression => {
  const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
};
const wait = async expression => {
  for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 100)); }
  throw Error('UI condition timed out: ' + expression);
};
const settled = () => wait("!!document.querySelector('.app-shell') && !document.querySelector('.loading-line') && !document.querySelector('[aria-busy=true]')");
const fill = (selector, value) => evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});assertInput(input);function assertInput(value){if(!value)throw Error('Missing field')};const proto=input.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);
const click = (label, scope = 'document') => evaluate(`(()=>{const root=${scope === 'document' ? 'document' : `document.querySelector(${JSON.stringify(scope)})`};const button=[...root.querySelectorAll('button')].find(item=>(item.closest('.configuration-nav')?item.querySelector('span').textContent:item.textContent).trim()===${JSON.stringify(label)});if(!button||button.disabled)throw Error('Unavailable: '+${JSON.stringify(label)});button.click();})()`);
const capture = async name => {
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const { data } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  writeFileSync(join(evidence, name + '.png'), Buffer.from(data, 'base64'));
};
const glide = async (name, label) => {
  await evaluate(`[...document.querySelectorAll('.select-field')].find(item=>item.querySelector('select')?.name===${JSON.stringify(name)}).querySelector('button').click()`);
  await wait("!!document.querySelector('[role=listbox]')");
  await evaluate(`[...document.querySelectorAll('[role=option]')].find(item=>item.firstElementChild.textContent.trim()===${JSON.stringify(label)}).click()`);
};
const checks = [];
try {
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  // localhost uses our IPv6 listener; the user's IPv4 dev server/Vault is never used.
  await send('Page.navigate', { url: 'http://localhost:5174/__synthetic_marker' });
  await wait("document.body.textContent === 'fc-ui-account-fixes-synthetic-only'");
  await send('Page.navigate', { url: 'http://localhost:5174/#/overview/consolidated/2026-08' });
  await wait("!!document.querySelector('input[name=adminToken]')");
  await fill('input[name=adminToken]', 'synthetic-browser-admin'); await click('Enter Finance Core'); await settled();
  await fill('.workspace-tools select', fixture.workspaceId); await settled();
  await evaluate(`(async()=>{const path='/api/v3/workspaces/'+${JSON.stringify(fixture.legacyWorkspaceId)}+'/accounts';const account=(await (await fetch(path)).json()).data.find(item=>item.id==='cash-cny');if(account.status!=='active'){const response=await fetch(path+'/cash-cny',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...account,status:'active'})});if(!response.ok)throw Error('Synthetic fixture reset failed');}})()`);
  // Restore only mutable synthetic metadata after a failing regression run; posted facts stay intact.
  await evaluate(`(async()=>{
    const prefix='/api/v3/workspaces/'+${JSON.stringify(fixture.legacyWorkspaceId)};
    const account=(await (await fetch(prefix+'/living-accounts')).json()).data.find(item=>item.id==='wallet-alpha');
    const source=(await (await fetch(prefix+'/living-snapshots')).json()).data.find(item=>item.accountId==='wallet-alpha'&&item.balance==='23');
    if(account.updatedAt!==source.recordedAt){
      const response=await fetch(prefix+'/living-accounts/wallet-alpha',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...account,updatedAt:source.recordedAt})});
      if(!response.ok)throw Error('Synthetic metadata reset failed');
    }
  })()`);
  await evaluate("location.hash='#/overview/consolidated/2026-08'"); await settled();

  assert.equal(await evaluate("document.querySelector('.configuration-nav button').textContent.trim()"), 'Overview');
  assert.equal(await evaluate("!!document.querySelector('main input, main select, main form')"), false, 'Overview is display-only, with no parameter form');
  assert.equal(await evaluate("document.querySelector('main').textContent.includes('Next steps')"), false);
  assert.equal(await evaluate("document.querySelector('main').textContent.includes('5447.5')"), true, 'Known synthetic personal wealth');
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.configuration-nav button')).backgroundColor"), 'rgb(232, 242, 255)');
  const dashboardRoute = await evaluate('location.hash');
  await click('Investment', 'main .subnav');
  assert.equal(await evaluate('location.hash'), dashboardRoute, 'Dashboard perspectives do not navigate');
  assert.equal(await evaluate("!!document.querySelector('[aria-label=\"investment financial overview\"]')"), true);
  await click('Living', 'main .subnav');
  assert.equal(await evaluate('location.hash'), dashboardRoute);
  await click('Consolidated', 'main .subnav');
  assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true);
  await capture('overview-1440'); checks.push('Read-only Overview and blue status-free navigation');

  assert.equal(await evaluate("getComputedStyle(document.querySelector('#main-navigation')).position"), 'sticky');
  assert.match(await evaluate("getComputedStyle(document.querySelector('#main-navigation')).backdropFilter"), /blur/);
  await evaluate('window.scrollTo(0,500)');
  assert.equal(await evaluate("Math.round(document.querySelector('#main-navigation').getBoundingClientRect().top)"), 12);
  await capture('sticky-navigation-1440'); checks.push('Horizontal navigation remains sticky with frosted background');

  await click('Master data', '.configuration-nav'); await settled();
  await evaluate('window.scrollTo(0,420)');
  const tabScroll = await evaluate('window.scrollY');
  assert(tabScroll > 300, 'Start at the Master data tabs, below the page header');
  await click('Accounts', '.subnav'); await settled();
  assert.equal(await evaluate('Math.round(window.scrollY)'), tabScroll, 'Tab changes must preserve scroll');
  await click('Prices', '.subnav'); await settled();
  assert.equal(await evaluate('Math.round(window.scrollY)'), tabScroll);
  await click('Commodities', '.subnav'); await settled();
  assert.equal(await evaluate('Math.round(window.scrollY)'), tabScroll);
  await capture('master-tabs-1440'); checks.push('Master data tabs preserve scroll position');

  await fill('.workspace-tools select', fixture.legacyWorkspaceId); await settled();
  await click('Master data', '.configuration-nav'); await settled(); await click('Accounts', '.subnav'); await settled();
  assert.equal(await evaluate("!!document.querySelector('select[name=segment]')"), true, 'Schema-2 registration also exposes the segment selector');
  await glide('segment', 'Living');
  assert.equal(await evaluate("document.querySelector('select[name=segment]').value"), 'living');
  await fill('input[name=name]', 'Synthetic central registration');
  await click('Add account'); await settled();
  const registered = await evaluate(`(async()=>{const prefix='/api/v3/workspaces/'+${JSON.stringify(fixture.legacyWorkspaceId)};return (await (await fetch(prefix+'/living-accounts')).json()).data.find(item=>item.name==='Synthetic central registration');})()`);
  assert(registered, 'Legacy Living account was saved via the centralized Master data form');
  await capture('legacy-segment-registration-1440'); checks.push('Glide Select registers Living accounts centrally without migrating schema-2');

  const accountRow = name => `[...document.querySelectorAll('table tbody tr')].find(row=>[...row.querySelectorAll('td')].some(cell=>cell.textContent.trim()===${JSON.stringify(name)}))`;
  const originalAlpha = await evaluate(`(async()=>{return (await (await fetch('/api/v3/workspaces/'+${JSON.stringify(fixture.legacyWorkspaceId)}+'/living-accounts')).json()).data.find(item=>item.id==='wallet-alpha');})()`);
  await evaluate(`${accountRow('Synthetic Alpha')}.querySelector('button').click()`);
  assert.equal(await evaluate("document.querySelector('input[name=balance]').readOnly"), true, 'Metadata edits cannot change recorded balances');
  await fill('input[name=note]', 'Synthetic metadata edit'); await click('Save account'); await settled();
  const editedAlpha = await evaluate(`(async()=>{return (await (await fetch('/api/v3/workspaces/'+${JSON.stringify(fixture.legacyWorkspaceId)}+'/living-accounts')).json()).data.find(item=>item.id==='wallet-alpha');})()`);
  assert.equal(editedAlpha.balance, originalAlpha.balance);
  assert.equal(editedAlpha.updatedAt, originalAlpha.updatedAt, 'Metadata editing preserves the balance recording timestamp');
  await evaluate('window.confirm=()=>true');
  assert.equal(await evaluate(`!!${accountRow('Synthetic central registration')}.querySelector('button.danger')`), true, 'Unused account deletion is actionable');
  await evaluate(`${accountRow('Synthetic central registration')}.querySelector('button.danger').click()`); await settled();
  assert.equal(await evaluate(`(async()=>{return (await (await fetch('/api/v3/workspaces/'+${JSON.stringify(fixture.legacyWorkspaceId)}+'/living-accounts')).json()).data.some(item=>item.id===${JSON.stringify(registered.id)});})()`), false);
  await evaluate(`${accountRow('CNY Cash')}.querySelector('button[data-action=end-purpose]').click()`);
  await wait("!!document.querySelector('dialog[open]')");
  await click('End purpose', 'dialog'); await settled();
  assert.equal(await evaluate(`(async()=>{return (await (await fetch('/api/v3/workspaces/'+${JSON.stringify(fixture.legacyWorkspaceId)}+'/accounts')).json()).data.find(item=>item.id==='cash-cny').status;})()`), 'inactive');
  assert.equal(await evaluate(`(async()=>{return (await (await fetch('/api/v3/workspaces/'+${JSON.stringify(fixture.legacyWorkspaceId)}+'/journal-entries')).json()).data.length;})()`), 1);
  await capture('account-lifecycle-1440'); checks.push('Unused deletion and end-purpose retain Journal history');

  await fill('input[name=name]', 'Discard this unsaved form');
  await evaluate(`${accountRow('Capital')}.querySelector('button[data-action=end-purpose]').click()`);
  await wait("!!document.querySelector('dialog[open]')"); await click('Cancel', 'dialog');
  assert.equal(await evaluate("document.querySelector('input[name=name]').value"), '', 'Accepting discard must actually reset the underlying form');
  checks.push('Account lifecycle honors physical dirty-form discard');

  await click('Living', '.segment-switcher'); await settled(); await click('Snapshots', '.subnav'); await settled();
  assert.equal(await evaluate("document.querySelector('[aria-label=\"Latest balance snapshots\"]')?.querySelectorAll('table > tbody > tr').length"), 2, 'Show one latest snapshot per account, not all 48 historical rows');
  assert.equal(await evaluate("document.querySelector('[aria-label=\"Latest balance snapshots\"] tbody td').textContent.trim()"), 'Synthetic Alpha');
  assert.equal(await evaluate("document.querySelector('[aria-label=\"Latest balance snapshots\"] tbody td:nth-child(2)').textContent"), '23', 'Equal legacy timestamps must still show the current recorded balance');
  await evaluate("document.querySelector('.snapshot-list').scrollIntoView({block:'center'})");
  await capture('compact-snapshots-1440');
  await evaluate("document.querySelector('.snapshot-history > summary').click()");
  assert.equal(await evaluate("document.querySelector('.snapshot-history table tbody').children.length"), 10, 'History is paged without discarding records');
  await click('Next', '.snapshot-history');
  assert.equal(await evaluate("document.querySelector('.snapshot-history table tbody').children.length"), 10);
  await evaluate("document.querySelector('.snapshot-history').scrollIntoView({block:'start'})");
  await capture('snapshot-history-1440'); checks.push('Readable latest-per-account snapshots with expandable paged history');

  const monthlyWorkspace = await evaluate(`(async()=>{const request=async(path,body)=>{const response=await fetch('/api/v3'+path,{method:path.includes('finance-parties')?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!response.ok)throw Error('Synthetic monthly fixture failed');return response.json();};const wid=(await request('/workspaces',{displayName:'Synthetic monthly UI',kind:'sandbox'})).data.id;const prefix='/workspaces/'+wid;await request(prefix+'/commodities',{code:'CNY',kind:'currency',scale:2,name:'Synthetic currency'});await request(prefix+'/finance-parties/owner',{id:'owner',name:'Synthetic owner'});for(let i=0;i<12;i++){const id='monthly-'+String(i).padStart(2,'0');await request(prefix+'/financial-accounts',{id,code:id,name:'Synthetic monthly '+String(i).padStart(2,'0'),type:'asset',subtype:'cash',segment:'living',balanceSource:'monthly_snapshot',ownerPartyId:'owner',allowedCommodityCodes:['CNY']});await request(prefix+'/monthly-observations',{id:'obs-'+i,subjectId:id,month:'2026-08',kind:'balance',currency:'CNY',amount:'9007199254740993.01',source:'Synthetic statement',confirmed:false});}return wid;})()`);
  await click('Settings', '.configuration-nav'); await settled();
  await fill('.workspace-tools select', monthlyWorkspace); await settled();
  await evaluate("location.hash='#/living/balances/2026-08'");
  await wait("document.querySelector('main input[type=month]')?.value==='2026-08'"); await settled();
  assert.equal(await evaluate("document.querySelectorAll('.balance-account:not([open])').length"), 12, 'Many account editors are collapsed by default');
  assert.equal(await evaluate("document.querySelector('[aria-label=\"Latest balance snapshots\"] table tbody').children.length"), 10);
  assert.equal(await evaluate("document.querySelector('[aria-label=\"Latest balance snapshots\"] tbody td:nth-child(2)').textContent"), '9007199254740993.01', 'Decimal strings are never rounded by the UI');
  await evaluate("document.querySelector('.balance-account').scrollIntoView({block:'start'})");
  await capture('monthly-balances-1440');
  await evaluate("document.querySelector('.balance-account > summary').click()");
  assert.equal(await evaluate("document.querySelector('.balance-account input[inputmode=decimal]').value"), '9007199254740993.01');
  await fill('.balance-account input[value=""]', 'Synthetic review correction');
  await evaluate("document.querySelector('.balance-account input[type=checkbox]').click()");
  await click('Confirm balance', '.balance-account'); await settled();
  assert.equal(await evaluate("document.querySelector('[aria-label=\"Latest balance snapshots\"] tbody td:last-child').textContent"), 'Confirmed');
  await evaluate("document.querySelector('.snapshot-list').scrollIntoView({block:'center'})");
  await capture('monthly-snapshots-1440'); checks.push('Many monthly accounts stay compact, pending/confirmed values retain exact decimals');

  await click('Master data', '.configuration-nav'); await settled(); await click('Accounts', '.subnav'); await settled();
  await glide('segment', 'Living'); await fill('input[name=code]', 'spare'); await fill('input[name=name]', 'Synthetic lifecycle spare');
  await glide('ownerPartyId', 'Synthetic owner'); await click('Add account'); await settled();
  const spare = await evaluate(`(async()=>{return (await (await fetch('/api/v3/workspaces/'+${JSON.stringify(monthlyWorkspace)}+'/financial-accounts')).json()).data.find(item=>item.code==='spare');})()`);
  assert.equal(spare.segment, 'living'); assert.equal(spare.balanceSource, 'monthly_snapshot'); assert.equal(spare.ownerPartyId, 'owner');
  await evaluate(`${accountRow('Synthetic monthly 00')}.querySelector('button[data-action=end-purpose]').click()`);
  await wait("!!document.querySelector('dialog[open]')"); await fill('dialog input[name=endMonth]', '2026-08');
  await capture('end-purpose-1440'); await click('End purpose', 'dialog'); await settled();
  await evaluate(`${accountRow('Synthetic lifecycle spare')}.querySelector('button.danger').click()`); await settled();
  await evaluate(`${accountRow('Synthetic monthly 00')}.querySelector('button.danger').click()`); await settled();
  const retained = await evaluate(`(async()=>{const prefix='/api/v3/workspaces/'+${JSON.stringify(monthlyWorkspace)};const accounts=(await (await fetch(prefix+'/financial-accounts')).json()).data;const observations=(await (await fetch(prefix+'/monthly-observations')).json()).data;return {account:accounts.find(item=>item.id==='monthly-00'),spare:accounts.some(item=>item.id===${JSON.stringify(spare.id)}),observations:observations.filter(item=>item.subjectId==='monthly-00')};})()`);
  assert.equal(retained.spare, false); assert.equal(retained.account.endMonth, '2026-08'); assert.equal(retained.account.status, 'inactive');
  assert.equal(retained.observations.length, 2, 'Stopping/deletion refusal preserves pending source and confirmed correction');
  await evaluate("location.hash='#/living/balances/2026-09'"); await settled();
  assert.equal(await evaluate("document.querySelectorAll('.balance-account').length"), 11, 'Ended account is not editable after its final month');
  await evaluate("location.hash='#/living/balances/2026-08'"); await settled();
  assert.equal(await evaluate("document.querySelectorAll('.balance-account').length"), 12, 'Its historical month stays correctable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true);
  await evaluate("document.querySelector('.snapshot-list').scrollIntoView({block:'center'})");
  await capture('monthly-snapshots-1920'); checks.push('Schema-3 central registration, safe deletion and dated end-purpose preserve history');

  writeFileSync(join(evidence, 'receipt.json'), JSON.stringify({ syntheticOnly: true, checks, productionMigration: false }, null, 2));
  console.log(JSON.stringify({ passed: checks.length, evidence }));
} finally {
  browser.cdp.failAll(new Error('Owned synthetic verification finished'));
  if (browser.child.exitCode === null) browser.child.kill();
}
