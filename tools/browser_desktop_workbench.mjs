// Isolated synthetic HTTP fixture only. Never attach to a user's browser or Vault.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';

const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + sep));
const fixture = JSON.parse(readFileSync(join(run, 'fixture.json'), 'utf8'));
assert.equal(fixture.syntheticOnly, true);
assert.equal(fixture.api, 'http://127.0.0.1:8791');
assert.equal(fixture.ui, 'http://localhost:5174');
assert(process.env.FC_AGENT_BROWSER && process.env.AGENT_BROWSER_SESSION && process.env.AGENT_BROWSER_NAMESPACE);
const call = (...args) => {
  const result = JSON.parse(execFileSync(process.env.FC_AGENT_BROWSER, ['--json', ...args], { encoding: 'utf8', timeout: 45000 }));
  assert.equal(result.success, true, result.error || 'Browser operation failed');
  return result.data;
};
const evaluate = source => call('eval', '-b', Buffer.from(source).toString('base64')).result;
const wait = source => call('wait', '--fn', source);
const settled = () => wait("!!document.querySelector('.app-shell') && !document.querySelector('[aria-busy=true]') && !document.querySelector('.loading-line')");
const navigate = hash => {
  evaluate(`location.hash=${JSON.stringify(hash)}`);
  wait(`location.hash===${JSON.stringify(hash)}`); settled();
  wait("[...document.querySelectorAll('.step-content')].every(node=>Math.abs(node.getBoundingClientRect().height-node.firstElementChild.getBoundingClientRect().height)<2)");
};
const click = label => call('find', 'role', 'button', 'click', '--name', label, '--exact');
const capture = name => { evaluate('window.scrollTo(0,0);document.activeElement?.blur()'); call('screenshot', join(run, name + '.png'), '--full'); };
const checks = [];

call('open', fixture.ui + '/api/v3/__synthetic_marker');
assert.equal(evaluate('document.body.textContent'), 'fc-desktop-workbench-synthetic-only');
call('set', 'viewport', '1440', '1000');
call('open', fixture.ui + '/#/overview/consolidated/2026-09');
wait("!!document.querySelector('input[name=adminToken]') || !!document.querySelector('.app-shell')");
if (evaluate("!!document.querySelector('input[name=adminToken]')")) {
  assert.equal(evaluate("document.querySelector('.auth-layout .brand img').getAttribute('alt')"), 'FINCR');
  capture('login-1440');
  call('fill', 'input[name=adminToken]', 'synthetic-workbench-admin'); click('Enter Finance Core');
}
settled();
if (evaluate("document.querySelector('.workspace-tools select').value") !== fixture.workspaceId) call('select', '.workspace-tools select', fixture.workspaceId);
settled();
if (evaluate("!!document.querySelector('[aria-label=\"Dismiss notification\"]')")) click('Dismiss notification');

const contrastChecks = () => evaluate(`(()=>{
  const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const context=canvas.getContext('2d',{willReadFrequently:true});
  const rgba=color=>{context.clearRect(0,0,1,1);context.fillStyle=color;context.fillRect(0,0,1,1);return [...context.getImageData(0,0,1,1).data];};
  const luminance=rgb=>rgb.slice(0,3).map(c=>c/255).map(c=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4).reduce((n,c,i)=>n+c*[.2126,.7152,.0722][i],0);
  const background=node=>{for(let ancestor=node;ancestor;ancestor=ancestor.parentElement){const color=rgba(getComputedStyle(ancestor).backgroundColor);if(color[3]===255)return color;}return [255,255,255,255];};
  return [...document.querySelectorAll('.record-identity h3,.record-meta,.record-amount,.record-currency,.record-status,.t-account-identity,.t-account-currency,.t-account-dates,.t-account-sides strong,.t-account-balance strong,.line-sidebar__label,.workbench-footer,.sort-direction,.primary')].filter(node=>node.getClientRects().length&&!node.closest(':disabled')).map(node=>{const style=getComputedStyle(node),fg=luminance(rgba(style.color)),bg=luminance(background(node));return {selector:node.className||node.tagName,color:style.color,ratio:(Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05)};});})()`);

