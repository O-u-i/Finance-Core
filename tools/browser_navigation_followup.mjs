// UI regression against an owned synthetic server, including an explicitly seeded schema-2 Vault.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';

const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + sep));
const fixture = JSON.parse(readFileSync(join(run,'fixture.json'),'utf8'));
assert.equal(fixture.syntheticOnly,true);
assert.equal(fixture.ui,'http://localhost:5174');
assert(process.env.AGENT_BROWSER_ARGS?.includes('--host-resolver-rules=MAP localhost [::1]'),'Pin localhost to the owned IPv6 test server before launching the browser.');
assert(fixture.legacyWorkspaceId && process.env.FC_AGENT_BROWSER && process.env.AGENT_BROWSER_SESSION && process.env.AGENT_BROWSER_NAMESPACE);
const call = (...args) => {
  const result = JSON.parse(execFileSync(process.env.FC_AGENT_BROWSER,['--json',...args],{encoding:'utf8',timeout:45000}));
  assert.equal(result.success,true,result.error || 'Browser operation failed'); return result.data;
};
const evaluate = source => call('eval','-b',Buffer.from(source).toString('base64')).result;
const wait = source => call('wait','--fn',source);
const settled = () => wait("!!document.querySelector('.app-shell') && !document.querySelector('[aria-busy=true]') && !document.querySelector('.loading-line')");
const navigate = hash => { evaluate(`location.hash=${JSON.stringify(hash)}`); settled(); };
const click = name => call('find','role','button','click','--name',name,'--exact');
const capture = name => { evaluate('window.scrollTo({top:0,behavior:"instant"});document.activeElement?.blur()'); call('mouse','move','1','1'); call('screenshot',join(run,name+'.png')); };
const rail = () => evaluate("[...document.querySelectorAll('.branched-menu__section')].map(node=>({title:node.querySelector('.branched-menu__head').textContent,branches:[...node.querySelectorAll('.branched-menu__item')].map(item=>item.textContent)}))");
const switchWorkspace = id => { call('select','.workspace-tools select',id); settled(); wait(`document.querySelector('.workspace-tools select').value===${JSON.stringify(id)}`); };
const checks = [];
const record = (name,detail=true) => { checks.push({name,detail}); writeFileSync(join(run,'browser-navigation.json'),JSON.stringify({checks},null,2)); };

call('open',fixture.ui+'/api/v3/__synthetic_marker');
assert.equal(evaluate('document.body.textContent'),'fc-layout-plans-synthetic-only');
call('set','viewport','1600','1000'); call('open',fixture.ui+'/#/investment/journal');
wait("!!document.querySelector('input[name=adminToken]') || !!document.querySelector('.app-shell')");
if (evaluate("!!document.querySelector('input[name=adminToken]')")) { call('fill','input[name=adminToken]','synthetic-layout-admin'); click('Enter Finance Core'); }
settled();
if (evaluate("document.querySelector('.workspace-tools select').value") !== fixture.workspaceId) switchWorkspace(fixture.workspaceId);
evaluate('window.__confirms=[]; window.confirm=text=>{window.__confirms.push(text);return true}');

for (const [width,height] of [[1440,900],[1600,1000],[1920,1080],[2560,1440]]) {
  call('set','viewport',String(width),String(height));
  for (const [name,hash] of [['journal','#/investment/journal'],['review','#/investment/monthlyreview/2026-09'],['living','#/living/balances'],['data','#/investment/data/import'],['master','#/master/accounts'],['settings','#/settings']]) {
    navigate(hash);
    const layout=evaluate(`(()=>{const q=s=>document.querySelector(s),r=n=>{const x=n.getBoundingClientRect();return {x:x.x,y:x.y,width:x.width,height:x.height}};return {viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,shell:r(q('.app-shell')),main:r(q('main')),gap:q('.workbench-session>button').getBoundingClientRect().left-q('.workspace-tools button').getBoundingClientRect().right,fonts:[...document.querySelectorAll('.branched-menu button,.subnav button,.field>label')].map(n=>parseFloat(getComputedStyle(n).fontSize)),nativeDates:document.querySelectorAll('input[type=date],input[type=month],input[type=datetime-local]').length}})()`);
    assert(layout.scrollWidth <= width && layout.shell.width > width*.92,'Fluid layout without document overflow');
    assert(layout.fonts.every(size=>size>=14),'Readable navigation and form labels');
    assert(layout.gap >= 8 && layout.gap <= 16,'Workspace and Sign out have a compact real control gap');
    assert.equal(layout.nativeDates,0);
    record(`${name} layout ${width}x${height}`,layout);
    if (width===1600 && ['review','living','data'].includes(name)) capture(name+'-modern-1600');
  }
}
call('set','viewport','1600','1000'); navigate('#/investment/journal');
for (const title of ['T-accounts','Securities & positions','Cash flow','Statements']) {
  assert.equal(rail().find(item=>item.title===title).branches.length,0);
}
record('Single-section pages have no redundant second-level heading');
const loadingGeometry=evaluate("(()=>{const main=document.querySelector('main'),panel=main.querySelector('[data-section-title]'),before=panel.getBoundingClientRect().top,node=document.createElement('div');node.className='loading-line';node.setAttribute('role','status');node.textContent='Loading records…';try{main.insertBefore(node,main.lastElementChild);return {shift:panel.getBoundingClientRect().top-before,position:getComputedStyle(node).position}}finally{node.remove()}})()");
assert(Math.abs(loadingGeometry.shift)<1,'A loading-status DOM fixture must not push page content');
record('Loading feedback reserves no document-flow space (CSS geometry fixture)',loadingGeometry);
assert.deepEqual(evaluate("[...document.querySelectorAll('.global-entries button')].map(n=>n.dataset.status)"),['ready','ready']);
record('Master data and Settings show verified green Ready states');

