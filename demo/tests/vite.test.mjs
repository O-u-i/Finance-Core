import test from 'node:test';
import assert from 'node:assert/strict';
import config from '../../vite.config.js';

test('Vite limits dependency discovery and watching to the UI without disabling HMR', () => {
  assert.deepEqual(config.optimizeDeps?.entries, ['index.html']);
  const ignored = config.server.watch?.ignored ?? [];
  for (const directory of [
    '.tmp', 'tmp', '.pytest_cache', 'backend', 'dist', 'test', 'demo/tests',
    'docs', 'plugins', 'tools', '.agents', '.codex',
    '.local-data', '.local-acceptance', 'imports', 'exports', 'private', 'personal',
    'real-data', 'attachments',
  ]) {
    assert.ok(ignored.includes(`**/${directory}/**`), `${directory} must not be watched`);
  }
  assert.notEqual(config.server.hmr, false);
  assert.equal(config.build.emptyOutDir, false);
});