for (const width of [1440, 1600]) {
  call('set', 'viewport', String(width), '1000');
  for (const [name, hash] of [
    ['overview', '#/overview/consolidated/2026-09'], ['journal', '#/investment/journal'],
    ['taccounts', '#/investment/taccounts'], ['living-balances', '#/living/balances'],
    ['living-assets', '#/living/assets/2026-09'], ['subnav', '#/master/accounts'],
  ]) {
    navigate(hash);
    const geometry = evaluate(`(()=>{
      const box=selector=>{const node=document.querySelector(selector);if(!node)return null;const rect=node.getBoundingClientRect();return {x:rect.x,y:rect.y,width:rect.width,height:rect.height};};
      const rows=[...document.querySelectorAll('.workbench-record')];
      return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,shell:box('.app-shell'),logo:box('.workbench-logo'),rail:box('.workbench-rail'),
        segment:getComputedStyle(document.querySelector('main')).backgroundColor,navTop:getComputedStyle(document.querySelector('.workbench-nav')).top,
        columns:document.querySelector('.t-account-grid')?getComputedStyle(document.querySelector('.t-account-grid')).gridTemplateColumns.split(' ').length:null,
        rows:rows.map(row=>({height:row.getBoundingClientRect().height,overlap:[...row.children].slice(0,-1).some((node,index)=>node.getBoundingClientRect().right>row.children[index+1].getBoundingClientRect().left+1)})),
        subnav:box('.subnav')};})()`);
    assert.equal(geometry.scrollWidth, width, `${name}: no document overflow`);
    assert(Math.abs(geometry.shell.width - Math.min(width - 48, 1480)) <= 1);
    assert(Math.abs(geometry.logo.x + geometry.logo.width / 2 - width / 2) <= 1, 'FINCR centered on viewport');
    assert.equal(geometry.navTop, '0px');
    if (geometry.rail) assert.equal(geometry.rail.width, 232);
    assert(geometry.rows.every(row => !row.overlap), `${name}: no record overlap`);
    if (name === 'taccounts') { assert.equal(geometry.columns, 4); assert(evaluate("document.querySelectorAll('.t-account-card').length>=4")); }
    if (name.startsWith('living-')) assert.equal(geometry.segment, 'rgb(240, 245, 238)');
    if (name === 'journal' || name === 'taccounts') assert.equal(geometry.segment, 'rgb(238, 243, 247)');
    if (geometry.subnav) assert(geometry.subnav.height <= 40, 'Compact page subnav');
    const contrasts = contrastChecks();
    assert(contrasts.every(item => item.ratio >= 4.5), `${name}: text/amount contrast below 4.5:1: ${JSON.stringify(contrasts.filter(item=>item.ratio<4.5))}`);
    assert(!evaluate("/Owner session|Finance you can trace|Local first · Deterministic|Restored from this browser/.test(document.body.innerText)"));
    capture(`${name}-${width}`); checks.push({ name, ...geometry, minimumTextContrast:Math.min(...contrasts.map(item=>item.ratio)) });
  }
}

navigate('#/investment/taccounts');
call('click','.line-sidebar__item [aria-current=page]');
assert(evaluate("document.querySelector('.line-sidebar__item [aria-current=page]').textContent.includes('T-accounts')"));
evaluate('window.scrollTo(0,200)');
assert.equal(evaluate("document.querySelector('.workbench-nav').getBoundingClientRect().top"),0);
evaluate('window.scrollTo(0,0)');
call('click', '.t-account-card'); wait("!!document.querySelector('dialog[open] tbody tr')");
assert.deepEqual(evaluate("[...document.querySelectorAll('dialog th')].map(node=>node.textContent)"), ['Posting date', 'Debit', 'Credit']);
assert(!evaluate("/Description|postedAt|timestamp/.test(document.querySelector('dialog').innerText)"));
assert(evaluate("document.querySelector('dialog').innerText.includes('2026-09-01')"));
capture('taccount-details-1600'); call('press', 'Escape'); wait("!document.querySelector('dialog[open]')");
assert(evaluate("document.activeElement.classList.contains('t-account-card')"));
call('hover', '.t-accounts-panel .help-trigger'); wait("!!document.querySelector('[role=tooltip]')");
assert(evaluate("document.querySelector('[role=tooltip]').innerText.includes('Asset and expense')"));
const tooltip = evaluate("(()=>{const rect=document.querySelector('[role=tooltip]').getBoundingClientRect();return {left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom,width:innerWidth,height:innerHeight};})()");
assert(tooltip.left>=0 && tooltip.right<=tooltip.width && tooltip.top>=0 && tooltip.bottom<=tooltip.height);
capture('tooltip-1600'); call('hover', '.workbench-logo'); wait("!document.querySelector('[role=tooltip]')");
call('set','viewport','1440','1000');call('hover','.t-accounts-panel .help-trigger');wait("!!document.querySelector('[role=tooltip]')");capture('tooltip-1440');call('hover','.workbench-logo');
call('set','viewport','1600','1000');
checks.push({ name:'T-account detail read, immutable entry dates, focus restore, hover-only tooltip', passed:true });

