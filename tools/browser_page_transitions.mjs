// Public UI regression against an owned synthetic preview with one-shot delay controls.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';

const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + sep));
const fixture = JSON.parse(readFileSync(join(run,'fixture.json'),'utf8'));
assert(fixture.syntheticOnly && fixture.ui === 'http://localhost:5174');
assert(process.env.AGENT_BROWSER_ARGS?.includes('--host-resolver-rules=MAP localhost [::1]'));
assert(process.env.AGENT_BROWSER_NAMESPACE && process.env.AGENT_BROWSER_SESSION && process.env.FC_AGENT_BROWSER);
const call = (...args) => {
  const response = JSON.parse(execFileSync(process.env.FC_AGENT_BROWSER,['--json',...args],{encoding:'utf8',timeout:45000}));
  assert(response.success,response.error); return response.data;
};
const evaluate = source => call('eval','-b',Buffer.from(source).toString('base64')).result;
const settled = () => call('wait','--fn',"!!document.querySelector('.app-shell') && !document.querySelector('[aria-busy=true]') && !document.querySelector('.loading-line')");
const navigate = hash => { evaluate(`location.hash=${JSON.stringify(hash)}`); settled(); };
const click = name => call('find','role','button','click','--name',name,'--exact');
const delay = (path,ms) => assert(evaluate(`fetch('/__test/delay',{method:'POST',body:JSON.stringify(${JSON.stringify({path,ms})})}).then(async r=>r.ok && (await r.json()).syntheticOnly)`));
const checks = [];
const record = (name,detail=true) => { checks.push({name,detail}); writeFileSync(join(run,'browser-page-transitions.json'),JSON.stringify({syntheticOnly:true,checks},null,2)); };
call('open',fixture.ui+'/api/v3/__synthetic_marker');
assert.equal(evaluate('document.body.textContent'),'fc-layout-plans-synthetic-only');
call('set','viewport','1600','1000'); call('open',fixture.ui+'/#/investment/journal');
call('wait','--fn',"!!document.querySelector('input[name=adminToken]') || !!document.querySelector('.app-shell')");
if(evaluate("!!document.querySelector('input[name=adminToken]')")) { call('fill','input[name=adminToken]','synthetic-layout-admin'); click('Enter Finance Core'); }
settled();
if(evaluate("document.querySelector('.workspace-tools select').value") !== fixture.workspaceId) { call('select','.workspace-tools select',fixture.workspaceId); settled(); }
evaluate('window.confirm=()=>true'); navigate('#/investment/journal');

// Sample painted frames through both the read and first lazy-module load, not only after settling.
delay(`/api/v3/workspaces/${fixture.workspaceId}/health`,300); delay('/assets/Data.js',750);
const cold = evaluate(`new Promise(resolve=>{
  const shell=document.querySelector('.app-shell'),main=document.querySelector('main'),header=document.querySelector('.workbench-header'),rail=document.querySelector('.branched-menu');
  const source=performance.timeOrigin,samples=[],start=performance.now();
  [...rail.querySelectorAll('.branched-menu__head')].find(n=>n.textContent==='Import & export').click();
  const frame=()=>{const head=[...rail.querySelectorAll('.branched-menu__head')].find(n=>n.textContent==='Journal');
    samples.push({page:main.dataset.page,panels:main.querySelectorAll('[data-section-title]').length,navOpacity:Number(getComputedStyle(head).opacity),inert:!!main.querySelector('[inert]'),status:!!document.querySelector('.loading-line'),shellConnected:shell.isConnected && main.isConnected && header.isConnected && rail.isConnected,routeAnimations:main.getAnimations({subtree:true}).filter(a=>a.effect?.target?.classList.contains('step-page')).length});
    if(performance.now()-start<1600)requestAnimationFrame(frame);else resolve({samples,sameDocument:source===performance.timeOrigin});};frame();})`);
record('Cold page transition frame evidence',cold);
assert(cold.sameDocument && cold.samples.every(s=>s.shellConnected),'Navigation must retain the document and workbench shell');
assert(cold.samples.every(s=>s.panels>0),'The visible page must not disappear while a destination module loads');
assert(cold.samples.every(s=>s.navOpacity===1),'Read-only navigation must not gray out the entire rail');
assert(cold.samples.every(s=>s.routeAnimations===0),'Switching pages must not replay a whole-page step animation');
assert(cold.samples.some(s=>s.status && s.inert),'Long waits retain accessible feedback and block stale page interactions');
assert.equal(cold.samples.at(-1).page,'data'); record('Cold navigation retains content, shell and rail brightness until the next page is ready');

