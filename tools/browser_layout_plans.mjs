// Public UI/HTTP verification against an explicitly owned synthetic server, never a personal Vault.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';

const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + sep));
const fixture = JSON.parse(readFileSync(join(run, 'fixture.json'), 'utf8'));
assert.equal(fixture.syntheticOnly, true);
assert.equal(fixture.ui, 'http://localhost:5174');
assert(process.env.AGENT_BROWSER_ARGS?.includes('--host-resolver-rules=MAP localhost [::1]'),'Pin localhost to the owned IPv6 test server before launching the browser.');
assert(process.env.FC_AGENT_BROWSER && process.env.AGENT_BROWSER_SESSION && process.env.AGENT_BROWSER_NAMESPACE);
const call = (...args) => {
  const result = JSON.parse(execFileSync(process.env.FC_AGENT_BROWSER, ['--json', ...args], { encoding:'utf8', timeout:45000 }));
  assert.equal(result.success, true, result.error || 'Browser operation failed'); return result.data;
};
const evaluate = source => call('eval', '-b', Buffer.from(source).toString('base64')).result;
const wait = source => call('wait', '--fn', source);
const settled = () => wait("!!document.querySelector('.app-shell') && !document.querySelector('[aria-busy=true]') && !document.querySelector('.loading-line')");
const navigate = hash => { evaluate(`location.hash=${JSON.stringify(hash)}`); settled(); };
const click = name => call('find','role','button','click','--name',name,'--exact');
const capture = name => { evaluate('window.scrollTo({top:0,behavior:"instant"});document.activeElement?.blur()'); call('mouse','move','1','1'); call('screenshot',join(run,name + '.png')); };
const checks = [];

call('open',fixture.ui + '/api/v3/__synthetic_marker');
assert.equal(evaluate('document.body.textContent'), 'fc-layout-plans-synthetic-only');
call('set','viewport','1600','1000'); call('open',fixture.ui + '/#/overview/consolidated/2026-09');
wait("!!document.querySelector('input[name=adminToken]') || !!document.querySelector('.app-shell')");
if (evaluate("!!document.querySelector('input[name=adminToken]')")) { call('fill','input[name=adminToken]','synthetic-layout-admin'); click('Enter Finance Core'); }
settled();
if (evaluate("document.querySelector('.workspace-tools select').value") !== fixture.workspaceId) call('select','.workspace-tools select',fixture.workspaceId);
settled();
evaluate('window.confirm=()=>true');

for (const [width,height] of [[1440,900],[1600,1000],[1920,1080],[2560,1440]]) {
  call('set','viewport',String(width),String(height));
  for (const [name,hash] of [['overview','#/overview/consolidated/2026-09'],['journal','#/investment/journal'],['review','#/investment/monthlyreview/2026-09'],['living','#/living/livingreview/2026-09'],['master','#/master/accounts'],['settings','#/settings']]) {
    navigate(hash);
    const layout = evaluate(`(()=>{
      const rect=node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
      return {viewport:innerWidth,width:document.documentElement.scrollWidth,shell:rect(document.querySelector('.app-shell')),main:rect(document.querySelector('main')),
        rail:!!document.querySelector('.workbench-rail'),fonts:[...document.querySelectorAll('.branched-menu button,.subnav button,.field>label')].filter(node=>node.getClientRects().length).map(node=>parseFloat(getComputedStyle(node).fontSize)),
        heightStyle:document.querySelector('.page-content').style.height,dateInputs:document.querySelectorAll('input[type=date],input[type=month],input[type=datetime-local]').length};})()`);
    assert(layout.width <= width, name + ': no document overflow');
    assert(layout.shell.width > width * .92, name + ': fluid desktop width');
    assert(layout.fonts.every(size => size >= 14), name + ': readable labels');
    assert.equal(layout.rail, name !== 'overview');
    assert.equal(layout.heightStyle, '', 'Page height is natural, not a JS animation');
    assert.equal(layout.dateInputs, 0, 'No browser-localized date controls');
    if (['overview','review','living','master'].includes(name) && [1600,2560].includes(width)) capture(name + '-' + width);
    checks.push({name,width,height,layout});
  }
}