navigate('#/living/assets/2026-09');
call('click', '.asset-record .record-actions button'); wait("!!document.querySelector('dialog[open]')");
assert(evaluate("document.querySelector('dialog').innerText.includes('Synthetic registry note')"));
capture('asset-secondary-details'); call('press', 'Escape');
call('find', 'role', 'button', 'click', '--name', 'Edit valuation', '--exact'); wait("!!document.querySelector('dialog form')");
assert(evaluate("document.querySelector('dialog').innerText.includes('Save valuation')"));
call('fill', 'dialog input[name=amount]', '7600.01');
assert(!evaluate("document.querySelector('dialog input[type=checkbox]').checked"));
call('fill', 'dialog input[name=reason]', 'Synthetic correction');
call('check', 'dialog input[type=checkbox]'); click('Save valuation'); settled();
assert(evaluate("document.querySelector('dialog [role=status]').innerText.includes('Valuation saved')"));
capture('asset-valuation-saved'); call('press', 'Escape'); wait("!document.querySelector('dialog[open]')");
assert(evaluate("[...document.querySelectorAll('.asset-record')].some(row=>row.innerText.includes('7600.01'))"));
call('find','role','button','click','--name','Edit valuation','--exact');wait("!!document.querySelector('dialog form')");
call('fill','dialog input[name=amount]','7600.02');
// Browser-confirm rejection must keep the dirty dialog mounted and visible.
evaluate("window.__originalConfirm=window.confirm;window.confirm=()=>false");
call('press','Escape');assert(evaluate("!!document.querySelector('dialog[open]')"));
evaluate('window.confirm=()=>true');call('press','Escape');wait("!document.querySelector('dialog[open]')");
evaluate('window.confirm=window.__originalConfirm;delete window.__originalConfirm');
checks.push({name:'Asset Note retained in details; backend valuation correction and renewed confirmation',passed:true});

navigate('#/investment/journal'); click('New draft'); wait("!!document.querySelector('#journal-editor')");
assert(evaluate("document.querySelector('dialog .brand')===null"));
capture('journal-editor-dialog'); call('press','Escape'); wait("!document.querySelector('dialog[open]')");

// Hold a real scoped detail response, then switch Vaults before publishing it.
navigate('#/investment/taccounts');
evaluate(`window.__originalJson=Response.prototype.json;Response.prototype.json=async function(){const payload=await window.__originalJson.call(this);if(this.url.includes('/postings?'))return new Promise(resolve=>{window.__releaseDetail=()=>resolve(payload);});return payload;};`);
call('click','.t-account-card');wait('typeof window.__releaseDetail === "function"');call('press','Escape');
call('select', '.workspace-tools select', fixture.otherWorkspaceId); settled();
evaluate('window.__releaseDetail();Response.prototype.json=window.__originalJson;delete window.__originalJson;delete window.__releaseDetail');
assert.equal(evaluate("document.querySelectorAll('.t-account-card,.workbench-record,dialog[open]').length"),0);
call('select', '.workspace-tools select', fixture.workspaceId); settled();
checks.push({name:'Workspace switch clears old details and records',passed:true});

for (const [width, expected] of [[1250,3],[1000,2],[390,1]]) {
  call('set','viewport',String(width),'1000'); navigate('#/investment/taccounts');
  if(width===390){call('click','.rail-toggle'); wait("document.querySelector('.workbench-rail').classList.contains('open')");}
  assert.equal(evaluate("getComputedStyle(document.querySelector('.t-account-grid')).gridTemplateColumns.split(' ').length"), expected);
  assert.equal(evaluate('document.documentElement.scrollWidth'),width);
  capture('responsive-taccounts-'+width);
}
writeFileSync(join(run,'browser-checks.json'),JSON.stringify({syntheticOnly:true,checks},null,2));
console.log(`Desktop workbench browser checks passed: ${checks.length}. Screenshots: ${run}`);