// Fold samples start in the same task as the click, not after a CLI round-trip.
for (const direction of ['close','open']) {
  const samples=evaluate(`new Promise(resolve=>{const section=[...document.querySelectorAll('.branched-menu__section')].find(n=>n.querySelector('.branched-menu__head').textContent==='Journal'),body=section.querySelector('.branched-menu__body'),head=section.querySelector('.branched-menu__head');head.click();const samples=[],start=performance.now();const frame=()=>{samples.push(body.getBoundingClientRect().height);if(performance.now()-start<420)requestAnimationFrame(frame);else resolve(samples)};frame()})`);
  const min=Math.min(...samples), max=Math.max(...samples);
  assert(max-min>60 && samples.some(value=>value>min+2 && value<max-2),'Fold has visible intermediate heights');
  assert(direction==='open' ? samples.at(-1)>samples[0] : samples.at(-1)<samples[0]);
  record('Branch '+direction+' uses a real transition',samples);
}
const hover=evaluate("(()=>{const n=[...document.querySelectorAll('.branched-menu__head')].find(n=>n.textContent==='Statements'),r=n.getBoundingClientRect(),s=getComputedStyle(n);return {x:r.x+80,y:r.y+r.height/2,background:s.backgroundColor,transform:s.transform}})()");
call('mouse','move',String(hover.x),String(hover.y));
const hovered=evaluate("(()=>{const s=getComputedStyle(document.querySelector('.branched-menu__head:hover'));return {background:s.backgroundColor,transform:s.transform}})()");
assert.equal(hovered.background,hover.background); assert.equal(hovered.transform,'none');
record('Menu hover only changes color, never a filled box or transform');

const scrollSamples = label => evaluate(`new Promise(resolve=>{const button=[...document.querySelectorAll('.branched-menu__item')].find(n=>n.textContent===${JSON.stringify(label)});button.click();const samples=[],start=performance.now();const frame=()=>{samples.push({y:scrollY,active:document.querySelector('.branched-menu__item[aria-current=location]')?.textContent,headingFocus:document.activeElement?.tagName==='H2'});if(performance.now()-start<1100)requestAnimationFrame(frame);else resolve(samples)};frame()})`);
const samples=scrollSamples('Posted journal');
assert(samples.at(-1).y-samples[0].y>60);
assert(samples.some(item=>item.y>samples[0].y+2 && item.y<samples.at(-1).y-2),'Scroll is eased, not an instantaneous jump');
assert(samples.slice(1).every(item=>item.active==='Posted journal' && !item.headingFocus),'React commits the requested branch without heading focus');
assert(samples.every((item,i)=>!i || item.y>=samples[i-1].y-1),'Scroll stays monotonic');
assert(Math.abs(samples.at(-1).y-samples.at(-6).y)<1,'Scroll settles without overshoot');
record('Branch scrolling is eased, bounded and does not focus headings',samples);
const rapid=evaluate("new Promise(resolve=>{const button=name=>[...document.querySelectorAll('.branched-menu__item')].find(n=>n.textContent===name);button('Unposted drafts').click();setTimeout(()=>button('Posted journal').click(),90);setTimeout(()=>resolve({active:document.querySelector('.branched-menu__item[aria-current=location]')?.textContent,y:scrollY}),1300)})");
assert.equal(rapid.active,'Posted journal'); assert(Math.abs(rapid.y-samples.at(-1).y)<2);
record('Rapid branch selection interrupts the previous motion without retargeting',rapid);
click('Unposted drafts'); wait("document.querySelector('.branched-menu__item[aria-current=location]')?.textContent==='Unposted drafts'");
assert(evaluate("document.activeElement?.classList.contains('branched-menu__item') && document.activeElement.textContent==='Unposted drafts'"));
record('A real pointer click keeps focus on the menu control, never on a heading');
capture('branched-menu-1600');

