import React, { lazy, Suspense, useEffect, useState } from 'react';
import { useFinance, views } from './state.jsx';
import { segmentViews, configurationViews } from './navigation.js';
import { SERVICE_VERSION } from './api.js';
import { Button, Field, Logo, Panel, Select, StepContent } from './components.jsx';
import LineSidebar from './LineSidebar.jsx';
// Authentication does not need to download or transform Workspace forms and CSV tooling.
const named = (load, name) => lazy(() => load().then(module => ({ default: module[name] })));
const Setup = lazy(() => import('./pages/Setup.jsx'));
const Journal = lazy(() => import('./pages/Journal.jsx'));
const Master = lazy(() => import('./pages/Master.jsx'));
const Planning = lazy(() => import('./pages/Planning.jsx'));
const Data = lazy(() => import('./pages/Data.jsx'));
const Settings = lazy(() => import('./pages/Settings.jsx'));
const MonthlyReview = lazy(() => import('./pages/MonthlyReview.jsx'));
const Reports = named(() => import('./pages/Dashboard.jsx'), 'Reports');
const AssetsLiabilities = named(() => import('./pages/PersonalFinance.jsx'), 'AssetsLiabilities');
const PersonalMonthlyReview = named(() => import('./pages/PersonalFinance.jsx'), 'PersonalMonthlyReview');
const FinanceOverview = named(() => import('./pages/RecordedBalances.jsx'), 'FinanceOverview');
const RecordedBalances = named(() => import('./pages/RecordedBalances.jsx'), 'RecordedBalances');
const RecordedLivingReview = named(() => import('./pages/RecordedBalances.jsx'), 'RecordedLivingReview');
const LivingData = named(() => import('./pages/SegmentData.jsx'), 'LivingData');

const pages = { overview: FinanceOverview, journal: Journal, taccounts: Reports, positions: Reports, cashflow: Reports, statements: Reports, monthlyreview: PersonalMonthlyReview, legacyreview: MonthlyReview, master: Master, planning: Planning, plans: Planning, balances: RecordedBalances, assets: AssetsLiabilities, livingreview: RecordedLivingReview, livingdata: LivingData, data: Data, settings: Settings };
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
  useEffect(() => { setMenu(false); }, [fc.route.view]);
  const segment = fc.route.segment || (['balances','assets','plans','livingreview','livingdata'].includes(fc.route.view) ? 'living' : 'investment');
  const globalPage = configurationViews.includes(fc.route.view);
  const navKeys = fc.migrationRequired && segment === 'living' ? ['planning'] : segmentViews[segment];
  const Page = fc.route.view === 'monthlyreview' && (!fc.route.segment || fc.migrationRequired) ? MonthlyReview : pages[fc.route.view];
  const blocked = !fc.setup.ready && !configurationViews.includes(fc.route.view);
  return <><a href="#main-content" className="skip-link" onClick={(e) => { e.preventDefault(); document.querySelector('#main-content')?.focus(); }}>Skip to content</a>
    {fc.notice && <div className={`global-notice notice ${fc.notice.error ? 'error' : 'success'}`} role={fc.notice.error ? 'alert' : 'status'}><span>{fc.notice.text}</span><Button aria-label="Dismiss notification" onClick={() => fc.setNotice(null)}>×</Button></div>}
    {fc.session === 'unavailable' && <div className="connection-state"><Logo/><h1>Finance Core is unavailable</h1><p>Start the local backend and try again.</p><Button primary onClick={fc.bootstrap}>Retry connection</Button><Button disabled={fc.busy} onClick={fc.signOut}>Forget saved sign-in</Button></div>}
    {['connecting', 'login'].includes(fc.session) && <Auth fc={fc}/>}
    {fc.session === 'wizard' && <Wizard fc={fc}/>}
    {fc.session === 'ready' && fc.workspace && <div className="app-shell" data-segment={globalPage ? 'shared' : segment}>
      <header className="workbench-header">
        <button className="overview-entry" aria-current={fc.route.view === 'overview' ? 'page' : undefined} disabled={fc.busy} onClick={() => fc.navigate('overview')}>Overview</button>
        <a className="workbench-logo" href="#/overview" onClick={event => { event.preventDefault(); fc.navigate('overview'); }}><Logo markOnly small/></a>
        <div className="workbench-session"><div className="workspace-tools"><Select label="Workspace" value={fc.workspace.id} disabled={fc.busy} onChange={fc.switchWorkspace} options={fc.workspaces.filter(item => item.status !== 'quarantined').map(item => ({ value: item.id, label: item.displayName }))}/></div><Button disabled={fc.busy} onClick={fc.signOut}>Sign out</Button></div>
      </header>
      <nav className="workbench-nav" aria-label="Global navigation">
        <div className="segment-entries">{['investment','living'].map(value => <button key={value} data-segment={value} disabled={fc.busy} aria-current={!globalPage && segment === value ? 'page' : undefined} onClick={() => fc.navigate(value === 'living' ? (fc.migrationRequired ? 'planning' : 'balances') : 'journal','',value)}>{value === 'living' ? 'Living' : 'Investment'}</button>)}</div>
        <div className="global-entries">{configurationViews.filter(key => key !== 'overview').map(key => <button key={key} disabled={fc.busy} aria-current={fc.route.view === key ? 'page' : undefined} onClick={() => fc.navigate(key)}>{views[key][0]}{key === 'master' && !fc.setup.masterReady && <span className="setup-required">Setup required</span>}</button>)}</div>
      </nav>
      <div className={`workbench-layout${globalPage ? ' workbench-global' : ''}`}>
      {!globalPage && <aside className={`workbench-rail${menu ? ' open' : ''}`}><Button aria-expanded={menu} aria-controls="main-navigation" className="rail-toggle" disabled={fc.busy} onClick={() => setMenu(!menu)}>Pages <span aria-hidden="true">{menu ? '−' : '+'}</span></Button><div className="rail-content" id="main-navigation"><p className="rail-title">{segment === 'living' ? 'Living' : 'Investment'}</p><LineSidebar items={navKeys.map(key => ({ key, label: views[key][0] }))} activeKey={fc.route.view} disabled={fc.busy || !fc.setup.ready} onNavigate={key => fc.navigate(key, '', segment)}/></div></aside>}
      <main id="main-content" tabIndex={-1} key={fc.workspace.id} aria-busy={fc.busy || fc.loading}>
        {fc.route.view !== 'overview' && <div className="page-heading"><h1>{views[fc.route.view][0]}</h1>{fc.readonly && <span className="badge">Read only</span>}</div>}
        {fc.readonly && <p className="notice">Archived workspace · records are read-only. Restore it in Settings to make changes.</p>}
        {(fc.busy || fc.loading) && <div className="loading-line" role="status">{fc.busy ? 'Applying operation…' : 'Loading records…'}</div>}
        <div inert={fc.loading || undefined}><StepContent className="page-content" step={`${fc.route.view}/${fc.route.tab}`}><React.Fragment key={`${fc.route.view}/${fc.route.tab}/${blocked}`} ><Suspense fallback={<p className="loading-line" role="status">Loading page…</p>}>{blocked ? <Setup fc={fc}/> : <Page fc={fc}/>}</Suspense></React.Fragment></StepContent></div>
      </main>
      </div>
      <footer className="workbench-footer"><span>Finance Core {SERVICE_VERSION}</span><a href="/THIRD-PARTY-NOTICES.txt" target="_blank" rel="noreferrer">Third-party notices</a></footer>
    </div>}
  </>;
}
