// Public UI + Workspace API regressions. The caller owns the synthetic server and named browser session.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';

const run = resolve(process.env.FC_UI_TEST_RUN || '');
assert(process.env.FC_UI_TEST_RUN && run.startsWith(resolve('.tmp') + sep), 'Select an owned .tmp run.');
const fixture = JSON.parse(readFileSync(join(run, 'fixture.json'), 'utf8'));
assert.equal(fixture.syntheticOnly, true);
assert(process.env.FC_AGENT_BROWSER && process.env.AGENT_BROWSER_SESSION && process.env.AGENT_BROWSER_NAMESPACE, 'Use an owned agent-browser session.');
const stage = process.argv[2] || 'segment';
assert(['segment', 'order', 'filters', 'all'].includes(stage), 'Select a regression stage.');
const evidence = join(run, 'registry-' + stage);
mkdirSync(evidence, { recursive: true });
const command = (...args) => {
  const result = JSON.parse(execFileSync(process.env.FC_AGENT_BROWSER, ['--json', ...args], { encoding: 'utf8', timeout: 40000 }));
  assert.equal(result.success, true, result.error || 'Browser command failed.');
  return result.data;
};
const evaluate = expression => command('eval', expression).result;
const settled = () => command('wait', '--fn', "!!document.querySelector('.app-shell') && !document.querySelector('.loading-line') && !document.querySelector('[aria-busy=true]')");
const glide = (name, label) => {
  command('click', `.select-field:has(select[name="${name}"]) button`);
  command('wait', '[role=listbox]');
  evaluate(`[...document.querySelectorAll('[role=option]')].find(item=>item.firstElementChild.textContent.trim()===${JSON.stringify(label)}).click()`);
};
const rows = () => evaluate(`[...document.querySelectorAll('[aria-label="Financial account registry"] tbody tr')].map(row=>[...row.cells].slice(0,6).map(cell=>cell.textContent.trim()))`);
const request = (workspaceId, path) => evaluate(`(async()=>{
  const response=await fetch('/api/v3/workspaces/'+${JSON.stringify(workspaceId)}+${JSON.stringify(path)});
  if(!response.ok)throw Error('Synthetic API read failed: '+response.status);
  return (await response.json()).data;
})()`);
const checks = [];
try {
  // Never continue against the user's IPv4 dev server or real Vaults.
  command('open', 'http://localhost:5174/__synthetic_marker');
  assert.equal(evaluate('document.body.textContent'), 'fc-ui-account-fixes-synthetic-only');
  command('set', 'viewport', '1440', '1000');
  command('open', 'http://localhost:5174/#/master/accounts');
  command('wait', '--fn', "!!document.querySelector('input[name=adminToken]') || !!document.querySelector('.app-shell')");
  if (evaluate("!!document.querySelector('input[name=adminToken]')")) {
    command('fill', 'input[name=adminToken]', 'synthetic-browser-admin');
    command('click', 'button[type=submit]');
  }
  settled();
  evaluate('window.confirm=()=>true');
  for (const [workspaceId, legacy] of [[fixture.workspaceId, false], [fixture.legacyWorkspaceId, true]]) {
    command('select', '.workspace-tools select', workspaceId); settled();
    command('click', '.configuration-nav button:nth-child(2)'); settled();
    command('click', '.subnav button:nth-child(2)'); settled();
    if (stage !== 'segment') {
      evaluate(`(async()=>{
        const prefix='/api/v3/workspaces/'+${JSON.stringify(workspaceId)};
        if(!(await (await fetch(prefix+'/commodities')).json()).data.some(item=>item.code==='MYR')){
          const response=await fetch(prefix+'/commodities',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:'MYR',kind:'currency',scale:2,name:'Synthetic MYR'})});
          if(!response.ok)throw Error('Synthetic currency setup failed');
        }
        const path=prefix+'/'+${JSON.stringify(legacy ? 'accounts' : 'financial-accounts')};
        const existing=(await (await fetch(path)).json()).data;
        for(const [code,name] of [['SORT10','Synthetic Alpha tenth'],['SORT2','Synthetic Beta second'],['SORT1','Synthetic Gamma first']]){
          const old=existing.find(item=>item.code===code);
          const body={id:'sort-'+code,code,name,type:code==='SORT10'?'liability':'asset',subtype:'cash',allowedCommodityCodes:[code==='SORT10'?'MYR':'CNY'],status:code==='SORT10'?'inactive':'active',...${legacy ? '{}' : "{segment:'investment',balanceSource:'ledger',classificationConfirmed:true}"}};
          const response=await fetch(path+(old?'/'+body.id:''),{method:old?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
          if(!response.ok)throw Error('Synthetic account setup failed: '+response.status);
        }
      })()`);
      command('click', '.subnav button:nth-child(3)'); settled();
      command('click', '.subnav button:nth-child(2)'); settled();
    }
    const original = request(workspaceId, legacy ? '/living-accounts' : '/financial-accounts');
    assert(original.some(item => legacy || item.segment === 'living'), 'The synthetic fixture contains Living accounts.');
    assert.equal(evaluate("document.querySelector('select[name=segment]').value"), 'investment');
    assert.deepEqual([...new Set(rows().map(row => row[2]))], ['investment'], 'Investment must not display Living accounts.');
    glide('segment', 'Living');
    assert.deepEqual([...new Set(rows().map(row => row[2]))], ['living'], 'Selecting Living switches the registry, not just the creation form.');
    glide('segment', 'Investment');
    assert.deepEqual([...new Set(rows().map(row => row[2]))], ['investment']);
    assert.deepEqual(request(workspaceId, legacy ? '/living-accounts' : '/financial-accounts'), original, 'Browsing segments must not mutate financial data.');
    checks.push(`${legacy ? 'Schema 2' : 'Schema 3'} segment visibility and API preservation`);
    if (stage !== 'segment') {
      assert.deepEqual(rows().map(row => row[0]).filter(code => code.startsWith('SORT')), ['SORT1', 'SORT2', 'SORT10'], 'Codes use natural ascending order, not insertion, name or lexical order.');
      checks.push(`${legacy ? 'Schema 2' : 'Schema 3'} natural code order`);
    }
    if (['filters', 'all'].includes(stage)) {
      assert.equal(evaluate("!!document.querySelector('input[name=accountSearch]')"), true, 'The registry offers an account search.');
      command('fill', 'input[name=name]', 'Unsaved synthetic draft');
      command('fill', 'input[name=accountSearch]', ' sort2 ');
      assert.deepEqual(rows().map(row => row[0]), ['SORT2'], 'Search codes without case or whitespace surprises.');
      command('click', 'input[name=accountSearch]'); command('press', 'Control+a'); command('press', 'Backspace');
      command('fill', 'input[name=accountSearch]', 'SORT');
      glide('accountTypeFilter', 'liability');
      assert.deepEqual(rows().map(row => row[0]), ['SORT10']);
      glide('accountTypeFilter', 'All types');
      glide('accountCommodityFilter', 'MYR');
      glide('accountStatusFilter', 'Inactive');
      assert.deepEqual(rows().map(row => row[0]), ['SORT10'], 'Commodity and status filters compose.');
      glide('accountStatusFilter', 'Active');
      assert.deepEqual(rows(), []);
      assert(evaluate("document.querySelector('main').textContent.includes('No accounts match these filters.')"));
      command('find', 'role', 'button', 'click', '--name', 'Clear filters', '--exact');
      assert.deepEqual(rows().map(row => row[0]).filter(code => code.startsWith('SORT')), ['SORT1', 'SORT2', 'SORT10']);
      assert.equal(evaluate("document.querySelector('input[name=name]').value"), 'Unsaved synthetic draft', 'Filters must not reset or submit the registration form.');
      assert.deepEqual(request(workspaceId, legacy ? '/living-accounts' : '/financial-accounts'), original);
      checks.push(`${legacy ? 'Schema 2' : 'Schema 3'} composable read-only filters and dirty-form preservation`);
    }
  }
  writeFileSync(join(evidence, 'receipt.json'), JSON.stringify({ syntheticOnly: true, checks }, null, 2));
  console.log(`Passed ${checks.length} account registry checks (${stage}).`);
} catch (error) {
  try { writeFileSync(join(evidence, 'visible-state.json'), JSON.stringify(evaluate(`({rows:[...document.querySelectorAll('main tbody tr')].map(row=>row.textContent),filters:[...document.querySelectorAll('.account-filters input,.account-filters select')].map(item=>({name:item.name,value:item.value}))})`), null, 2)); } catch {}
  writeFileSync(join(evidence, 'failure.txt'), error.stack || String(error));
  throw error;
}
