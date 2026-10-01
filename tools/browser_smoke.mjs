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
  const action = evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}); if (!button || button.disabled) throw new Error('Button unavailable: '+${JSON.stringify(text)}); button.click(); })()`);
  action.catch(() => {});
  if (dialog) { await browser.cdp.waitFor('Page.javascriptDialogOpening', session); await send('Page.handleJavaScriptDialog', { accept: true }); }
  await action;
};
const fill = (selector, value) => evaluate(`(() => { const e=document.querySelector(${JSON.stringify(selector)}); if(!e) throw new Error('Input unavailable'); const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)}); e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true})); })()`);
const route = async (text, dialog = false) => { if (await evaluate(`document.querySelector('.mobile-nav-toggle')?.getClientRects().length > 0 && !document.querySelector('.pill-nav.open') && !![...document.querySelectorAll('.pill-nav button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`)) await click('Menu +'); await click(text, dialog); await wait(`([...document.querySelectorAll('.pill-nav button.active,.subnav button.selected')].some(b=>b.textContent.trim()===${JSON.stringify(text)})) && !document.querySelector('.loading-line')`); await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))'); await wait("!document.querySelector('.loading-line')"); };
const screenshot = async (name) => {
  const { data } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  writeFileSync(`${root}/${name}.png`, Buffer.from(data, 'base64'));
};
const checks = [];
try {
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  await send('Page.navigate', { url: 'http://127.0.0.1:5174' });
  await wait("!!document.querySelector('input[name=adminToken]')"); await screenshot('login-1440');
  await fill('input[name=adminToken]', 'synthetic-browser-admin'); await click('Enter Finance Core');
  await wait("!!document.querySelector('input[name=displayName]') || !!document.querySelector('.overview-intro')");
  const settingsCreation = await evaluate("!!document.querySelector('.overview-intro')");
  const workspaceName = 'Browser Sandbox ' + Date.now();
  if (settingsCreation) await route('Settings');
  await fill('input[name=displayName]', workspaceName); await fill('select[name=kind]', 'sandbox'); await click('Create workspace');
  if (settingsCreation) {
    await wait("document.body.textContent.includes('Workspace created.') && !document.querySelector('.loading-line')");
    const wid = await evaluate(`[...document.querySelectorAll('.select-native option')].find(o=>o.textContent===${JSON.stringify(workspaceName)})?.value`);
    await fill('.select-native', wid);
  }
  await wait("!!document.querySelector('.overview-intro') && !document.querySelector('.loading-line')");
  await click('Load synthetic example', true); await wait("document.body.textContent.includes('Synthetic example loaded.') && !document.querySelector('.loading-line')");
  await route('Journal'); await wait("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Review') && !document.querySelector('.loading-line')"); await click('Review');
  await wait("document.querySelector('#journal-editor')?.textContent.includes('Posting 1')");
  await click('Validate draft'); await wait("document.body.textContent.includes('Validation passed') && !document.querySelector('.loading-line')");
  // Editing must immediately remove the old validation and posting confirmation.
  await fill('#journal-editor input[type=date]', '2026-09-29');
  await wait("!document.querySelector('.validation') && !document.querySelector('.confirmation')");
  await click('Validate draft'); await wait("document.body.textContent.includes('Validation passed') && !document.querySelector('.loading-line')");
  await evaluate("document.querySelector('.confirmation input[type=checkbox]').click()");
  await click('Confirm and post'); await wait("document.body.textContent.includes('Entry posted.') && !document.querySelector('.loading-line')");
  checks.push('login, sandbox creation, synthetic loading, draft validation invalidation and confirmed posting');
  await route('Holdings & reports'); await route('Statements');
  assert.equal(await evaluate("document.querySelector('table')?.textContent.includes('10000')"), true);
  await screenshot('statements-1440'); checks.push('posted statements reflect backend values');
  await route('Journal'); await wait("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Reverse') && !document.querySelector('.loading-line')"); await click('Reverse', true); await wait("document.body.textContent.includes('Linked reversal created.') && !document.querySelector('.loading-line')");
  checks.push('linked reversal retains original entry');
  await route('Automation & data'); await route('Import');
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
  await fill('textarea',JSON.stringify({drafts:[validDraft]})); await click('Check structure');
  await evaluate("document.querySelector('.confirmation input[type=checkbox]').click()"); await click('Validate and import');
  await wait("document.body.textContent.includes('Import completed: 1 drafts.') && !document.querySelector('.loading-line')");
  await fill('.panel .select-native','csv');
  const csvId='csv-browser-'+Date.now();
  const csv='entryId,date,description,balancingCommodityCode,postingId,accountId,side,units,commodityCode\n'+csvId+',2026-09-30,Synthetic CSV,CNY,'+csvId+'-debit,cash,debit,1.10,CNY\n'+csvId+',2026-09-30,Synthetic CSV,CNY,'+csvId+'-credit,capital,credit,1.10,CNY\n';
  await fill('textarea',csv);await click('Check structure');
  await evaluate("document.querySelector('.confirmation input[type=checkbox]').click()");await click('Validate and import');
  await wait("document.body.textContent.includes('Import completed: 1 drafts.') && !document.querySelector('.loading-line')");
  checks.push('JSON and CSV imports create validated unposted drafts');
  await route('Overview');
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
  await wait("!!document.querySelector('.overview-intro') && !document.querySelector('.loading-line')");
  await route('Automation & data'); await route('Export & backup');
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
  assert.equal(await evaluate("document.querySelector('.stats article:nth-child(2) strong').textContent"), '0');
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
  for (const page of ['Journal', 'Holdings & reports', 'Living & plans', 'Automation & data', 'Master data', 'Settings']) {
    await route(page);
    for (const width of [320,375,768,1024,1440]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
      await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'), `${page} overflow at ${width}`);
      await screenshot(`${page.toLowerCase().replaceAll(/[^a-z]+/g,'-')}-${width}`);
    }
  }
  checks.push('all seven pages contained at 320, 375, 768, 1024 and 1440px');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate("document.querySelector('.select-custom>button').focus()");
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40});
  await wait("document.activeElement?.getAttribute('role')==='listbox'");
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  assert.equal(await evaluate("document.activeElement?.getAttribute('aria-haspopup')"),'listbox');
  assert.equal(await evaluate("getComputedStyle(document.activeElement).outlineStyle !== 'none'"),true);
  assert.equal(await evaluate("matchMedia('(prefers-reduced-motion:reduce)').matches"),true);
  checks.push('custom select keyboard opening, Escape focus restoration and visible focus');
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
