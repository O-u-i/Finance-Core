import React from 'react';
import { Button, Panel } from '../components.jsx';

export default function Setup({ fc, compact = false }) {
  return <Panel sectionKey="configuration" className="setup-panel" title={fc.setup.ready ? 'Workspace configuration' : 'Finish workspace setup'} description="Settings establishes your session and Workspace. Master data supplies currencies and financial accounts.">
    <ul className="setup-checks">
      <li><span className={`status-dot ${fc.setup.sessionReady && fc.setup.workspaceReady ? 'good' : ''}`}/><div><strong>Settings</strong><small>{fc.setup.sessionReady && fc.setup.workspaceReady ? 'Authenticated owner session · Workspace selected' : 'Sign in and choose an available Workspace'}</small></div><Button disabled={fc.busy} onClick={() => fc.navigate('settings')}>Open Settings</Button></li>
      <li><span className={`status-dot ${fc.setup.masterReady ? 'good' : ''}`}/><div><strong>Master data</strong><small>{fc.setup.loaded ? `${fc.setup.currencyCount} active currencies · ${fc.setup.accountCount} active accounts` : 'Checking configuration…'}</small></div><Button disabled={fc.busy} onClick={() => fc.navigate('master')}>Open Master data</Button></li>
    </ul>
    {!fc.setup.ready && <><p>Financial tools unlock when at least two active accounts support the same active currency. Prices are optional for Journal; valuation requires explicit prices.</p><ul>{fc.setup.missing.map(message => <li key={message}>{message}</li>)}</ul></>}
    {!compact && <div className="actions"><Button disabled={fc.busy || fc.loading} onClick={() => fc.refresh()}>Check configuration</Button>
      {fc.workspace.kind === 'sandbox' && <Button disabled={fc.busy || fc.loading || fc.readonly} onClick={() => { if (confirm('Load synthetic data into this empty sandbox? The backend will reject a non-empty sandbox.')) fc.ledger('/demo/load-synthetic', { method: 'POST' }, 'Synthetic example loaded.'); }}>Load synthetic example</Button>}
    </div>}
  </Panel>;
}
