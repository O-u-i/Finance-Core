import test from 'node:test';
import assert from 'node:assert/strict';
import { createClient, createCoordinator, validationMatches } from '../src/api.js';

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
