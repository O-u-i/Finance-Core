import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer, isFileServingAllowed, normalizePath } from 'vite';
import { fileURLToPath } from 'node:url';
import { createServer as createHttpServer } from 'node:http';
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

test('Vite serves UI inputs, not local Vaults, private files or unrelated workspace roots', async () => {
  const server = await createServer({
    ...config, configFile: false, logLevel: 'silent',
    cacheDir: '.tmp/ui-render-cache',
    optimizeDeps: { noDiscovery: true, entries: [] },
    server: { ...config.server, middlewareMode: true, watch: null, hmr: false },
  });
  const http = createHttpServer(server.middlewares);
  const path = value => fileURLToPath(new URL(value, import.meta.url));
  try {
    assert.equal(config.server.host, '127.0.0.1');
    assert.equal(config.server.strictPort, true);
    for (const name of ['index.html', 'demo/src/main.jsx', 'node_modules/react/index.js', 'public/LICENSE.txt']) {
      assert.equal(isFileServingAllowed(server.config, path(`../../${name}`)), true, name);
    }
    for (const name of [
      '.local-data/v3/workspaces/synthetic/finance-core.sqlite3', '.local-acceptance/fixture.json',
      '.env', 'AGENTS.md', '.git/config', '.tmp/fixture.json', 'tmp/fixture.json',
      'backend/pyproject.toml', 'test/fixture.csv', 'private/fixture.json',
      'personal/fixture.json', 'imports/fixture.json', 'exports/fixture.json',
      'attachments/fixture.json', 'package.json', 'docs/private-plan.md',
      'demo/src/accidental-secret.pem', 'public/accidental-finance.sqlite3',
    ]) {
      assert.equal(isFileServingAllowed(server.config, path(`../../${name}`)), false, name);
    }
    assert.equal(isFileServingAllowed(server.config, path('../../../unrelated-vault/fixture.json')), false);
    await new Promise(resolve => http.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${http.address().port}`;
    assert.equal((await fetch(`${base}/index.html`)).status, 200);
    assert.equal((await fetch(`${base}/demo/src/main.jsx`)).status, 200);
    for (const name of ['backend/pyproject.toml', 'package.json']) {
      assert.equal((await fetch(`${base}/${name}`)).status, 403, name);
      assert.equal((await fetch(`${base}/@fs/${normalizePath(path(`../../${name}`))}?raw`)).status, 403, name);
    }
  } finally {
    http.closeAllConnections();
    if (http.listening) await new Promise(resolve => http.close(resolve));
    await server.close();
  }
});