navigate('#/investment/journal'); evaluate('window.scrollTo({top:100,behavior:"instant"})');
const scroll=evaluate(`new Promise(resolve=>{const before=scrollY;[...document.querySelectorAll('.branched-menu__head')].find(n=>n.textContent==='Securities & positions').click();setTimeout(()=>resolve({before,after:scrollY,max:document.documentElement.scrollHeight-innerHeight}),700)})`);
assert(scroll.before>=90 && Math.abs(scroll.after-Math.min(scroll.before,scroll.max))<2,'A visible page heading does not require a trip back to the document header');
record('Primary page navigation preserves the visible workbench position',scroll);

navigate('#/investment/journal'); delay(`/api/v3/workspaces/${fixture.workspaceId}/health`,450);
const rapid=evaluate(`new Promise(resolve=>{const click=name=>[...document.querySelectorAll('.branched-menu__head')].find(n=>n.textContent===name).click();click('Import & export');setTimeout(()=>click('Cash flow'),70);setTimeout(()=>resolve({page:document.querySelector('main').dataset.page,hash:location.hash}),1200)})`);
assert.equal(rapid.page,'cashflow'); assert(rapid.hash.endsWith('/cashflow'));
record('A later page choice cancels a slower read instead of freezing navigation',rapid);

navigate('#/investment/journal'); delay(`/api/v3/workspaces/${fixture.workspaceId}/health`,450);
const retainedBranch=evaluate(`new Promise(resolve=>{[...document.querySelectorAll('.branched-menu__head')].find(n=>n.textContent==='Import & export').click();setTimeout(()=>[...document.querySelectorAll('.branched-menu__item')].find(n=>n.textContent==='Posted journal').click(),70);setTimeout(()=>resolve({page:document.querySelector('main').dataset.page,active:document.querySelector('.branched-menu__item[aria-current=location]')?.textContent,hash:location.hash}),1200)})`);
assert.equal(retainedBranch.page,'journal'); assert.equal(retainedBranch.active,'Posted journal');
assert(retainedBranch.hash.endsWith('/journal'));
record('Choosing a branch on the retained page cancels the pending destination too',retainedBranch);

// Cancellation must also win after reads finish but before the first module import resolves.
navigate('#/investment/journal'); delay('/assets/PersonalFinance.js',850);
const interrupted=evaluate(`new Promise(resolve=>{const click=name=>[...document.querySelectorAll('.branched-menu__head')].find(n=>n.textContent===name).click();click('Monthly review');setTimeout(()=>click('Statements'),220);setTimeout(()=>resolve({page:document.querySelector('main').dataset.page,hash:location.hash}),1500)})`);
assert.equal(interrupted.page,'statements'); assert(interrupted.hash.endsWith('/statements'));
record('A later page choice also supersedes a pending lazy-module transition',interrupted);

delay('/assets/RecordedBalances.js',850);
evaluate("[...document.querySelectorAll('.segment-entries button')].find(n=>n.textContent==='Living').click()");
call('select','.workspace-tools select',fixture.otherWorkspaceId); settled();
call('wait','--fn',`document.querySelector('.workspace-tools select').value===${JSON.stringify(fixture.otherWorkspaceId)}`);
assert.equal(evaluate("document.querySelector('main').dataset.page"),'overview');
assert(!evaluate("document.querySelector('main').textContent.includes('Synthetic schedule')"));
record('Workspace change clears the old page instead of retaining cross-Workspace content during a lazy transition');
call('select','.workspace-tools select',fixture.workspaceId); settled();

call('set','media','light','reduced-motion'); navigate('#/investment/journal'); click('Statements'); settled();
assert.equal(evaluate("document.querySelector('main').getAnimations({subtree:true}).length"),0);
record('Reduced-motion page navigation has no whole-pane animation'); call('set','media','light');
assert.deepEqual(evaluate('({local:localStorage.length,session:sessionStorage.length})'),{local:0,session:0});
record('Navigation does not cache finance data or credentials in browser storage');
console.log(JSON.stringify({passed:checks.length,receipt:join(run,'browser-page-transitions.json')},null,2));
