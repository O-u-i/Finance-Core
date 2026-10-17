import { useCallback, useEffect, useRef, useState, useTransition } from 'react';
import { createClient, createCoordinator, readLedgerPaths } from './api.js';

const client = createClient();
export { views, parseRoute } from './navigation.js';
import { viewPaths, parseRoute, assessSetup, routeHash } from './navigation.js';

export function useFinance() {
  const gate = useRef(createCoordinator()).current;
  const [route, setRoute] = useState(parseRoute);
  const [session, setSession] = useState('connecting');
  const [health, setHealth] = useState(null);
  const [actor, setActor] = useState(null);
  const [sessionOrigin, setSessionOrigin] = useState('restored');
  const [setupRecords, setSetupRecords] = useState({ loaded: false });
  const [workspaces, setWorkspaces] = useState([]);
  const [workspace, setWorkspace] = useState(null);
  const setup = assessSetup({ ...setupRecords, workspace, actor });
  const [data, setData] = useState({});
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState(false);
  const [preparingPage, startPageTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [controlUndo, setControlUndo] = useState(null);
  const [oneTimeToken, setOneTimeToken] = useState('');
  const dirty = useRef(new Set());
  // Session-memory only: no finance data is persisted in browser storage.
  const journalBuffer = useRef(null);
  const workspaceRef = useRef(workspace); workspaceRef.current = workspace;
  const routeRef = useRef(route); routeRef.current = route;
  const fail = useCallback((error) => {
    if (error.name === 'AbortError') return;
    setNotice({ error: true, text: error.message });
    if (error.status === 401) { gate.invalidate(); journalBuffer.current = null; setData({}); setWorkspace(null); setWorkspaces([]); setControlUndo(null); setSession('login'); setActor(null); setSetupRecords({ loaded: false }); setOneTimeToken(''); dirty.current.clear(); }
  }, [gate]);

  const bootstrap = useCallback(async ({ fresh = false } = {}) => {
    const ticket = gate.read(); if (!workspaceRef.current) setSession('connecting'); setNotice(null);
    try {
      const [healthResult, me] = await Promise.all([
        client.request('/api/v3/health', { signal: ticket.signal }),
        client.request('/api/v3/me', { signal: ticket.signal }),
      ]);
      const result = await client.request('/api/v3/workspaces', { signal: ticket.signal });
      if (!ticket.current()) return;
      if (fresh) setSessionOrigin('signed-in');
      setHealth(healthResult); setActor(me.data); setWorkspaces(result.data);
      const active = result.data.filter((item) => item.status === 'active');
      const selected = active.find((item) => item.id === workspaceRef.current?.id) || active[0] || null;
      if (selected?.id !== workspaceRef.current?.id) { journalBuffer.current = null; setData({}); setSetupRecords({ loaded: false }); }
      setWorkspace(selected); setSession(selected ? 'ready' : 'wizard');
    } catch (error) { if (ticket.current()) { setSession(error.status === 401 ? 'login' : 'unavailable'); fail(error); } }
  }, [gate, fail]);
  useEffect(() => { bootstrap(); return () => gate.invalidate(); }, [bootstrap, gate]);

  const refresh = useCallback(async (selected = workspaceRef.current, view = routeRef.current.view, nextRoute = null) => {
    if (!selected) return;
    const ticket = gate.read(); setLoading(true);
    try {
      const target = nextRoute || routeRef.current;
      const paths = { ledgerHealth: '/health', commodities: '/commodities' + (['master', 'overview'].includes(view) ? '?includeUsage=true' : ''), accounts: '/accounts', financialAccounts:'/financial-accounts', ...viewPaths(view, target.tab, new Date(), target.segment, target.month) };
      const result = await readLedgerPaths(client, selected.id, paths, ticket.signal);
      if (result.migrationRequired && view === 'overview') {
        Object.assign(result, await readLedgerPaths(client, selected.id, { legacyDashboard: '/dashboard', world: '/world' }, ticket.signal));
      }
      if(result.migrationRequired && view === 'monthlyreview') {
        const legacy = viewPaths('legacyreview', target.tab, new Date(), target.segment, target.month);
        result.monthlyReview = (await client.ledger(selected.id,legacy.monthlyReview,{signal:ticket.signal})).data;
      }
      if (result.migrationRequired && ['balances','livingreview','planning'].includes(view)) {
        Object.assign(result, await readLedgerPaths(client, selected.id, viewPaths('planning',target.tab,new Date(),'living',target.month),ticket.signal));
      }
      if (view === 'settings') {
        const [workspaceResult, tokenResult] = await Promise.all([
          client.request('/api/v3/workspaces', { signal: ticket.signal }), client.request('/api/v3/access-tokens', { signal: ticket.signal }),
        ]);
        result.workspaces = workspaceResult.data; result.tokens = tokenResult.data;
      }
      if (ticket.current() && selected.id === workspaceRef.current?.id && (nextRoute || view === routeRef.current.view)) {
        const commit = () => {
          setData(result);
          setSetupRecords(previous => ({ loaded: true, commodities: result.commodities, accounts: result.accounts, financialAccounts: Object.hasOwn(result,'financialAccounts') ? result.financialAccounts : previous.financialAccounts,
            migrationRequired: Object.hasOwn(result,'migrationRequired') ? result.migrationRequired : previous.migrationRequired }));
          if (nextRoute) {
            dirty.current.clear(); routeRef.current = nextRoute; setRoute(nextRoute);
          }
          if (result.workspaces) setWorkspaces(result.workspaces);
        };
        // Keep the current page visible if the destination's lazy UI is not ready yet.
        if (nextRoute) startPageTransition(commit); else commit();
      }
    } catch (error) { if (ticket.current()) {
      if (error.configurationError) setSetupRecords(previous => ({...previous,error:true,settingsError:!!error.settingsError}));
      fail(error); if (nextRoute) history.replaceState(null, '', routeHash(routeRef.current));
    } }
    finally { if (ticket.current()) setLoading(false); }
  }, [gate, fail, startPageTransition]);
  // Page navigation loads and commits the target atomically; this effect handles Workspace/session changes only.
  useEffect(() => { if (session === 'ready') refresh(workspaceRef.current, routeRef.current.view); }, [workspace?.id, session, refresh]);

  const canLeave = useCallback(() => !gate.writing && (!dirty.current.size || confirm('Discard unsaved changes?')), [gate]);
  const transition = useCallback((next) => {
    setOneTimeToken(''); setNotice(null);
    if (next.view !== routeRef.current.view || next.segment !== routeRef.current.segment || next.month !== routeRef.current.month || (['master','balances','assets','monthlyreview','livingreview','legacyreview'].includes(next.view) && next.tab !== routeRef.current.tab)) refresh(workspaceRef.current, next.view, next);
    else { gate.invalidate(); setLoading(false); dirty.current.clear(); routeRef.current = next; setRoute(next); }
  }, [gate, refresh]);
  useEffect(() => {
    const changed = () => {
      if (!canLeave()) { history.replaceState(null, '', routeHash(routeRef.current)); return; }
      transition(parseRoute());
    };
    const beforeUnload = (event) => { if (dirty.current.size || gate.writing || journalBuffer.current?.unsaved) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('hashchange', changed); window.addEventListener('beforeunload', beforeUnload);
    return () => { window.removeEventListener('hashchange', changed); window.removeEventListener('beforeunload', beforeUnload); };
  }, [canLeave, gate, transition]);

  const navigate = (view, tab = '', segment = routeRef.current.segment || 'investment', month = '') => {
    const next = { view, tab, segment, ...(month ? { month } : {}) };
    const hash = routeHash(next);
    if (location.hash === hash) return true;
    if (!canLeave()) return false;
    history.pushState(null, '', hash); transition(next);
    return true;
  };
  const switchWorkspace = (wid) => {
    if (!canLeave() || (journalBuffer.current?.unsaved && !confirm('Discard the retained Journal editor and switch Workspace? Saved drafts are kept.'))) return;
    gate.invalidate(); journalBuffer.current = null; dirty.current.clear(); setData({}); setSetupRecords({ loaded: false }); setOneTimeToken(''); setControlUndo(null); setNotice(null);
    const next = workspaces.find((item) => item.id === wid);
    workspaceRef.current = next; setWorkspace(next); routeRef.current = { view: 'overview', tab: '' }; setRoute(routeRef.current);
    history.replaceState(null, '', '#/overview');
    window.scrollTo({ top: 0, behavior: 'instant' });
  };
  const run = async (work, message = 'Operation completed.', { write = true, reload = true } = {}) => {
    if (!gate.beginWrite()) return undefined;
    setBusy(true); setLoading(false); setNotice(null);
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
    if (!canLeave() || (journalBuffer.current?.unsaved && !confirm('Discard the retained Journal editor and sign out? Saved drafts are kept.'))) return;
    run(async (api) => {
      // Exit the local UI immediately, even if cookie revocation cannot reach the backend.
      gate.invalidate(); journalBuffer.current = null; setLoading(false); setData({}); setWorkspace(null); workspaceRef.current = null;
      setWorkspaces([]); setActor(null); setSetupRecords({ loaded: false }); setOneTimeToken(''); setControlUndo(null);
      dirty.current.clear(); setSession('login');
      try { await api.request('/api/v3/session', { method: 'DELETE' }); }
      catch (error) { throw new Error('Exited this page, but the saved session could not be revoked. Reconnect and use Forget saved sign-in before reopening your records.'); }
    }, 'Signed out. Saved session cleared.', { write: false, reload: false });
  };
  return { route, session, health, actor, setup, sessionOrigin, workspaces, workspace, data, notice, loading:loading || preparingPage, busy, controlUndo, oneTimeToken, journalBuffer,
    setOneTimeToken, setControlUndo, setNotice, setWorkspace, setWorkspaces, setSession, bootstrap, refresh, navigate, switchWorkspace,
    run, ledger, signOut, canLeave, discardChanges: () => dirty.current.clear(), markDirty: (scope = 'page') => { dirty.current.add(scope); }, clean: (scope = 'page') => { dirty.current.delete(scope); },
    readonly: workspace?.status === 'archived', migrationRequired: setupRecords.migrationRequired, client };
}
