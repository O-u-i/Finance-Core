import test from 'node:test';
import assert from 'node:assert/strict';
import { createClient, createCoordinator, downloadPrivate, validationMatches, readLedgerPaths } from '../src/api.js';

test('new reads abort old requests and discard results across workspace/view changes', () => {
  const gate = createCoordinator(); const old = gate.read(); const latest = gate.read();
  assert.equal(old.signal.aborted, true); assert.equal(old.current(), false); assert.equal(latest.current(), true);
  gate.invalidate(); assert.equal(latest.current(), false);
});
test('writes invalidate reads and prevent duplicate submission until completion', () => {
  const gate = createCoordinator(), read = gate.read();
  assert.equal(gate.beginWrite(), true); assert.equal(read.signal.aborted, true);
  assert.equal(gate.writing, true); assert.equal(gate.beginWrite(), false);
  gate.endWrite(); assert.equal(gate.writing, false); assert.equal(gate.beginWrite(), true);
});
test('any changed draft invalidates its validation snapshot without altering decimal strings', () => {
  const draft = { postings: [{ units: '9007199254740993.001', valuationRate: '0.0001' }] };
  const snapshot = JSON.stringify(draft); assert.equal(validationMatches(draft, snapshot), true);
  const edited = structuredClone(draft); edited.postings[0].units = '9007199254740993.002';
  assert.equal(validationMatches(edited, snapshot), false); assert.equal(draft.postings[0].units, '9007199254740993.001');
});
test('client scopes routes explicitly and transmits decimals unchanged', async () => {
  let received;
  const api = createClient(async (path, options) => { received = { path, options }; return new Response(JSON.stringify({ data: 'ok' }), { headers: { 'Content-Type': 'application/json' } }); });
  await api.ledger('workspace-a', '/drafts', { method: 'POST', body: { units: '9007199254740993.001' } });
  assert.equal(received.path, '/api/v3/workspaces/workspace-a/drafts');
  assert.equal(JSON.parse(received.options.body).units, '9007199254740993.001');
  assert.throws(() => api.ledger(null, '/drafts'));
});
test('session expiry reaches the caller with safe error metadata and performs no retry', async () => {
  let count = 0;
  const api = createClient(async () => { count++; return new Response(JSON.stringify({ error: { code: 'AUTH_REQUIRED', message: 'Authentication is required.' } }), { status: 401, headers: { 'Content-Type': 'application/json' } }); });
  await assert.rejects(api.request('/api/v3/me'), (error) => error.status === 401 && error.code === 'AUTH_REQUIRED');
  assert.equal(count, 1);
});

test('schema-2 refusal preserves existing ledger reads without migration writes', async () => {
  const calls=[];
  const api={async ledger(workspace,path) {
    calls.push([workspace,path]);
    if(path==='/financial-accounts') throw Object.assign(new Error('Migration required'),{code:'SCHEMA_MIGRATION_REQUIRED',status:409});
    return {data:path==='/health' ? {ledgerSchemaVersion:2} : [{id:'existing-ledger-record'}]};
  }};
  const result=await readLedgerPaths(api,'selected-vault',{ledgerHealth:'/health',accounts:'/accounts',financialAccounts:'/financial-accounts'});
  assert.equal(result.migrationRequired,true);
  assert.equal(result.accounts[0].id,'existing-ledger-record');
  assert.equal(result.financialAccounts,undefined);
  assert.ok(calls.every(([workspace]) => workspace==='selected-vault'));
  assert.deepEqual(calls.map(([,path]) => path),['/health','/accounts','/financial-accounts']);
});
test('schema-3 view reads clear migration state; auth failures are never partial success', async () => {
  const api={async ledger(workspace,path) { return {data:path==='/health' ? {ledgerSchemaVersion:3} : []}; }};
  assert.equal((await readLedgerPaths(api,'new-vault',{ledgerHealth:'/health',financialAccounts:'/financial-accounts'})).migrationRequired,false);
  api.ledger=async () => { throw Object.assign(new Error('Unauthorized'),{code:'AUTH_REQUIRED',status:401}); };
  await assert.rejects(readLedgerPaths(api,'new-vault',{financialAccounts:'/financial-accounts'}),error => error.status===401);
});

test('configuration read failures are distinguishable from an unrelated report failure', async () => {
  const api={async ledger() { throw Object.assign(new Error('Synthetic unavailable'),{status:503}); }};
  await assert.rejects(readLedgerPaths(api,'synthetic',{commodities:'/commodities'}),error => error.configurationError && !error.settingsError);
  await assert.rejects(readLedgerPaths(api,'synthetic',{ledgerHealth:'/health'}),error => error.configurationError && error.settingsError);
  await assert.rejects(readLedgerPaths(api,'synthetic',{report:'/reports/synthetic'}),error => !error.configurationError);
});

test('shared private downloads stay Workspace scoped and preserve JSON decimals and one CSV BOM', async t => {
  const blobs = [], revoked = [], calls = [], links = [];
  const documentBefore = globalThis.document;
  globalThis.document = {
    body: { append(link) { links.push(link); } },
    createElement() { return { click() { this.clicked = true; }, remove() { this.removed = true; } }; },
  };
  t.after(() => { if (documentBefore === undefined) delete globalThis.document; else globalThis.document = documentBefore; });
  t.mock.method(URL, 'createObjectURL', blob => { blobs.push(blob); return 'blob:synthetic-download'; });
  t.mock.method(URL, 'revokeObjectURL', url => revoked.push(url));
  t.mock.method(globalThis, 'setTimeout', work => { work(); return 1; });
  const fc = { run(work, message, options) {
    assert.deepEqual(options, {write:false,reload:false});
    return work({ ledger: async (workspace, path) => {
      calls.push([workspace, path]);
      return path.endsWith('.csv') ? '\ufeffamount\r\n0.10\r\n' : {data:{amount:'99999999999999999999.99'}};
    } }, 'synthetic-vault');
  } };
  await downloadPrivate(fc, '/vault-backup', 'backup.json');
  await downloadPrivate(fc, '/segments/living/export.csv', 'living.csv', true);
  assert.equal(JSON.parse(await blobs[0].text()).data.amount, '99999999999999999999.99');
  assert.deepEqual([...new Uint8Array(await blobs[1].arrayBuffer())].slice(0, 6), [239,187,191,97,109,111]);
  assert.equal(blobs[1].type, 'text/csv;charset=utf-8');
  assert.deepEqual(calls, [['synthetic-vault','/vault-backup'],['synthetic-vault','/segments/living/export.csv']]);
  assert.ok(links.every(link => link.clicked && link.removed));
  assert.equal(revoked.length, 2);
});