navigate('#/investment/data/import');
const before=rail();
for (const [tab,label,title] of [['backup','Segment export','Investment export'],['recurring','Recurring drafts','Recurring draft templates'],['batch','Atomic batch','Atomic batch creation'],['import','Import','Import drafts']]) {
  click(label); settled();
  assert.deepEqual(rail(),before,'Right-side tabs cannot rewrite sidebar structure');
  assert.equal(evaluate("document.querySelector('.branched-menu__item[aria-current=location]')?.textContent"),title);
  assert.equal(evaluate("document.activeElement?.closest('.subnav') ? document.activeElement.textContent : null"),label,'The shell retains focus on the selected tab while replacing its content');
  assert(evaluate(`!![...document.querySelectorAll('main [data-section-title]')].find(n=>n.dataset.sectionTitle===${JSON.stringify(title)})`));
  record('Internal tab '+tab+' and sidebar share the same selection');
}
click('Atomic batch creation'); settled(); wait("location.hash.endsWith('/data/batch')");
assert.equal(evaluate("document.querySelector('.subnav button[aria-current=page]').textContent"),'Atomic batch');
record('Sidebar branch selects the corresponding internal tab');
// Native localized file controls are not duplicated in the accessible UI.
navigate('#/investment/data/import');
assert(evaluate("[...document.querySelectorAll('input[type=file]')].every(n=>n.hidden && n.getAttribute('aria-hidden')==='true')"));
assert(evaluate("document.body.textContent.includes('No file selected')"));
record('English file picker has a single accessible chooser and filename state');
navigate('#/monthlyreview/2026-09');
assert.deepEqual(rail().find(item=>item.title==='Monthly review').branches,['Three-month comparison','Corrections and coverage']);
click('Corrections and coverage'); wait("document.querySelector('.branched-menu__item[aria-current=location]')?.textContent==='Corrections and coverage'");
record('Unscoped activity-report links use the matching sidebar destinations, not formal-close branches');

