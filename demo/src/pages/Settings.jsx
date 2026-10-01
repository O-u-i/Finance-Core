import React from 'react';
import { API_VERSION, SERVICE_VERSION } from '../api.js';
import { Button, Panel, ResourceForm, Table } from '../components.jsx';
import { options } from './Master.jsx';

export default function Settings({ fc }) {
  const control = async (api, path, body, method = 'POST') => {
    const result = await api.request(path, { method, body });
    const all = (await api.request('/api/v3/workspaces')).data; fc.setWorkspaces(all);
    const current = all.find((item) => item.id === fc.workspace.id);
    if (current?.status === 'quarantined') { await fc.bootstrap(); }
    else if (current) fc.setWorkspace(current);
    return result;
  };
  const undo = () => fc.run(async (api) => {
    const result = await api.request('/api/v3/undo', { method: 'POST', body: { undoToken: fc.controlUndo.undoToken } });
    fc.setControlUndo(null); await fc.bootstrap(); return result;
  }, 'Workspace operation undone.', { write: false, reload: false });
  const active = fc.workspaces.filter((item) => item.status === 'active').map((item) => ({ value: item.id, label: item.displayName }));
  return <>
    <Panel title="Workspaces" description="Each Vault owns one complete finance database. Archive for read-only access or move files to recoverable quarantine.">
      <ResourceForm fc={{ ...fc, readonly: false }} fields={[
        ['displayName', 'Workspace name'], ['kind', 'Kind', 'text', options(['personal', 'sandbox'])],
      ]} submitLabel="Create workspace" onSave={(values) => fc.run((api) => control(api, '/api/v3/workspaces', values), 'Workspace created.', { write: false })}/>
      {fc.controlUndo && <div className="notice">Undo available for {fc.controlUndo.operationType}. <Button disabled={fc.busy} onClick={undo}>Undo workspace operation</Button></div>}
      <Table rows={fc.workspaces} columns={[['displayName', 'Name'], ['kind', 'Kind'], ['status', 'Status'], ['actions', 'Actions', (item) => <div className="actions">{item.status !== 'quarantined' && <><Button disabled={fc.busy} onClick={() => fc.run((api) => control(api, `/api/v3/workspaces/${item.id}`, { status: item.status === 'active' ? 'archived' : 'active' }, 'PATCH'), 'Workspace status updated.', { write: false })}>{item.status === 'active' ? 'Archive' : 'Restore'}</Button><Button danger disabled={fc.busy} onClick={() => { if (confirm('Move this Vault into recoverable quarantine? Files will be preserved.')) fc.run((api) => control(api, `/api/v3/workspaces/${item.id}`, undefined, 'DELETE'), 'Vault quarantined.', { write: false, reload: false }); }}>Quarantine</Button></>}</div>]]}/>
    </Panel>
    <Panel title="API access" description="Issue a token for a local backend client. Access tokens stay out of browser storage and source code.">
      <ResourceForm fc={{ ...fc, readonly: false }} fields={[
        ['name', 'Token name'], ['workspaceId', 'Workspace', 'text', active], ['scope', 'Scope', 'text', [{ value: 'ledger:read', label: 'Read only' }, { value: 'ledger:write', label: 'Read and write' }]],
      ]} submitLabel="Create token" onSave={(values) => fc.run(async (api) => {
        const result = await api.request('/api/v3/access-tokens', { method: 'POST', body: { name: values.name, workspaceIds: [values.workspaceId], scopes: values.scope === 'ledger:write' ? ['ledger:read', 'ledger:write'] : ['ledger:read'] } });
        fc.setOneTimeToken(result.token); return result;
      }, 'Token created. Copy it now; it is displayed once.', { write: false })}/>
      {fc.oneTimeToken && <div className="token-once"><strong>Shown once</strong><code>{fc.oneTimeToken}</code><Button onClick={() => fc.setOneTimeToken('')}>Dismiss token</Button></div>}
      <Table rows={fc.data.tokens} columns={[['name', 'Name'], ['scopes', 'Scopes', (item) => item.scopes.join(', ')], ['revokedAt', 'Status', (item) => item.revokedAt ? 'Revoked' : 'Active'], ['actions', 'Actions', (item) => !item.revokedAt && <Button danger disabled={fc.busy} onClick={() => { if (confirm('Revoke this token permanently?')) fc.run((api) => api.request(`/api/v3/access-tokens/${item.id}/revoke`, { method: 'POST' }), 'Token revoked.', { write: false }); }}>Revoke</Button>]]}/>
    </Panel>
    <Panel title="About Finance Core"><dl className="version-list"><dt>Product</dt><dd>{SERVICE_VERSION}</dd><dt>API contract</dt><dd>{API_VERSION}</dd><dt>Ledger schema</dt><dd>{fc.health?.ledgerSchemaVersion}</dd><dt>Registry schema</dt><dd>{fc.health?.registrySchemaVersion}</dd><dt>Session</dt><dd>Local owner · HttpOnly cookie</dd></dl><p>Finance Core owns financial records and deterministic calculations. It does not connect to banks, brokers, live prices or language models.</p><Button disabled={fc.busy} onClick={fc.signOut}>Sign out</Button></Panel>
  </>;
}