call('set','viewport','1600','1000'); call('open',fixture.ui + '/?navigation-check=1#/investment/journal'); call('reload'); settled();
evaluate('window.confirm=()=>true');
wait("document.querySelector('.branched-menu__head[aria-current=page]')?.textContent==='Journal'");
click('Monthly review'); settled();
wait("document.querySelector('.branched-menu__head[aria-current=page]')?.textContent==='Monthly review'");
wait("document.querySelectorAll('.branched-menu__section:has(>.branched-menu__head[aria-current=page]) .branched-menu__item').length===2");
wait("document.querySelectorAll('.branched-menu__head[aria-expanded=true]').length===2");
assert.equal(evaluate("document.querySelectorAll('.line-sidebar').length"),0, 'Legacy sidebar is retired');
for (const name of ['Immutable month close','Investment monthly review','Immutable month close','Investment monthly review']) {
  click(name);
  const samples = evaluate(`new Promise(resolve=>{const samples=[],start=performance.now();const frame=()=>{const node=document.querySelector('.branched-menu__item[aria-current=location]');const target=document.getElementById([...document.querySelectorAll('[data-section-title]')].find(item=>item.dataset.sectionTitle===${JSON.stringify(name)})?.id);samples.push({label:node?.textContent,y:target?.getBoundingClientRect().top,scroll:scrollY});if(performance.now()-start<1100)requestAnimationFrame(frame);else resolve(samples);};requestAnimationFrame(frame);})`);
  assert(samples.every(sample => sample.label === name), 'Clicked branch never becomes another section');
  assert(Math.abs(samples.at(-1).scroll-samples.at(-6).scroll) <= 1, 'Eased scrolling settles without drift');
  assert(samples.at(-1).y >= 70 && samples.at(-1).y < 650, 'Target settles below sticky navigation and in the reading area');
  checks.push({branch:name,samples});
}
checks.push('Branch selection stays controlled throughout eased scrolling; no scroll spy retargets it.');
capture('branched-menu-1600');
click('Posted journal'); settled(); wait("document.querySelector('.branched-menu__item[aria-current=location]')?.textContent==='Posted journal'");
click('Investment monthly review'); settled(); wait("document.querySelector('.branched-menu__item[aria-current=location]')?.textContent==='Investment monthly review'");
checks.push('A retained branch in an inactive expanded group navigates to its page and the exact heading.');
click('Posted journal'); settled(); wait("document.querySelector('.branched-menu__item[aria-current=location]')?.textContent==='Posted journal'");
const failedReport = fixture.ui + '/api/v3/workspaces/' + fixture.workspaceId + '/reports/investment-monthly-review*';
call('network','route',failedReport,'--abort');
try {
  click('Investment monthly review'); wait("!!document.querySelector('.global-notice.error') && !document.querySelector('[aria-busy=true]')");
  assert.equal(evaluate("document.querySelector('.branched-menu__head[aria-current=page]').textContent"),'Journal','Failed scoped read retains the current page');
} finally { call('network','unroute',failedReport); }
click('Dismiss notification');
if (evaluate("[...document.querySelectorAll('.branched-menu__head')].find(node=>node.textContent==='Monthly review').getAttribute('aria-expanded')==='true'")) click('Monthly review');
click('Monthly review'); settled(); wait("document.querySelector('.branched-menu__head[aria-current=page]')?.textContent==='Monthly review'");
assert.equal(evaluate("document.querySelector('.branched-menu__item[aria-current=location]')?.textContent || ''"),'','Failed navigation must not leave a delayed branch selection on a later page visit');
checks.push('A failed cross-page branch read retains the page and discards its pending scroll before a later ordinary visit.');