navigate('#/investment/journal'); click('New draft');
assert.equal(evaluate("document.querySelectorAll('dialog input[type=date],dialog input[type=month]').length"),0);
// Field IDs are generated; use the public label to select inputs reliably.
const field = (label,value) => { evaluate(`(()=>{const n=[...document.querySelectorAll('dialog .field')].find(n=>n.querySelector('label').textContent===${JSON.stringify(label)});n.querySelector('input').setAttribute('data-test-field','value')})()`); call('fill','dialog [data-test-field=value]',value); evaluate("document.querySelector('dialog [data-test-field]')?.removeAttribute('data-test-field')"); };
const draftLabel='Synthetic retained draft '+Date.now();
field('Description',draftLabel); field('Reference','retain-0.13');
const confirmsBefore=evaluate('window.__confirms.length'); click('Close Journal draft');
assert.equal(evaluate('window.__confirms.length'),confirmsBefore,'Close retains instead of asking to discard');
click('Resume draft');
assert(evaluate("[...document.querySelectorAll('dialog input')].some(n=>n.value==='retain-0.13')"));
click('Close Journal draft'); navigate('#/investment/taccounts'); navigate('#/investment/journal'); click('Resume draft');
assert(evaluate(`[...document.querySelectorAll('dialog input')].some(n=>n.value===${JSON.stringify(draftLabel)})`));
record('Close and page navigation retain the unfinished Journal editor');
field('Date','2026-02-30'); click('Validate draft');
assert(evaluate("!!document.querySelector('dialog .input-error') && !document.querySelector('dialog .validation')"));
record('Invalid English date input cannot bypass validation through Validate draft');
field('Date','2026-09-21');
const headerBeforeNotice=evaluate("document.querySelector('.workbench-header').getBoundingClientRect().top");
click('Validate draft'); settled(); wait("!!document.querySelector('dialog .validation.success')");
assert(evaluate("!!document.querySelector('.global-notice')"));
assert(Math.abs(evaluate("document.querySelector('.workbench-header').getBoundingClientRect().top")-headerBeforeNotice)<1,'A real operation notification must not move the header');
record('A real validation notification does not shift the workspace header');
assert(evaluate("document.querySelector('dialog .confirmation button').disabled"),'Fresh human confirmation is required');
click('Close Journal draft'); click('Resume draft');
assert.equal(evaluate("document.querySelectorAll('dialog .validation,dialog .confirmation').length"),0,'Resume cannot reuse an old validation/confirmation');
record('Resume requires fresh validation and never preserves posting approval');
click('Discard changes');
assert(!evaluate("!!document.querySelector('dialog[open]')"));
assert(evaluate(`document.querySelector('main').textContent.includes(${JSON.stringify(draftLabel)})`),'Discarding edits does not delete a saved backend draft');
const draftAction = action => evaluate(`(()=>{const row=[...document.querySelectorAll('.record-list article')].find(n=>n.querySelector('h3')?.textContent===${JSON.stringify(draftLabel)});[...row.querySelectorAll('button')].find(n=>n.textContent===${JSON.stringify(action)}).click()})()`);
draftAction('Review'); click('Close Journal draft');
assert(evaluate("[...document.querySelectorAll('.journal-tools button')].some(n=>n.textContent==='Resume draft')"));
draftAction('Delete'); settled();
assert(!evaluate("[...document.querySelectorAll('.journal-tools button')].some(n=>n.textContent==='Resume draft')"));
record('Deleting a saved draft clears only its matching retained editor');
click('New draft'); field('Description','Synthetic discarded unfinished input'); click('Discard draft'); click('New draft');
assert(!evaluate("[...document.querySelectorAll('dialog input')].some(n=>n.value==='Synthetic discarded unfinished input')"));
click('Close Journal draft');
record('Explicit discard clears an unfinished editor while saved drafts remain separately managed');
click('New draft'); field('Description','Synthetic session-only input'); click('Close Journal draft');
switchWorkspace(fixture.otherWorkspaceId); switchWorkspace(fixture.workspaceId); navigate('#/investment/journal');
assert(!evaluate("[...document.querySelectorAll('main button')].some(n=>n.textContent==='Resume draft')"));
record('Workspace changes warn and clear transient input without leaking it to another Vault');

// A missing configuration must remain accessible for repair but disable financial tools.
switchWorkspace(fixture.otherWorkspaceId); navigate('#/investment/journal');
assert.equal(evaluate("document.querySelector('.global-entries button').dataset.status"),'error');
assert(evaluate("[...document.querySelectorAll('.branched-menu button')].every(n=>n.disabled)"));
assert(evaluate("[...document.querySelectorAll('.global-entries button')].every(n=>!n.disabled)"));
record('Missing Master data is red; financial rail is disabled, repair navigation stays available');
switchWorkspace(fixture.workspaceId); navigate('#/investment/journal');
const configRoute=fixture.ui+'/api/v3/workspaces/'+fixture.workspaceId+'/commodities*';
call('network','route',configRoute,'--abort');
try {
  navigate('#/settings');
  wait("document.querySelector('.global-entries button')?.dataset.status==='error'");
  assert(evaluate("[...document.querySelectorAll('.branched-menu button')].every(n=>n.disabled)"));
  record('A failed configuration read clears stale green readiness and disables financial tools');
} finally { call('network','unroute',configRoute); }
click('Check configuration'); settled();
assert.equal(evaluate("document.querySelector('.global-entries button').dataset.status"),'ready');
record('Successful configuration retry restores verified readiness');
const healthRoute=fixture.ui+'/api/v3/workspaces/'+fixture.workspaceId+'/health';
call('network','route',healthRoute,'--abort');
try {
  navigate('#/settings');
  wait("document.querySelectorAll('.global-entries button')[1]?.dataset.status==='error'");
  assert(evaluate("[...document.querySelectorAll('.branched-menu button')].every(n=>n.disabled)"));
  record('Settings becomes red when Workspace health cannot be verified');
} finally { call('network','unroute',healthRoute); }
click('Check configuration'); settled();
assert.deepEqual(evaluate("[...document.querySelectorAll('.global-entries button')].map(n=>n.dataset.status)"),['ready','ready']);
record('A successful health retry restores both status indicators');
const livingOnly=evaluate(`(async()=>{const send=async(path,body,method='POST')=>{const r=await fetch('/api/v3'+path,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error('Synthetic setup failed');return (await r.json()).data};const w=await send('/workspaces',{displayName:'Synthetic Living-only '+Date.now(),kind:'sandbox'}),p='/workspaces/'+w.id;await send(p+'/commodities',{code:'CNY',kind:'currency',scale:2,name:'Synthetic currency'});await send(p+'/finance-parties/owner',{id:'owner',name:'Synthetic owner'},'PUT');await send(p+'/financial-accounts',{id:'living-only',code:'L1',name:'Synthetic Living account',type:'asset',allowedCommodityCodes:['CNY'],segment:'living',balanceSource:'monthly_snapshot',ownerPartyId:'owner'});return w.id})()`);
navigate('#/settings'); switchWorkspace(livingOnly); navigate('#/investment/journal');
assert.deepEqual(evaluate("[...document.querySelectorAll('.global-entries button')].map(n=>n.dataset.status)"),['ready','ready']);
record('Living-only configuration stays ready even when first read from a Journal route');
switchWorkspace(fixture.workspaceId);

