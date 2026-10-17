import React, { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { useFinance, views } from './state.jsx';
import { segmentViews, configurationViews, masterSections, pageSections, pageTabs } from './navigation.js';
import { SERVICE_VERSION } from './api.js';
import { Button, Field, Logo, Panel, Select, Tabs } from './components.jsx';
import BranchedMenu from './BranchedMenu.jsx';
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
const SegmentExport = named(() => import('./pages/SegmentData.jsx'), 'SegmentExport');

function LegacyAssets({ fc }) {
  return <Panel title="Asset register unavailable in this legacy Vault"><p>Schema 2 retains its original accounts, snapshots and plans. Asset ownership and dated valuations require an explicitly reviewed schema migration. No migration or estimated values are applied here.</p><Button onClick={() => fc.navigate('settings')}>Open Settings</Button></Panel>;
}

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
  const [showLoading, setShowLoading] = useState(false);
  const [selection, setSelection] = useState(null), [pendingSection, setPendingSection] = useState(null);
  const previousPage = useRef(fc.route.view);
  useEffect(() => { setMenu(false); }, [fc.route.view]);
  useEffect(() => {
    setShowLoading(false);
    if (!fc.loading || fc.busy) return;
    // Short reads need no flashing toast; aria-busy remains immediate.
    const timer = setTimeout(() => setShowLoading(true),180);
    return () => clearTimeout(timer);
  }, [fc.loading,fc.busy]);
  const segment = fc.route.segment || (['balances','assets','plans','livingreview','livingdata'].includes(fc.route.view) ? 'living' : 'investment');
  const globalPage = configurationViews.includes(fc.route.view);
  const railView = fc.route.view === 'legacyreview' ? 'monthlyreview' : fc.route.view;
  const activityReview = fc.route.view === 'legacyreview' || (fc.route.view === 'monthlyreview' && (!fc.route.segment || fc.migrationRequired));
  const navKeys = segmentViews[segment];
  const Page = fc.migrationRequired && ['balances','livingreview','planning'].includes(fc.route.view) ? Planning
    : fc.migrationRequired && fc.route.view === 'assets' ? LegacyAssets
    : fc.migrationRequired && fc.route.view === 'livingdata' ? SegmentExport
    : fc.route.view === 'monthlyreview' && (!fc.route.segment || fc.migrationRequired) ? MonthlyReview : pages[fc.route.view];
  const blocked = !fc.setup.ready && !configurationViews.includes(fc.route.view);
  const sections = pageSections(activityReview ? 'legacyreview' : fc.route.view,fc.migrationRequired);
  const activeSection = selection?.workspace === fc.workspace?.id && selection?.view === fc.route.view && selection?.tab === fc.route.tab
    ? selection.key : sections.find(item => item.tab && item.tab === (fc.route.tab || sections[0]?.tab))?.key;
  const tabs = pageTabs(fc.route.view,fc.migrationRequired);
  const scrollTo = top => window.scrollTo({top,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  useEffect(() => {
    if (previousPage.current !== fc.route.view && !pendingSection) {
      const heading = document.querySelector('#main-content .page-heading') || document.getElementById('main-content');
      const clearance = (document.querySelector('.workbench-nav')?.getBoundingClientRect().bottom || 0) + 20;
      if (heading && heading.getBoundingClientRect().bottom < clearance) scrollTo(Math.max(0,scrollY + heading.getBoundingClientRect().top - clearance));
    }
    previousPage.current = fc.route.view;
  }, [fc.route.view,pendingSection]);
  const locateSection = item => {
    const node = [...document.querySelectorAll('#main-content [data-section-title]')].find(node => !node.closest('dialog') && (node.dataset.sectionKey === item.key || node.dataset.sectionTitle === item.label));
    if (!node) return false;
    for (let ancestor = node.parentElement; ancestor; ancestor = ancestor.parentElement) if (ancestor.tagName === 'DETAILS') ancestor.open = true;
    const clearance = Math.max(innerHeight / 4, (document.querySelector('.workbench-nav')?.getBoundingClientRect().bottom || 0) + 24);
    scrollTo(Math.max(0, scrollY + node.getBoundingClientRect().top - clearance));
    setSelection({workspace:fc.workspace.id,view:fc.route.view,tab:fc.route.tab,key:item.key});
    return true; // Keep focus on the activated menu button, not on the destination heading.
  };
  useEffect(() => {
    if (!pendingSection || fc.loading) return;
    if (pendingSection.workspace !== fc.workspace?.id || pendingSection.view !== fc.route.view || pendingSection.tab !== fc.route.tab || blocked) { setPendingSection(null); return; }
    const locate = () => { if (locateSection(pendingSection.item)) setPendingSection(null); };
    locate();
    const main = document.getElementById('main-content');
    if (!main) return;
    // Only wait for a lazy destination; mutations never define or rewrite the menu.
    const observer = new MutationObserver(locate); observer.observe(main,{childList:true,subtree:true});
    return () => observer.disconnect();
  }, [pendingSection,fc.route.view,fc.route.tab,fc.workspace?.id,fc.loading,blocked]);
  const selectSection = (key,item,view) => {
    view = item.view || view;
    const tab = item.tab ?? (view === fc.route.view ? fc.route.tab : '');
    if (view === fc.route.view && tab === fc.route.tab && !fc.loading) { setPendingSection(null); locateSection(item); }
    else if (fc.navigate(view,tab,segment,view === fc.route.view ? fc.route.month : '')) setPendingSection({workspace:fc.workspace.id,view,tab,item});
  };
  const configItems = masterSections(fc.migrationRequired);
  const activeMaster = configItems.some(([key]) => key === fc.route.tab) ? fc.route.tab : 'commodities';
  const railItems = fc.route.view === 'master' ? configItems.map(([key,label]) => ({key,label})) : fc.route.view === 'settings' ? sections : navKeys.map(key => ({key,label:views[key][0],children:key === 'monthlyreview' && activityReview ? sections.map(item => ({...item,view:fc.route.view})) : pageSections(key,fc.migrationRequired)}));
  const hasRail = fc.route.view !== 'overview';
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
        <div className="segment-entries">{['investment','living'].map(value => <button key={value} data-segment={value} disabled={fc.busy} aria-current={!globalPage && segment === value ? 'page' : undefined} onClick={() => fc.navigate(value === 'living' ? 'balances' : 'journal','',value)}>{value === 'living' ? 'Living' : 'Investment'}</button>)}</div>
        <div className="global-entries">{configurationViews.filter(key => key !== 'overview').map(key => {
          const ready = key === 'master' ? fc.setup.masterReady : fc.setup.sessionReady && fc.setup.workspaceReady;
          const status = !fc.setup.loaded && !fc.setup.error ? 'checking' : ready ? 'ready' : 'error';
          return <button key={key} data-status={status} disabled={fc.busy} aria-current={fc.route.view === key ? 'page' : undefined} onClick={() => fc.navigate(key)}>{views[key][0]}<span className="configuration-state">{status === 'checking' ? 'Checking' : ready ? 'Ready' : 'Needs attention'}</span></button>;
        })}</div>
      </nav>
      <div className={`workbench-layout${!hasRail ? ' workbench-global' : ''}`}>
      {hasRail && <aside className={`workbench-rail${menu ? ' open' : ''}`}><Button aria-expanded={menu} aria-controls="main-navigation" className="rail-toggle" disabled={fc.busy} onClick={() => setMenu(!menu)}>Pages <span aria-hidden="true">{menu ? '−' : '+'}</span></Button><div className="rail-content" id="main-navigation"><p className="rail-title">{globalPage ? views[fc.route.view][0] : segment === 'living' ? 'Living' : 'Investment'}</p><BranchedMenu items={railItems} activeKey={fc.route.view === 'master' ? activeMaster : fc.route.view === 'settings' ? activeSection : railView} activeSection={activeSection} label={globalPage ? `${views[fc.route.view][0]} sections` : 'Segment pages'} disabled={fc.busy || (!globalPage && !fc.setup.ready)} onSection={selectSection} onNavigate={key => {
        setPendingSection(null);
        if (fc.route.view === 'settings') selectSection(key,sections.find(item => item.key === key),'settings');
        else if (fc.route.view === 'master') fc.navigate('master',key,segment);
        else fc.navigate(key,'',segment);
      }}/></div></aside>}
      <Suspense key={fc.workspace.id} fallback={<main id="main-content" tabIndex={-1} aria-busy="true"><p className="loading-line" role="status">Loading page…</p></main>}>
      <main id="main-content" data-page={fc.route.view} data-tab={fc.route.tab} tabIndex={-1} aria-busy={fc.busy || fc.loading}>
        {fc.route.view !== 'overview' && <div className="page-heading"><h1>{views[fc.route.view][0]}</h1>{fc.readonly && <span className="badge">Read only</span>}</div>}
        {fc.readonly && <p className="notice">Archived workspace · records are read-only. Restore it in Settings to make changes.</p>}
        {fc.migrationRequired && !globalPage && <p className="legacy-vault-notice" role="status">Legacy Vault · original record basis retained. Dated balances, asset ownership and immutable monthly closes require an explicitly reviewed migration.</p>}
        {(fc.busy || (fc.loading && showLoading)) && <div className="loading-line" role="status">{fc.busy ? 'Applying operation…' : 'Loading records…'}</div>}
        {!blocked && tabs.length > 1 && <Tabs items={tabs} value={tabs.some(([key]) => key === fc.route.tab) ? fc.route.tab : tabs[0][0]} disabled={fc.busy} onChange={tab => fc.navigate(fc.route.view,tab,segment)}/>}
        <div inert={fc.loading || undefined} className="page-content">{blocked ? <Setup fc={fc}/> : <Page key={`${fc.route.view}/${fc.route.tab}`} fc={fc} segment={segment}/>}</div>
      </main>
      </Suspense>
      </div>
      <footer className="workbench-footer"><span>Finance Core {SERVICE_VERSION}</span><a href="/THIRD-PARTY-NOTICES.txt" target="_blank" rel="noreferrer">Third-party notices</a></footer>
    </div>}
  </>;
}