navigate('#/master/accounts');
const before = evaluate('document.querySelector("main").getBoundingClientRect().width');
for (const name of ['Commodities','Prices','Accounts']) { click(name); settled(); assert.equal(evaluate('document.querySelector("main").getBoundingClientRect().width'),before); }
navigate('#/living/plans/2026-02');
const interval = value => { evaluate("[...document.querySelectorAll('.select-field')].find(node=>node.querySelector('label').textContent.startsWith('Repeat interval')).querySelector('button').click()"); call('find','role','option','click','--name',value,'--exact'); };
interval('Annual');
const planName = 'Synthetic annual UI check ' + Date.now();
call('fill','input[name=name]',planName); call('fill','input[name=amount]','12.34'); call('fill','input[name=category]','UI regression');
call('fill','input[name=startDate]','2026-02-01'); call('fill','input[name=dayOfMonth]','28'); click('Add plan'); settled();
assert(evaluate(`[...document.querySelectorAll('tbody tr')].some(row=>row.textContent.includes(${JSON.stringify(planName)})&&row.textContent.includes('Annual')&&row.textContent.includes('2026-02-28'))`));
const stored = evaluate(`(async()=>{const result=await fetch('/api/v3/workspaces/${fixture.workspaceId}/monthly-plans');return (await result.json()).data.find(item=>item.name===${JSON.stringify(planName)});})()`);
assert.equal(stored.repeatEveryMonths,12); assert.equal(stored.dayOfMonth,28); assert.equal(stored.startDate,'2026-02-01');
call('fill','input[name=name]','Invalid synthetic date'); call('fill','input[name=amount]','1'); call('fill','input[name=category]','UI regression');
call('fill','input[name=startDate]','2026-02-30'); click('Add plan');
assert(evaluate("document.querySelector('.input-error')?.textContent.includes('Enter a valid date as YYYY-MM-DD')"));
assert(evaluate(`(async()=>{const r=await fetch('/api/v3/workspaces/${fixture.workspaceId}/monthly-plans');return !(await r.json()).data.some(item=>item.name==='Invalid synthetic date');})()`));
checks.push('Impossible calendar dates fail with English inline feedback and do not persist a plan.');
call('fill','input[name=startDate]','2026-02-01'); click('Choose Start date'); wait("!!document.querySelector('.date-popover:popover-open')");
assert(evaluate("document.querySelector('.date-popover:popover-open').textContent.includes('Sun')"));
click('2026-02-21'); assert.equal(evaluate("document.querySelector('input[name=startDate]').value"),'2026-02-21');
interval('One time'); assert.equal(evaluate("document.querySelector('input[name=dayOfMonth]')"),null);
evaluate('document.querySelector("form.monthly-plan-form").reset()');
checks.push('Annual plan saved and reread through the Workspace API; English calendar selection updates the real input; one-time hides the unused due day.');
const monthRoute = evaluate('location.hash');
call('fill','input[data-date-kind=month]','2026-');
assert.equal(evaluate('location.hash'),monthRoute); assert.equal(evaluate("document.querySelector('input[data-date-kind=month]').value"),'2026-');
call('fill','input[data-date-kind=month]','2026-03'); settled();
wait("document.querySelector('input[data-date-kind=month]')?.value==='2026-03'");
assert(evaluate("location.hash.endsWith('/2026-03')"));
checks.push('Partial ISO month entry stays editable without navigation; a complete month changes the scoped report.');
navigate('#/investment/data/import');
assert(evaluate("document.body.textContent.includes('Choose file') && document.body.textContent.includes('No file selected')"));
assert(evaluate("[...document.querySelectorAll('input[type=file]')].every(node=>node.hidden && node.getAttribute('aria-hidden')==='true')"));
checks.push('Application-owned file affordances are English. The external OS file dialog is not tested or changed.');
writeFileSync(join(run,'browser-layout-plans.json'), JSON.stringify({syntheticOnly:true,checks},null,2));
console.log(`Passed ${checks.length} browser checks; screenshot evidence is local and synthetic.`);