switchWorkspace(fixture.legacyWorkspaceId); navigate('#/living/balances');
const legacyRail=rail();
assert.deepEqual(legacyRail.map(item=>item.title),['Accounts & balances','Assets & liabilities','Cash-flow plans','Monthly review','Import & export']);
assert(evaluate("document.body.textContent.includes('Legacy Vault') && document.body.textContent.includes('Synthetic legacy wallet')"));
for (const name of ['Snapshots','Living accounts','Snapshots']) { evaluate(`[...document.querySelectorAll('main .subnav button')].find(n=>n.textContent===${JSON.stringify(name)}).click()`); settled(); assert.deepEqual(rail(),legacyRail); }
evaluate("[...document.querySelectorAll('main .subnav button')].find(n=>n.textContent==='Living accounts').click()"); settled();
record('Schema-2 Living retains all five pages and stable account/snapshot navigation');
assert(evaluate("(()=>{const f=document.querySelector('.balance-form');return f.querySelector('button').getBoundingClientRect().left-f.querySelector('input').getBoundingClientRect().right>=8})()"),'Legacy balance input and Record button must not overlap');
record('Larger legacy balance inputs remain inside their field without covering Record');
capture('living-legacy-1600');
for (const [hash,expected] of [['#/living/assets','Asset register unavailable'],['#/living/plans','Cash-flow plans'],['#/living/livingreview','Living balance summary'],['#/living/livingdata','Legacy ledger export']]) {
  navigate(hash); assert(evaluate(`document.querySelector('main').textContent.includes(${JSON.stringify(expected)})`));
  assert.deepEqual(rail(),legacyRail); record('Legacy compatible destination '+hash);
}
navigate('#/investment/monthlyreview/2026-09');
assert(evaluate("document.querySelector('main').textContent.includes('External completeness unknown')"));
assert(!evaluate("document.querySelector('main').textContent.includes('Your month, in context.')"));
assert(evaluate("document.querySelector('main').textContent.includes('15.2')"),'Exact backend legacy activity is still displayed');
capture('review-legacy-1600'); record('Legacy monthly review is readable without hiding completeness or recalculating values');
navigate('#/investment/monthlyreview/2026-06');
assert(evaluate("!![...document.querySelectorAll('[data-section-title]')].find(n=>n.dataset.sectionTitle==='Corrections and coverage')"));
capture('review-legacy-empty-1600'); record('Empty legacy review retains the same two useful destinations');
const schema=evaluate(`fetch('/api/v3/workspaces/${fixture.legacyWorkspaceId}/health').then(r=>r.json()).then(r=>(r.data || r).ledgerSchemaVersion)`);
assert.equal(schema,2); record('Legacy browsing never migrates or rewrites the schema');

// Real reduced-motion media emulation, not a mocked application branch.
call('set','media','light','reduced-motion'); navigate('#/investment/journal');
const reduced=scrollSamples('Posted journal');
assert(evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches"));
assert(reduced.every(item=>Math.abs(item.y-reduced[0].y)<1));
assert.equal(evaluate("getComputedStyle(document.querySelector('.branched-menu__body')).transitionDuration"),'0s');
record('Reduced-motion disables fold and smooth scroll',reduced);
call('set','media','light');

const storage=evaluate('({local:localStorage.length,session:sessionStorage.length})');
assert.deepEqual(storage,{local:0,session:0}); record('No financial data or credentials enter browser storage',storage);
record('Completed against the production build; human acceptance and real Vault behavior remain separate');
console.log(JSON.stringify({passed:checks.length,receipt:join(run,'browser-navigation.json')},null,2));
