import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useFinance, views } from './state.jsx';
import { mainViews, configurationViews } from './navigation.js';
import Setup from './pages/Setup.jsx';
import { SERVICE_VERSION } from './api.js';
import { Button, Field, Logo, Panel, Select, StepContent } from './components.jsx';
import { Overview, Reports } from './pages/Dashboard.jsx';
import Journal from './pages/Journal.jsx';
import Master from './pages/Master.jsx';
import Planning from './pages/Planning.jsx';
import Data from './pages/Data.jsx';
import Settings from './pages/Settings.jsx';

const pages = { overview: Overview, journal: Journal, taccounts: Reports, positions: Reports, cashflow: Reports, statements: Reports, master: Master, planning: Planning, data: Data, settings: Settings };
function Auth({ fc }) {
  return <div className="auth-layout"><Logo/><div className="auth-copy"><h1>Keep your finances<br/>close. See them clearly.</h1><p>A private, local workspace for your financial records.</p><div className="auth-lines" aria-hidden="true"><span/><span/><span/></div></div><Panel title="Enter your workspace" description="Sign in with your local admin token."><form onSubmit={(event) => {
    event.preventDefault(); const form = event.currentTarget, secret = new FormData(form).get('adminToken');
    fc.run(async (api) => { await api.request('/api/v3/session', { method: 'POST', body: { adminToken: secret } }); form.reset(); await fc.bootstrap({ fresh: true }); }, 'Connected.', { write: false, reload: false });
  }}><fieldset disabled={fc.busy}><Field label="Admin token"><input name="adminToken" type="password" autoComplete="current-password" required/></Field><Button primary type="submit">Enter Finance Core</Button></fieldset></form><div className="saved-signin-actions"><h3>Saved sign-in</h3><p>Forget a previous sign-in on this browser. Your workspaces and records are kept.</p><Button disabled={fc.busy} onClick={fc.signOut}>Forget saved sign-in</Button></div></Panel></div>;
}
function Wizard({ fc }) {
  return <div className="wizard-layout"><Logo/><Panel title="Create your first workspace" description="Choose a personal Vault for your records or an empty sandbox for synthetic examples."><form onSubmit={(event) => {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget));
    fc.run(async (api) => { const result = await api.request('/api/v3/workspaces', { method: 'POST', body: values }); await fc.bootstrap(); return result; }, 'Workspace created.', { write: false, reload: false });
  }}><fieldset disabled={fc.busy}><Field label="Workspace name"><input name="displayName" required maxLength={120}/></Field><Field label="Kind"><select name="kind"><option value="personal">Personal</option><option value="sandbox">Sandbox</option></select></Field><Button primary>Create workspace</Button></fieldset></form>
  {fc.workspaces.filter((item) => item.status === 'archived').map((item) => <Button key={item.id} disabled={fc.busy} onClick={() => fc.run(async (api) => { const result = await api.request(`/api/v3/workspaces/${item.id}`, { method: 'PATCH', body: { status: 'active' } }); await fc.bootstrap(); return result; }, 'Workspace restored.', { write: false, reload: false })}>Restore {item.displayName}</Button>)}
  {fc.controlUndo && <Button disabled={fc.busy} onClick={() => fc.run(async (api) => { const result = await api.request('/api/v3/undo', { method: 'POST', body: { undoToken: fc.controlUndo.undoToken } }); fc.setControlUndo(null); await fc.bootstrap(); return result; }, 'Workspace operation undone.', { write: false, reload: false })}>Undo workspace operation</Button>}
  </Panel><Button disabled={fc.busy} onClick={fc.signOut}>Sign out</Button></div>;
}
export default function App() {
  const fc = useFinance(); const [menu, setMenu] = useState(false);
  const navigation = useRef(null), [pill, setPill] = useState(null);
  useEffect(() => { setMenu(false); }, [fc.route.view]);
  useLayoutEffect(() => {
    const nav = navigation.current;
    if (!nav) return;
    const measure = () => {
      const active = nav.querySelector('button.active');
      setPill(active?.getClientRects().length ? { width: active.offsetWidth, height: active.offsetHeight, transform: `translate(${active.offsetLeft}px, ${active.offsetTop}px)` } : null);
    };
    measure(); const observer = new ResizeObserver(measure); observer.observe(nav);
    return () => observer.disconnect();
  }, [fc.route.view, fc.session, menu]);
  const Page = pages[fc.route.view];
  const blocked = !fc.setup.ready && !configurationViews.includes(fc.route.view);
  return <><a href="#main-content" className="skip-link" onClick={(e) => { e.preventDefault(); document.querySelector('#main-content')?.focus(); }}>Skip to content</a>
    {fc.notice && <div className={`global-notice notice ${fc.notice.error ? 'error' : 'success'}`} role={fc.notice.error ? 'alert' : 'status'}><span>{fc.notice.text}</span><Button aria-label="Dismiss notification" onClick={() => fc.setNotice(null)}>×</Button></div>}
    {fc.session === 'connecting' && <div className="connection-state"><Logo/><h1>Connecting to Finance Core</h1><p role="status">Checking your local session…</p></div>}
    {fc.session === 'unavailable' && <div className="connection-state"><Logo/><h1>Finance Core is unavailable</h1><p>Start the local backend and try again.</p><Button primary onClick={fc.bootstrap}>Retry connection</Button><Button disabled={fc.busy} onClick={fc.signOut}>Forget saved sign-in</Button></div>}
    {fc.session === 'login' && <Auth fc={fc}/>}
    {fc.session === 'wizard' && <Wizard fc={fc}/>}
    {fc.session === 'ready' && fc.workspace && <div className="app-shell">
      <header className="app-header"><div className="identity-row"><a className="brand-link" href="#/overview" onClick={(e) => { e.preventDefault(); fc.navigate('overview'); }}><Logo/></a><div className="session-tools"><span className="session-label">Owner session<small>{fc.sessionOrigin === 'restored' ? 'Restored from this browser' : 'Signed in with your admin token'}</small></span><Button disabled={fc.busy} onClick={fc.signOut}>Sign out</Button></div></div>
        <div className="configuration-row"><nav className="configuration-nav" aria-label="Configuration navigation">{configurationViews.map(key => <button key={key} data-status={(key === 'master' ? fc.setup.masterReady : fc.setup.sessionReady && fc.setup.workspaceReady) ? 'ready' : 'pending'} disabled={fc.busy} aria-current={fc.route.view === key ? 'page' : undefined} className={fc.route.view === key ? 'active' : ''} onClick={() => fc.navigate(key)}><span>{views[key][0]}</span><small className="configuration-status">{key === 'master' ? (fc.setup.masterReady ? 'Ready' : 'Setup required') : (fc.setup.sessionReady && fc.setup.workspaceReady ? 'Ready' : 'Setup required')}</small></button>)}</nav><div className="workspace-tools"><Select label={<><span>Workspace</span><span className="workspace-kind" data-kind={fc.workspace.kind}>{fc.workspace.kind}</span></>} value={fc.workspace.id} disabled={fc.busy} onChange={fc.switchWorkspace} options={fc.workspaces.filter(item => item.status !== 'quarantined').map(item => ({ value: item.id, label: item.displayName }))}/></div></div>
      </header>
      <Button aria-expanded={menu} aria-controls="main-navigation" className="mobile-nav-toggle" disabled={fc.busy} onClick={() => setMenu(!menu)}>Menu <span aria-hidden="true">{menu ? '−' : '+'}</span></Button>
      <nav ref={navigation} id="main-navigation" className={`pill-nav ${menu ? 'open' : ''} ${pill ? 'has-indicator' : ''}`} aria-label="Main navigation">{pill && <span className="nav-indicator" aria-hidden="true" style={pill}/>} {mainViews.map(key => <button key={key} disabled={fc.busy || !fc.setup.ready} aria-current={fc.route.view === key ? 'page' : undefined} className={fc.route.view === key ? 'active' : ''} onClick={() => fc.navigate(key)}><span>{views[key][0]}</span></button>)}</nav>
      <main id="main-content" tabIndex={-1} key={fc.workspace.id} aria-busy={fc.busy || fc.loading}>
        {fc.route.view !== 'overview' && <div className="page-heading"><div><p>{fc.workspace.displayName}</p><h1>{views[fc.route.view][0]}</h1></div><span className="badge">{fc.workspace.status === 'archived' ? 'Read only' : 'Workspace scoped'}</span></div>}
        {fc.readonly && <p className="notice">Archived workspace · records are read-only. Restore it in Settings to make changes.</p>}
        {(fc.busy || fc.loading) && <div className="loading-line" role="status">{fc.busy ? 'Applying operation…' : 'Loading records…'}</div>}
        <div inert={fc.loading || undefined}><StepContent className="page-content" step={`${fc.route.view}/${fc.route.tab}`}><React.Fragment key={`${fc.route.view}/${fc.route.tab}/${blocked}`} >{blocked ? <Setup fc={fc}/> : <Page fc={fc}/>}</React.Fragment></StepContent></div>
      </main>
      <aside className="about-strip"><h2>Finance you can trace.</h2><p>A local ledger, explicit values and a history that stays intact.</p><Button onClick={() => fc.navigate('settings')}>About Finance Core</Button></aside>
      <footer><span>Finance Core {SERVICE_VERSION}</span><span>Local first · Deterministic · Private by design</span></footer>
    </div>}
  </>;
}
