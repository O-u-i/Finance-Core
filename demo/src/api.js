export const API_VERSION = '3.5.0';
export const SERVICE_VERSION = '3.6.0';
export const id = (prefix) => `${prefix}-${crypto.randomUUID()}`;
export const localDate = () => {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};

export function createClient(fetcher = globalThis.fetch) {
  async function request(path, { body, signal, headers, ...options } = {}) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    let timeout = false;
    if (signal?.aborted) abort();
    signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(() => { timeout = true; abort(); }, 10000);
    try {
      const response = await fetcher(path, {
        ...options, signal: controller.signal, credentials: 'same-origin',
        headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...headers },
        ...(body !== undefined ? { body: typeof body === 'string' ? body : JSON.stringify(body) } : {}),
      });
      const payload = response.headers.get('content-type')?.includes('json') ? await response.json() : await response.text();
      if (!response.ok) {
        const error = new Error(payload?.error?.message || 'Finance Core could not complete this request.');
        error.status = response.status; error.code = payload?.error?.code; error.issues = payload?.error?.issues;
        throw error;
      }
      return payload;
    } catch (error) {
      if (timeout) throw new Error('Request timed out. Check the local Finance Core backend.');
      if (error instanceof TypeError) throw new Error('Cannot connect to Finance Core. Start the local backend and retry.');
      throw error;
    } finally {
      clearTimeout(timer); signal?.removeEventListener('abort', abort);
    }
  }
  return {
    request,
    ledger(workspaceId, path, options) {
      if (!workspaceId) throw new Error('Select a workspace first.');
      return request(`/api/v3/workspaces/${encodeURIComponent(workspaceId)}${path}`, options);
    },
  };
}

// Shared by React and deterministic tests: only the newest read may publish;
// a write locks navigation, invalidates reads, and cannot start twice.
export function createCoordinator() {
  let generation = 0, writing = false, controller;
  return {
    read() {
      controller?.abort(); controller = new AbortController();
      const ticket = ++generation;
      return { signal: controller.signal, current: () => ticket === generation };
    },
    invalidate() { ++generation; controller?.abort(); },
    beginWrite() {
      if (writing) return false;
      writing = true; ++generation; controller?.abort(); return true;
    },
    endWrite() { writing = false; },
    get writing() { return writing; },
  };
}

export const validationMatches = (draft, validatedDraft) => JSON.stringify(draft) === validatedDraft;

export function downloadPrivate(fc, path, filename, csv = false) {
  return fc.run(async (api, workspaceId) => {
    const payload = await api.ledger(workspaceId, path);
    const content = csv ? '\ufeff' + payload.replace(/^\ufeff/, '') : JSON.stringify(payload, null, 2);
    const url = URL.createObjectURL(new Blob([content], { type: csv ? 'text/csv;charset=utf-8' : 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = filename;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return { downloaded: true };
  }, 'Private export downloaded. Store it safely outside Git.', { write: false, reload: false });
}

// Keep a schema-2 ledger usable without enabling new personal reads. Only the
// explicit migration refusal is recoverable; auth/network failures stay fatal.
export async function readLedgerPaths(api, workspaceId, paths, signal) {
  let migrationRequired = false;
  const result = Object.fromEntries(await Promise.all(Object.entries(paths).map(async ([key, path]) => {
    try {
      const payload = await api.ledger(workspaceId, path, { signal });
      return [key, Object.hasOwn(payload, 'data') ? payload.data : payload];
    } catch (error) {
      if (error.code !== 'SCHEMA_MIGRATION_REQUIRED') throw error;
      migrationRequired = true;
      return [key, undefined];
    }
  })));
  if (Object.hasOwn(paths, 'ledgerHealth') || Object.hasOwn(paths, 'financialAccounts')) result.migrationRequired = migrationRequired || result.ledgerHealth?.ledgerSchemaVersion === 2;
  return result;
}
