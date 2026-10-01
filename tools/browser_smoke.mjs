// Uses the already-installed Archify Chrome transport; no browser package is installed.
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const { ChromeVisualBrowser, findChrome } = await import(pathToFileURL(join(process.env.ARCHIFY_SKILL_ROOT || join(homedir(), '.codex/skills/archify'), 'bin/visual-check.mjs')));
import { mkdirSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const root = '.tmp/ui-verification'; mkdirSync(root, { recursive: true });
const browser = new ChromeVisualBrowser(findChrome());
const session = await browser.sessionPromise;
const send = (method, params = {}) => browser.cdp.send(method, params, session);
const evaluate = async (expression) => {
  const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result?.value;
};
const wait = async (expression) => {
  for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await new Promise((resolve) => setTimeout(resolve, 100)); }
  throw new Error(`UI condition timed out: ${expression}`);
};
const click = async (text, dialog = false) => {
  const action = evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(b => (b.closest('.configuration-nav') ? b.querySelector(':scope > span').textContent : b.textContent).trim() === ${JSON.stringify(text)}); if (!button || button.disabled) throw new Error('Button unavailable: '+${JSON.stringify(text)}); button.click(); })()`);
  action.catch(() => {});
  if (dialog) { await browser.cdp.waitFor('Page.javascriptDialogOpening', session); await send('Page.handleJavaScriptDialog', { accept: true }); }
  await action;
};
const fill = (selector, value) => evaluate(`(() => { const e=document.querySelector(${JSON.stringify(selector)}); if(!e) throw new Error('Input unavailable'); const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)}); e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true})); })()`);
const route = async (text, dialog = false) => { if (await evaluate(`document.querySelector('.mobile-nav-toggle')?.getClientRects().length > 0 && !document.querySelector('.pill-nav.open') && !![...document.querySelectorAll('.pill-nav button')].find(b=>(b.closest('.configuration-nav') ? b.querySelector(':scope > span').textContent : b.textContent).trim()===${JSON.stringify(text)})`)) await click('Menu +'); await click(text, dialog); await wait(`([...document.querySelectorAll('.pill-nav button.active,.configuration-nav button.active,.subnav button.selected')].some(b=>(b.closest('.configuration-nav') ? b.querySelector(':scope > span').textContent : b.textContent).trim()===${JSON.stringify(text)})) && !document.querySelector('.loading-line')`); await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))'); await wait("!document.querySelector('.loading-line')"); };
const screenshot = async (name) => {
  const { data } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  writeFileSync(`${root}/${name}.png`, Buffer.from(data, 'base64'));
};
const checks = [];
try {
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  await send('Page.navigate', { url: process.env.FC_UI_TEST_URL || 'http://127.0.0.1:5174' });
  await wait("!!document.querySelector('input[name=adminToken]')"); await screenshot('login-1440');
  await fill('input[name=adminToken]', 'synthetic-browser-admin'); await click('Enter Finance Core');
  await wait("!!document.querySelector('input[name=displayName]') || !!document.querySelector('.overview-intro')");
  const settingsCreation = await evaluate("!!document.querySelector('.overview-intro')");
  const workspaceName = 'Browser Sandbox ' + Date.now();
  if (settingsCreation) await route('Settings');
  await fill('input[name=displayName]', workspaceName);
  await evaluate("document.querySelector('select[name=kind]').closest('.select-field').querySelector('button').click()");
  await wait("!!document.querySelector('.glide-menu [role=option]')");
  await evaluate("document.querySelector('.glide-menu [data-index=\"1\"]').click()");
  assert.equal(await evaluate("document.querySelector('select[name=kind]').value"),'sandbox');
  await click('Create workspace');
  if (settingsCreation) {
    await wait("document.body.textContent.includes('Workspace created.') && !document.querySelector('.loading-line')");
    const wid = await evaluate(`[...document.querySelectorAll('.select-native option')].find(o=>o.textContent===${JSON.stringify(workspaceName)})?.value`);
    await fill('.select-native', wid);
  }
  await wait("!!document.querySelector('.setup-panel') && !document.querySelector('.loading-line')");
  assert.equal(await evaluate("[...document.querySelectorAll('.pill-nav button')].every(b=>b.disabled)"),true);
  assert.equal(await evaluate("document.querySelector('.configuration-nav').getBoundingClientRect().top < document.querySelector('.pill-nav').getBoundingClientRect().top"),true);
  checks.push('empty Workspace blocks financial tools and keeps upper configuration navigation available');
  await click('Load synthetic example', true); await wait("document.body.textContent.includes('Synthetic example loaded.') && !document.querySelector('.loading-line')");
  await route('Journal'); await wait("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Review') && !document.querySelector('.loading-line')"); await click('Review');
  await wait("document.querySelector('#journal-editor')?.textContent.includes('Posting 1')");
  // Exercise the actual Journal dropdown, not its hidden native mobile control.
  await evaluate("(()=>{const f=[...document.querySelectorAll('#journal-editor .select-field')].find(e=>e.querySelector('label')?.textContent==='Account');f.querySelector('.select-custom button').click();})()");
  await wait("!!document.querySelector('.glide-menu [role=option]')");
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.glide-menu')).backgroundColor"), 'rgb(39, 39, 42)');
  const originalAccount = await evaluate("document.querySelector('.glide-menu [role=option][aria-selected=true]').textContent.trim()");
  await evaluate("document.querySelector('.glide-menu [role=option][data-index=\"2\"]').click()");
  assert.equal(await evaluate("[...document.querySelectorAll('#journal-editor .select-field')].find(e=>e.querySelector('label')?.textContent==='Account').querySelector('select').value"), 'investment');
  await evaluate("[...document.querySelectorAll('#journal-editor .select-field')].find(e=>e.querySelector('label')?.textContent==='Account').querySelector('button').click()");
  await wait("!!document.querySelector('.glide-menu [role=option]')");
  await evaluate(`[...document.querySelectorAll('.glide-menu [role=option]')].find(e=>e.textContent.trim()===${JSON.stringify(originalAccount.replace(/✓$/, '').trim())}).click()`);
  assert.equal(await evaluate("!!document.querySelector('.glide-menu')"), false);
  checks.push('Journal account uses shared dark glide menu and preserves the selected account');
  await click('Validate draft'); await wait("document.body.textContent.includes('Validation passed') && !document.querySelector('.loading-line')");
  assert.equal(await evaluate("document.querySelector('#journal-editor .postings').getClientRects().length"), 0);
  assert.equal(await evaluate("!!document.querySelector('.review-summary')"), true);
  // Editing must immediately remove the old validation and posting confirmation.
  await click('Edit draft');
  await fill('#journal-editor input[type=date]', '2026-09-29');
  await wait("!document.querySelector('.validation') && !document.querySelector('.confirmation')");
  await click('Validate draft'); await wait("document.body.textContent.includes('Validation passed') && !document.querySelector('.loading-line')");
  await evaluate("document.querySelector('.confirmation input[type=checkbox]').click()");
  await click('Confirm and post'); await wait("document.body.textContent.includes('Entry posted.') && !document.querySelector('.loading-line')");
  assert.equal(await evaluate("!!document.querySelector('.step-result')"), true);
  checks.push('login, sandbox creation, synthetic loading, draft validation invalidation and confirmed posting');
  await route('Securities & positions'); await route('Statements');
  assert.equal(await evaluate("document.querySelector('table')?.textContent.includes('10000')"), true);
  await screenshot('statements-1440'); checks.push('posted statements reflect backend values');
  await route('Journal'); await wait("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Reverse') && !document.querySelector('.loading-line')"); await click('Reverse', true); await wait("document.body.textContent.includes('Linked reversal created.') && !document.querySelector('.loading-line')");
  checks.push('linked reversal retains original entry');
  await route('Import & export'); await route('Import');
  await fill('.panel .select-native','json');
  await fill('textarea', '{broken'); await click('Check structure');
  assert.equal(await evaluate("document.querySelector('.global-notice')?.classList.contains('error')"), true);
  checks.push('malformed import retains input and displays error');
  const invalidDraft = {id:'invalid-browser',date:'2026-09-30',description:'Synthetic invalid account',balancingCommodityCode:'CNY',postings:[{id:'invalid-debit',accountId:'missing-synthetic-account',side:'debit',units:'1.10',commodityCode:'CNY'},{id:'invalid-credit',accountId:'capital',side:'credit',units:'1.10',commodityCode:'CNY'}]};
  const invalidInput = JSON.stringify({drafts:[invalidDraft]});
  await fill('textarea',invalidInput); await click('Check structure');
  await wait("!!document.querySelector('.confirmation')");
  await evaluate("document.querySelector('.confirmation input[type=checkbox]').click()");
  await click('Validate and import');
  await wait("document.querySelector('.global-notice')?.classList.contains('error') && !document.querySelector('.loading-line')");
  assert.equal(await evaluate("document.querySelector('textarea').value"),invalidInput);
  assert.equal(await evaluate("!!document.querySelector('.confirmation')"),true);
  checks.push('backend import validation failure preserves input and confirmation state');
  assert.equal(await evaluate("document.querySelector('textarea').value"), invalidInput);
  const validDraft = structuredClone(invalidDraft); validDraft.id='valid-browser-'+Date.now(); validDraft.postings=validDraft.postings.map((p,i)=>({...p,id:validDraft.id+'-'+i,accountId:i?'capital':'cash'}));
  await click('Edit input');
  await fill('textarea',JSON.stringify({drafts:[validDraft]})); await click('Check structure');
  await evaluate("document.querySelector('.confirmation input[type=checkbox]').click()"); await click('Validate and import');
  await wait("document.body.textContent.includes('Import completed: 1 drafts.') && !document.querySelector('.loading-line')");
  await click('Import another file');
  await fill('.panel .select-native','csv');
  const csvId='csv-browser-'+Date.now();
  const csv='entryId,date,description,balancingCommodityCode,postingId,accountId,side,units,commodityCode\n'+csvId+',2026-09-30,Synthetic CSV,CNY,'+csvId+'-debit,cash,debit,1.10,CNY\n'+csvId+',2026-09-30,Synthetic CSV,CNY,'+csvId+'-credit,capital,credit,1.10,CNY\n';
  await fill('textarea',csv);await click('Check structure');
  await evaluate("document.querySelector('.confirmation input[type=checkbox]').click()");await click('Validate and import');
  await wait("document.body.textContent.includes('Import completed: 1 drafts.') && !document.querySelector('.loading-line')");
  checks.push('JSON and CSV imports create validated unposted drafts');
  await route('Overview');
  // Delay target reads and record every frame: the current ledger stays visible until the target is ready.
  await send('Network.enable');
  await send('Network.emulateNetworkConditions',{offline:false,latency:250,downloadThroughput:-1,uploadThroughput:-1});
  await evaluate(`(()=>{window.__frames=[];window.__record=true;const frame=()=>{if(!window.__record)return;window.__frames.push({page:document.querySelector('.pill-nav button.active')?.textContent,stats:!!document.querySelector('.stats'),loading:!!document.querySelector('.loading-line')});requestAnimationFrame(frame)};requestAnimationFrame(frame)})()`);
  await route('Securities & positions');
  const frames = await evaluate("(()=>{window.__record=false;return window.__frames})()");
  await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  assert.ok(frames.some(f=>f.page==='Overview' && f.loading));
  assert.ok(frames.filter(f=>f.page==='Overview').every(f=>f.stats), 'Current page must not blank during delayed navigation');
  await route('Overview');
  checks.push('delayed page navigation keeps prior records visible and commits target content atomically');
  await send('Network.emulateNetworkConditions',{offline:false,latency:250,downloadThroughput:-1,uploadThroughput:-1});
  await click('Securities & positions'); await click('Master data');
  await wait("document.querySelector('.configuration-nav button.active span')?.textContent==='Master data' && !document.querySelector('.loading-line')");
  await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  assert.equal(await evaluate("document.querySelector('.panel h2')?.textContent"), 'Commodity registry');
  await route('Overview'); checks.push('rapid page changes discard superseded target reads');
  await evaluate('history.back()');
  await wait("document.querySelector('.configuration-nav button.active span')?.textContent==='Master data' && !document.querySelector('.loading-line')");
  await evaluate('history.forward()');
  await wait("document.querySelector('.pill-nav button.active')?.textContent==='Overview' && !document.querySelector('.loading-line')");
  checks.push('hash history back and forward retain correct page data');
  assert.equal(await evaluate("!!document.querySelector('.global-notice')"), false);
  assert.equal(await evaluate('scrollY'), 0);
  const contrast = (left,right) => {
    const luminance=(hex)=>{const channels=hex.replace('#','').match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4);return channels[0]*0.2126+channels[1]*0.7152+channels[2]*0.0722;};
    const a=luminance(left),b=luminance(right);return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
  };
  const palette=await evaluate("(()=>{const s=getComputedStyle(document.documentElement);return Object.fromEntries(['paper','ink','accent','muted','error'].map(k=>[k,s.getPropertyValue('--'+k).trim()]));})()");
  for (const [text,surface] of [[palette.ink,palette.paper],[palette.muted,palette.paper],[palette.accent,'#FFFFFF'],[palette.error,'#FFFFFF']]) assert.ok(contrast(text,surface)>=4.5);
  checks.push('primary, muted, action and error text contrast exceeds 4.5:1');
  for (const width of [320, 375, 768, 1024, 1440]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: width < 600 ? 900 : 1000, deviceScaleFactor: 1, mobile: false });
    await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
    const metrics = await evaluate('({viewport:innerWidth,width:document.documentElement.scrollWidth})');
    assert.ok(metrics.width <= width, `Horizontal overflow at ${width}: ${metrics.width}`);
    await screenshot(`overview-${width}`); checks.push(`overview containment ${width}px`);
  }
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await route('Master data'); await screenshot('master-1440');
  await route('Living & plans'); await screenshot('planning-1440');
  await route('Settings'); await screenshot('settings-1440');
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
  assert.equal(await evaluate("document.activeElement !== document.body"), true); checks.push('keyboard focus and reduced-motion path');
  // The backup is exported through the UI's same-origin, scoped API and restored through its file control.
  const backup = await evaluate(`(async()=>{const wid=document.querySelector('.select-native').value;const response=await fetch('/api/v3/workspaces/'+wid+'/backup');if(!response.ok)throw new Error('Backup export failed');return response.json();})()`);
  const backupFile = resolve(root, 'synthetic-backup.json');
  writeFileSync(backupFile, JSON.stringify(backup));
  const restoredName = 'Browser Restore ' + Date.now();
  await fill('input[name=displayName]', restoredName); await fill('select[name=kind]', 'sandbox'); await click('Create workspace');
  await wait("document.body.textContent.includes('Workspace created.') && !document.querySelector('.loading-line')");
  const restoredWid = await evaluate(`[...document.querySelectorAll('.select-native option')].find(o=>o.textContent===${JSON.stringify(restoredName)})?.value`);
  await fill('.select-native', restoredWid);
  await wait("!!document.querySelector('.setup-panel') && !document.querySelector('.loading-line')");
  await route('Settings');
  const dom = await send('DOM.getDocument');
  const fileNode = await send('DOM.querySelector', { nodeId: dom.root.nodeId, selector: 'input[type=file]' });
  await send('DOM.setFileInputFiles', { nodeId: fileNode.nodeId, files: [backupFile] });
  await wait("document.body.textContent.includes('Selected: synthetic-backup.json')");
  await click('Validate and restore', true);
  await wait("document.body.textContent.includes('Backup validated and restored.') && !document.querySelector('.loading-line')");
  await route('Overview');
  assert.equal(await evaluate("document.querySelector('.stats article:nth-child(2) strong').textContent"), '2');
  await click('Undo latest operation');
  await wait("document.body.textContent.includes('Latest operation undone.') && !document.querySelector('.loading-line')");
  assert.equal(await evaluate("!!document.querySelector('.setup-panel')"), true);
  await click('Load synthetic example',true); await wait("document.body.textContent.includes('Synthetic example loaded.') && !document.querySelector('.loading-line')");
  checks.push('SHA-256 backup file restore into empty sandbox and ledger undo');
  await route('Settings');
  const rowButton = async (label, dialog = false) => {
    const action = evaluate(`(()=>{const row=[...document.querySelectorAll('tr')].find(r=>r.firstElementChild?.textContent===${JSON.stringify(restoredName)});const button=[...row.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)});if(!button||button.disabled)throw new Error('Workspace action unavailable');button.click();})()`);
    action.catch(()=>{});
    if(dialog){await browser.cdp.waitFor('Page.javascriptDialogOpening',session);await send('Page.handleJavaScriptDialog',{accept:true});}
    await action;
  };
  await rowButton('Archive');
  await wait("document.body.textContent.includes('Archived workspace · records are read-only') && !document.querySelector('.loading-line')");
  await route('Journal');
  assert.equal(await evaluate("document.querySelector('#journal-editor fieldset').disabled"), true);
  await route('Settings'); await rowButton('Restore');
  await wait("document.body.textContent.includes('Workspace status updated.') && !document.querySelector('.loading-line')");
  await rowButton('Quarantine', true);
  await wait("document.body.textContent.includes('Vault quarantined.') && !document.querySelector('.loading-line')");
  await route('Settings'); await click('Undo workspace operation');
  await wait("document.body.textContent.includes('Workspace operation undone.') && !document.querySelector('.loading-line')");
  assert.equal(await evaluate(`[...document.querySelectorAll('tr')].find(r=>r.firstElementChild?.textContent===${JSON.stringify(restoredName)})?.textContent.includes('active')`), true);
  checks.push('archive read-only, restore, reversible quarantine and control undo');
  await fill('input[name=name]', 'Synthetic browser token'); await click('Create token');
  await wait("!!document.querySelector('.token-once') && !document.querySelector('.loading-line')");
  await route('Overview'); await route('Settings');
  assert.equal(await evaluate("!!document.querySelector('.token-once')"), false);
  checks.push('one-time token cleared on navigation');
  for (const page of ['Journal', 'T-accounts', 'Securities & positions', 'Cash flow', 'Statements', 'Living & plans', 'Import & export', 'Master data', 'Settings']) {
    await route(page);
    for (const width of [320,375,768,1024,1440]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
      await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'), `${page} overflow at ${width}`);
      await screenshot(`${page.toLowerCase().replaceAll(/[^a-z]+/g,'-')}-${width}`);
    }
  }
  checks.push('all ten pages contained at 320, 375, 768, 1024 and 1440px');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate("document.querySelector('.select-custom>button').focus()");
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40});
  await wait("document.activeElement?.getAttribute('role')==='listbox'");
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  assert.equal(await evaluate("document.activeElement?.getAttribute('aria-haspopup')"),'listbox');
  assert.equal(await evaluate("getComputedStyle(document.activeElement).outlineStyle !== 'none'"),true);
  assert.equal(await evaluate("matchMedia('(prefers-reduced-motion:reduce)').matches"),true);
  checks.push('custom select keyboard opening, Escape focus restoration and visible focus');
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
  await route('Journal');
  await click('Review'); await click('Validate draft');
  await wait("!!document.querySelector('.review-summary') && !document.querySelector('.loading-line')");
  await evaluate("document.querySelector('[aria-label=\"Dismiss notification\"]').click();document.querySelector('.stepper').scrollIntoView({block:'start'})");
  await evaluate('new Promise(r=>setTimeout(r,350))'); await screenshot('journal-confirm-motion-1440');
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.step-content')).transitionDuration"), '0.22s');
  await click('Edit draft');
  await evaluate("[...document.querySelectorAll('#journal-editor .select-field')].find(e=>e.querySelector('label')?.textContent==='Account').querySelector('button').click()");
  await wait("!!document.querySelector('.glide-menu [role=option]')");
  await evaluate("document.querySelector('.glide-menu [data-index=\"3\"]').dispatchEvent(new PointerEvent('pointermove',{bubbles:true}))");
  await evaluate('new Promise(r=>setTimeout(r,250))'); await screenshot('journal-glide-motion-1440');
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.select-highlight')).transitionDuration.split(',')[0]"), '0.22s');
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await fill('#journal-editor input[type=date]', '2026-09-28');
  await send('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await click('Securities & positions', true);
  await wait("document.querySelector('.global-notice')?.classList.contains('error') && document.querySelector('.pill-nav button.active')?.textContent==='Journal' && !document.querySelector('.loading-line')");
  assert.equal(await evaluate("document.querySelector('#journal-editor input[type=date]').value"), '2026-09-28');
  await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  const cancelNavigation = evaluate("[...document.querySelectorAll('.configuration-nav button')].find(e=>e.querySelector('span')?.textContent==='Master data').click()");
  cancelNavigation.catch(()=>{});
  await browser.cdp.waitFor('Page.javascriptDialogOpening',session); await send('Page.handleJavaScriptDialog',{accept:false}); await cancelNavigation;
  assert.equal(await evaluate("document.querySelector('.pill-nav button.active')?.textContent"), 'Journal');
  await route('Master data',true);
  checks.push('failed navigation retains input and unsaved-change protection; cancellation stays on current page');
  await route('Import & export'); await route('Atomic batch'); await fill('textarea','{"drafts":[]}');
  await route('Import', true); await route('Atomic batch');
  assert.equal(await evaluate("document.querySelector('textarea').value"), '');
  checks.push('normal-motion step pages and glide highlight; confirmed tab discard resets form');
  // Hover and selection share one navigation surface; there is no hover fill layer.
  const targetButton = await evaluate("(()=>{const e=[...document.querySelectorAll('.pill-nav button')].find(e=>e.textContent==='Securities & positions');const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',...targetButton}); await evaluate('new Promise(r=>setTimeout(r,80))');
  await route('Securities & positions');
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.pill-nav button.active'),'::before').content"),'none');
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.pill-nav')).borderRadius"),'12px');
  await route('Statements');
  await evaluate('new Promise(r=>setTimeout(r,260))');
  const geometry = await evaluate("({top:document.querySelector('.panel').getBoundingClientRect().top,toolbar:document.querySelector('.report-context').getBoundingClientRect().height})");
  await route('Cash flow');
  await evaluate('new Promise(r=>setTimeout(r,260))');
  assert.ok(Math.abs(await evaluate("document.querySelector('.panel').getBoundingClientRect().top")-geometry.top)<.5);
  assert.equal(geometry.toolbar,104);
  await route('Overview'); await screenshot('refined-navigation-1440');
  checks.push('hover-click uses one fill layer; rectangular navigation and equal sub-tab panel origins');
  if (process.env.FC_TEST_ACCOUNTING_CSV) {
    // This optional file must contain only the explicitly sanitized synthetic derivative.
    await route('Settings'); const mappingName=await evaluate("[...document.querySelectorAll('.workspace-tools select option')].some(o=>o.textContent==='journal-test') ? 'journal-test '+Date.now() : 'journal-test'");
    await fill('input[name=displayName]',mappingName); await fill('select[name=kind]','sandbox'); await click('Create workspace');
    await wait("document.body.textContent.includes('Workspace created.') && !document.querySelector('.loading-line')");
    const mappingWid=await evaluate(`[...document.querySelectorAll('.workspace-tools select option')].find(o=>o.textContent===${JSON.stringify(mappingName)})?.value`);
    await fill('.workspace-tools select',mappingWid); await wait("!!document.querySelector('.setup-panel') && !document.querySelector('.loading-line')");
    await evaluate(`(async()=>{const wid=document.querySelector('.workspace-tools select').value;const r=await fetch('/api/v3/workspaces/'+wid+'/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({commodities:['CNY','MYR'].map(code=>({code,name:'Synthetic currency '+code,kind:'currency',scale:2,status:'active'})),accounts:Array.from({length:5},(_,i)=>({id:'csv-account-'+i,code:String(9001+i),name:['Synthetic cash','Synthetic receivable','Synthetic capital','Synthetic income','Synthetic expense'][i],type:['asset','asset','equity','income','expense'][i],subtype:i===0?'cash':'',allowedCommodityCodes:['CNY','MYR'],status:'active'}))})});if(!r.ok)throw new Error('Synthetic mapping seed failed')})()`);
    await click('Check configuration'); await wait("!!document.querySelector('.overview-intro') && !document.querySelector('.loading-line')");
    await route('Import & export'); await route('Import'); await fill('.panel .select-native','csv');
    const tree=await send('DOM.getDocument'); const node=await send('DOM.querySelector',{nodeId:tree.root.nodeId,selector:'input[type=file]'});
    await send('DOM.setFileInputFiles',{nodeId:node.nodeId,files:[resolve(process.env.FC_TEST_ACCOUNTING_CSV)]});
    await wait("document.querySelector('textarea').value.includes('父记录')");
    await click('Check structure'); await wait("!!document.querySelector('.csv-mapping')");
    assert.equal(await evaluate("!!document.querySelector('.confirmation')"),false);
    await evaluate("document.querySelector('.csv-mapping input[type=checkbox]').click()");
    await click('Check structure'); await wait("!!document.querySelector('.confirmation')");
    assert.equal(await evaluate("document.querySelector('.confirmation tbody').children.length"),24);
    await evaluate('new Promise(r=>setTimeout(r,280))'); await screenshot('accounting-mapping-preview-synthetic');
    for (const width of [320,375,768,1024,1440]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
      await evaluate('new Promise(r=>setTimeout(r,280))');
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),`Accounting preview overflow at ${width}`);
      if(width===375) await screenshot('accounting-preview-synthetic-375');
    }
    await evaluate("document.querySelector('.confirmation input[type=checkbox]').click()");
    await click('Validate and import'); await wait("document.body.textContent.includes('Import completed: 24 drafts.') && !document.querySelector('.loading-line')");
    const imported=await evaluate(`(async()=>{const wid=document.querySelector('.workspace-tools select').value;return (await (await fetch('/api/v3/workspaces/'+wid+'/journal-entry-drafts')).json()).data.filter(item=>item.draft.source==='accounting-csv')})()`);
    assert.equal(imported.length,24); assert.ok(imported.every(item=>item.draft.postings.every(p=>typeof p.units==='string' && ['1.10','1.1'].includes(p.units))));
    checks.push('48-row synthetic accounting template maps to 24 backend-validated unposted drafts with unchanged decimal values');
  }
  await click('Sign out'); await wait("!!document.querySelector('input[name=adminToken]')");
  assert.equal(await evaluate("document.body.textContent.includes('Browser Sandbox')"), false); checks.push('sign out removes workspace data');
  writeFileSync(`${root}/receipt.json`, JSON.stringify({ status: 'pass', checks }, null, 2));
  console.log(JSON.stringify({ status: 'pass', checks }));
} catch (error) {
  await screenshot('failure');
  console.log(await evaluate("({headings:[...document.querySelectorAll('h1,h2')].map(e=>e.textContent),notice:document.querySelector('.global-notice')?.textContent})"));
  throw error;
} finally {
  // Retain the ignored profile; never recursively purge a directory.
  try { await browser.cdp.send('Browser.close'); } catch {}
  browser.child.kill();
}
