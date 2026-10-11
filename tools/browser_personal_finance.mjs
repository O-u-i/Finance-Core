// Synthetic desktop acceptance only. Set an isolated backend and a fresh evidence directory.
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
const root=resolve(process.env.FC_UI_EVIDENCE_DIR || '');
assert(process.env.FC_UI_EVIDENCE_DIR && root.startsWith(resolve('.tmp') + '\\'), 'Use an owned repository-local .tmp evidence directory.');
mkdirSync(root,{recursive:true});
// Keep the owned browser profile with this run; never recursively purge it.
process.env.TEMP=join(root,'chrome-profiles'); process.env.TMP=process.env.TEMP; mkdirSync(process.env.TEMP,{recursive:true});
assert(process.env.ARCHIFY_SKILL_ROOT,'Select the existing approved Archify tooling root.');
const { ChromeVisualBrowser, findChrome }=await import(pathToFileURL(join(process.env.ARCHIFY_SKILL_ROOT,'bin/visual-check.mjs')));
const browser=new ChromeVisualBrowser(findChrome()),session=await browser.sessionPromise;
const send=(method,params={})=>browser.cdp.send(method,params,session);
const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);return result.result.value;};
const wait=async expression=>{for(let count=0;count<150;count++){if(await evaluate(expression))return;await new Promise(resolve=>setTimeout(resolve,100));}throw Error('UI condition timed out: '+expression);};
const settled=()=>wait("!document.querySelector('.loading-line') && !document.querySelector('[aria-busy=true]')");
const fill=(selector,value)=>evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});if(!input)throw Error('Missing field');const proto=input.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:input.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);
const click=(label,scope='')=>evaluate(`(()=>{const root=${scope ? `document.querySelector(${JSON.stringify(scope)})` : 'document'};const button=[...root.querySelectorAll('button')].find(item=> (item.closest('.configuration-nav')? item.querySelector('span').textContent:item.textContent).trim()===${JSON.stringify(label)});if(!button || button.disabled)throw Error('Unavailable: '+${JSON.stringify(label)});button.click();})()`);
const capture=async name=>{await evaluate("document.querySelector('.global-notice button')?.click()");await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');const {data}=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});writeFileSync(join(root,name+'.png'),Buffer.from(data,'base64'));};
const checks=[];
try {
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  const testUrl = process.env.FC_UI_TEST_URL;
  assert(testUrl, 'Explicitly select the owned synthetic UI server.');
  assert.equal(new URL(testUrl).origin, 'http://localhost:5174', 'Use the owned loopback UI fixture only.');
  await send('Page.navigate', {url: testUrl + '/__synthetic_marker'});
  await wait("document.body.textContent === 'fc-ui-account-fixes-synthetic-only'");
  await send('Page.navigate',{url:testUrl+'/#/overview/consolidated/2026-08'});
  await wait("!!document.querySelector('input[name=adminToken]')");
  await fill('input[name=adminToken]','synthetic-browser-admin');await click('Enter Finance Core');
  await wait("document.body.textContent.includes('Financial overview')");await settled();
  if(process.env.FC_UI_TEST_WORKSPACE) {
    await fill('.workspace-tools select',process.env.FC_UI_TEST_WORKSPACE);await settled();
    await evaluate("location.hash='#/overview/consolidated/2026-08'");await settled();
  }
  assert.equal(await evaluate("[...document.querySelectorAll('.configuration-nav button > span')].map(item=>item.textContent).join('|')"),'Overview|Master data|Settings');
  assert.equal(await evaluate("document.querySelector('.configuration-row').getBoundingClientRect().top < document.querySelector('.pill-nav').getBoundingClientRect().top"),true);
  assert.equal(await evaluate("document.body.textContent.includes('5447.5')"),true);
  await capture('overview-1440');checks.push('horizontal global/segment navigation and beneficiary-only consolidated value');

  const generated=await evaluate(`(async()=>{const wid=document.querySelector('.workspace-tools select').value;const prefix='/api/v3/workspaces/'+wid;const report=(await (await fetch(prefix+'/reports/personal-balance-sheet?month=2026-08')).json()).data;const result=await fetch(prefix+'/investment-arrangements/pool-policy/drafts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:'ui-funding',date:'2026-08-20',operation:'funding',amount:'600',partyId:'owner',claimAccountId:'member-owner',cashAccountId:'pool',expectedRevision:report.revision,fromLiving:true,reason:'Synthetic browser funding'})});if(!result.ok)throw Error('Draft generation failed');return result.json();})()`);
  assert.equal(generated.data.status,'draft');
  await click('Journal','.pill-nav');await settled();
  await evaluate("[...document.querySelectorAll('.record-list article')].find(item=>item.textContent.includes('Synthetic browser funding')).querySelector('button').click()");
  await click('Validate draft');await settled();
  await wait("document.body.textContent.includes('Validation passed')");
  await evaluate("document.querySelector('.confirmation input[type=checkbox]').click()");
  await click('Confirm and post');await settled();await wait("document.body.textContent.includes('Entry posted')");
  checks.push('generated generic funding draft requires normal human Validate / Confirm / Post');

  await click('Living','.segment-switcher');await settled();
  assert.equal(await evaluate("[...document.querySelectorAll('.pill-nav button span')].map(item=>item.textContent).join('|')"),'Accounts & balances|Assets & liabilities|Monthly plans|Monthly review|Import & export');
  await fill('input[type=month]','2026-08');await settled();
  await evaluate("document.querySelector('.balance-account > summary').click()");
  await fill('.balance-account input[inputmode=decimal]','400');
  const cancelled=click('Master data','.configuration-nav');cancelled.catch(()=>{});
  await browser.cdp.waitFor('Page.javascriptDialogOpening',session);await send('Page.handleJavaScriptDialog',{accept:false});await cancelled;
  assert.equal(await evaluate('location.hash'),'#/living/balances/2026-08');
  checks.push('dirty form cancels cross-area navigation without discarding the observation');
  await evaluate("(()=>{const form=document.querySelector('.balance-account form');const inputs=form.querySelectorAll('input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(inputs[1],'Synthetic UI statement');inputs[1].dispatchEvent(new Event('input',{bubbles:true}));Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(inputs[2],'Synthetic correction');inputs[2].dispatchEvent(new Event('input',{bubbles:true}));form.querySelector('input[type=checkbox]').click();})()");
  await click('Confirm balance','.balance-account');await settled();
  await click('Monthly review','.pill-nav');await settled();await fill('input[type=month]','2026-08');await settled();
  await fill('input[name=outgoing]','600');await fill('input[name=reason]','Synthetic transfer confirmation');
  await evaluate("document.querySelector('input[name=outgoing]').closest('form').querySelector('input[type=checkbox]').click()");
  await click('Confirm totals');await settled();
  await capture('living-review-1440');checks.push('Living month-end corrections and aggregate transfer reconciliation, no detailed transaction page');

  await click('Overview','.configuration-nav');await settled();await evaluate("location.hash='#/overview/consolidated/2026-08'");await settled();
  assert.equal(await evaluate("document.body.textContent.includes('5447.5')"),true);
  checks.push('personal wealth unchanged by owner funding after confirmed Living balance and transfer totals');
  await click('Living','.segment-switcher');await settled();
  await click('Assets & liabilities','.pill-nav');await settled();
  assert.equal(await evaluate("!!document.querySelector('input[name=purchaseCost]') && !!document.querySelector('input[name=ownershipShare]')"),true);
  await capture('assets-1440');
  await click('Monthly plans','.pill-nav');await settled();
  assert.equal(await evaluate("document.body.textContent.includes('Monthly plans (not actuals)') && !document.querySelector('input[name=balance]')"),true);
  await click('Import & export','.pill-nav');await settled();
  await fill('textarea','subjectId,month,kind,currency,amount,incoming,outgoing,source\ndebt,2026-09,balance,CNY,150,,,Synthetic CSV statement\n');
  await click('Validate preview');await settled();await wait("document.body.textContent.includes('Import pending rows')");
  const imported=click('Import pending rows');imported.catch(()=>{});
  await browser.cdp.waitFor('Page.javascriptDialogOpening',session);await send('Page.handleJavaScriptDialog',{accept:true});await imported;await settled();
  assert.equal(await evaluate("document.body.textContent.includes('Imported pending observations')"),true);
  checks.push('manual asset controls, plans not actuals, and Living CSV preview/import stays pending');
  await click('Master data','.configuration-nav');await settled();await click('Ownership & agreements','.subnav');await settled();await capture('ownership-1440');
  await click('Settings','.configuration-nav');await settled();assert.equal(await evaluate("document.body.textContent.includes('Download unified Vault backup (format 3)')"),true);
  checks.push('generic ownership controls and global complete backup placement');
  await send('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
  await click('Overview','.configuration-nav');await settled();await capture('overview-1920');
  assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'),true);
  const ids=await evaluate(`(async()=>{const previous=document.querySelector('.workspace-tools select').value;const result=await fetch('/api/v3/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({displayName:'Synthetic second Vault',kind:'sandbox'})});if(!result.ok)throw Error('Workspace create failed');return {previous,next:(await result.json()).data.id};})()`);
  // Refresh the owner Workspace list before selecting; no browser finance storage.
  await click('Settings','.configuration-nav');await settled();
  await fill('.workspace-tools select',ids.next);await settled();
  await wait("document.body.textContent.includes('Financial overview')");
  assert.equal(await evaluate("document.body.textContent.includes('5447.5')"),false);
  await fill('.workspace-tools select',ids.previous);await settled();
  checks.push('Workspace switch discards old report values and requests before loading another Vault');
  if(process.env.FC_UI_LEGACY_WORKSPACE) {
    await click('Settings','.configuration-nav');await settled();
    await fill('.workspace-tools select',process.env.FC_UI_LEGACY_WORKSPACE);await settled();
    await wait("document.body.textContent.includes('Schema 2 Vault retained without automatic migration')");
    await click('Investment','.segment-switcher');await settled();
    assert.equal(await evaluate("document.body.textContent.includes('Synthetic opening')"),true);
    await click('Master data','.configuration-nav');await settled();await click('Accounts','.subnav');await settled();
    assert.equal(await evaluate("document.body.textContent.includes('Legacy storage is retained')"),true);
    assert.equal(await evaluate("!!document.querySelector('select[name=segment]')"),true);
    await click('Monthly review','.pill-nav');await settled();
    assert.equal(await evaluate("!!document.querySelector('input[type=month]')"),true);
    await click('Living','.segment-switcher');await settled();
    assert.equal(await evaluate("[...document.querySelectorAll('.pill-nav button span')].map(item=>item.textContent).join('|')"),'Living & plans');
    await click('Settings','.configuration-nav');await settled();
    assert.equal(await evaluate("document.body.textContent.includes('Download legacy backup (format 2)')"),true);
    await capture('legacy-schema2-1920');
    assert.equal(await evaluate(`(async()=>{const id=document.querySelector('.workspace-tools select').value;return (await (await fetch('/api/v3/workspaces/'+id+'/health')).json()).ledgerSchemaVersion;})()`),2);
    checks.push('schema-2 GUI remains usable with legacy ledger/review/Living/backup and no implicit migration');
  }
  writeFileSync(join(root,'receipt.json'),JSON.stringify({syntheticOnly:true,desktopViewports:['1440x1000','1920x1080'],checks,productionMigration:false,humanFinancialAcceptance:false},null,2));
  console.log(JSON.stringify({passed:checks.length,evidenceDir:root}));
} finally {
  // Do not call Archify close(), which recursively removes its temporary profile.
  browser.cdp.failAll(new Error('Synthetic browser verification finished'));
  if(browser.child.exitCode===null) browser.child.kill();
}
