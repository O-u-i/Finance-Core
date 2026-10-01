import { useCallback, useEffect, useRef, useState } from 'react';
import { createClient, createCoordinator } from './api.js';

const client = createClient();
export const views = {
  overview: ['Overview', { dashboard: '/dashboard', reconciliation: '/reconciliation', undo: '/undo/latest' }],
  journal: ['Journal', { commodities: '/commodities', accounts: '/accounts', drafts: '/journal-entry-drafts', entries: '/journal-entries', undo: '/undo/latest' }],
  reports: ['Holdings & reports', { holdings: '/holdings', statements: '/financial-statements', cashFlow: '/cash-flow', tAccounts: '/t-accounts' }],
  planning: ['Living & plans', { commodities: '/commodities', living: '/living-accounts', snapshots: '/living-snapshots', plans: '/monthly-plans', world: '/world' }],
  data: ['Automation & data', { recurring: '/recurring-entry-rules', drafts: '/journal-entry-drafts', undo: '/undo/latest' }],
  master: ['Master data', { commodities: '/commodities', accounts: '/accounts', quotes: '/price-quotes', undo: '/undo/latest' }],
  settings: ['Settings', {}],
};
export const parseRoute = () => {
  const [view, tab] = location.hash.replace(/^#\/?/, '').split('/');
  return { view: views[view] ? view : 'overview', tab: tab || '' };
};

export function useFinance() {
  const gate = useRef(createCoordinator()).current;
  const [route, setRoute] = useState(parseRoute);
  const [session, setSession] = useState('connecting');
  const [health, setHealth] = useState(null);
  const [workspaces, setWorkspaces] = useState([]);
  const [workspace, setWorkspace] = useState(null);
  const [data, setData] = useState({});
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [controlUndo, setControlUndo] = useState(null);
  const [oneTimeToken, setOneTimeToken] = useState('');
  const dirty = useRef(new Set());
  const workspaceRef = useRef(workspace); workspaceRef.current = workspace;
  const routeRef = useRef(route); routeRef.current = route;
  const fail = useCallback((error) => {
    if (error.name === 'AbortError') return;
    setNotice({ error: true, text: error.message });
    if (error.status === 401) { gate.invalidate(); setData({}); setWorkspace(null); setWorkspaces([]); setControlUndo(null); setSession('login'); setOneTimeToken(''); dirty.current.clear(); }
  }, [gate]);

  const bootstrap = useCallback(async () => {
    const ticket = gate.read(); setSession('connecting'); setNotice(null);
    try {
      const healthResult = await client.request('/api/v3/health', { signal: ticket.signal });
      await client.request('/api/v3/me', { signal: ticket.signal });
      const result = await client.request('/api/v3/workspaces', { signal: ticket.signal });
      if (!ticket.current()) return;
      setHealth(healthResult); setWorkspaces(result.data);
      const active = result.data.filter((item) => item.status === 'active');
      const selected = active.find((item) => item.id === workspaceRef.current?.id) || active[0] || null;
      setWorkspace(selected); setSession(selected ? 'ready' : 'wizard');
    } catch (error) { if (ticket.current()) { setSession(error.status === 401 ? 'login' : 'unavailable'); fail(error); } }
  }, [gate, fail]);
  useEffect(() => { bootstrap(); return () => gate.invalidate(); }, [bootstrap, gate]);

  const refresh = useCallback(async (selected = workspaceRef.current, view = routeRef.current.view) => {
    if (!selected) return;
    const ticket = gate.read(); setLoading(true);
    try {
      const paths = views[view][1];
      const result = view === 'settings'
        ? { workspaces: (await client.request('/api/v3/workspaces', { signal: ticket.signal })).data, tokens: (await client.request('/api/v3/access-tokens', { signal: ticket.signal })).data }
        : Object.fromEntries(await Promise.all(Object.entries(paths).map(async ([key, path]) => {
          const payload = await client.ledger(selected.id, path, { signal: ticket.signal });
          return [key, Object.hasOwn(payload, 'data') ? payload.data : payload];
        })));
      if (ticket.current() && selected.id === workspaceRef.current?.id && view === routeRef.current.view) {
        setData(result);
        if (result.workspaces) setWorkspaces(result.workspaces);
      }
    } catch (error) { if (ticket.current()) fail(error); }
    finally { if (ticket.current()) setLoading(false); }
  }, [gate, fail]);
  useEffect(() => { if (session === 'ready') refresh(workspace, route.view); }, [workspace?.id, route.view, session, refresh]);

  const canLeave = useCallback(() => !gate.writing && (!dirty.current.size || confirm('Discard unsaved changes?')), [gate]);
  useEffect(() => {
    const changed = () => {
      if (!canLeave()) { history.replaceState(null, '', `#/${routeRef.current.view}${routeRef.current.tab ? '/' + routeRef.current.tab : ''}`); return; }
      const next = parseRoute(); dirty.current.clear(); setOneTimeToken(''); setNotice(null);
      if (next.view !== routeRef.current.view) { gate.invalidate(); setData({}); }
      setRoute(next);
      window.scrollTo({ top: 0, behavior: 'instant' });
    };
    const beforeUnload = (event) => { if (dirty.current.size || gate.writing) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('hashchange', changed); window.addEventListener('beforeunload', beforeUnload);
    return () => { window.removeEventListener('hashchange', changed); window.removeEventListener('beforeunload', beforeUnload); };
  }, [canLeave, gate]);

  const navigate = (view, tab = '') => {
    if (!canLeave()) return;
    dirty.current.clear(); location.hash = `/${view}${tab ? '/' + tab : ''}`;
  };
  const switchWorkspace = (wid) => {
    if (!canLeave()) return;
    gate.invalidate(); dirty.current.clear(); setData({}); setOneTimeToken(''); setControlUndo(null); setNotice(null);
    const next = workspaces.find((item) => item.id === wid);
    workspaceRef.current = next; setWorkspace(next); setRoute({ view: 'overview', tab: '' });
    history.replaceState(null, '', '#/overview');
    window.scrollTo({ top: 0, behavior: 'instant' });
  };
  const run = async (work, message = 'Operation completed.', { write = true, reload = true } = {}) => {
    if (!gate.beginWrite()) return undefined;
    setBusy(true); setNotice(null);
    try {
      if (write && workspaceRef.current?.status === 'archived') throw new Error('Archived workspaces are read-only.');
      const result = await work(client, workspaceRef.current?.id);
      if (result?.undo && !result.undo.operationType?.startsWith('ledger')) setControlUndo(result.undo);
      setNotice({ text: message });
      if (reload) await refresh();
      return result;
    } catch (error) { fail(error); return undefined; }
    finally { gate.endWrite(); setBusy(false); }
  };
  const ledger = (path, options, message) => run((api, wid) => api.ledger(wid, path, options), message);
  const signOut = () => {
    if (!canLeave()) return;
    run(async (api) => {
      await api.request('/api/v3/session', { method: 'DELETE' });
      gate.invalidate(); setData({}); setWorkspace(null); setWorkspaces([]); setOneTimeToken(''); setControlUndo(null);
      dirty.current.clear(); setSession('login');
    }, 'Signed out.', { write: false, reload: false });
  };
  return { route, session, health, workspaces, workspace, data, notice, loading, busy, controlUndo, oneTimeToken,
    setOneTimeToken, setControlUndo, setNotice, setWorkspace, setWorkspaces, setSession, bootstrap, refresh, navigate, switchWorkspace,
    run, ledger, signOut, canLeave, discardChanges: () => dirty.current.clear(), markDirty: (scope = 'page') => { dirty.current.add(scope); }, clean: (scope = 'page') => { dirty.current.delete(scope); },
    readonly: workspace?.status === 'archived', client };
}
