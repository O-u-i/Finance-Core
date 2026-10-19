import React, { useState } from 'react';
import { API_VERSION, SERVICE_VERSION } from '../api.js';
import { Button, Dialog, Field, Panel, ResourceForm, Table, options } from '../components.jsx';
import Setup from './Setup.jsx';
import { Backup } from './Data.jsx';
import ReaderAccess from '../ReaderAccess.jsx';

export function accessScopes(mode) {
  const scopes = { read: ['ledger:read'], write: ['ledger:write'], both: ['ledger:read', 'ledger:write'] }[mode];
  if (!scopes) throw new Error('Choose Read, Write or Both.');
  return scopes;
}

export function tokenStatus(item) {
  return item.revokedAt ? 'Revoked' : item.expiresAt && Date.parse(item.expiresAt) <= Date.now() ? 'Expired' : 'Active';
}

export function PermanentDeleteConfirmation({ target, busy, onClose, onDelete }) {
  const [name, setName] = useState('');
  return <Dialog title={`Delete ${target.kind} permanently`} onClose={onClose} dismissible={!busy}>
    <p className="notice" role="alert">No undo. {target.kind === 'Vault'
      ? 'Removes this quarantined database and its Vault record, and revokes tokens containing this Vault. Backups and exported copies are not deleted. Additional files require manual review; directories are never recursively deleted.'
      : 'Removes this inactive token record and its read grant. It cannot be restored or used again.'}</p>
    <p><strong>{target.name}</strong> · Record ID: {target.id}</p>
    {target.error && <p role="alert" className="notice">{target.error}</p>}
    <p>If a request times out, refresh before retrying: permanent deletion may already have started.</p>
    <form onSubmit={async event => { event.preventDefault(); if (name === target.name && !busy) await onDelete(name); }}>
      <Field label="Type the exact name to confirm"><input required autoComplete="off" value={name} disabled={busy} onChange={event => setName(event.target.value)}/></Field>
      <div className="actions"><Button type="button" disabled={busy} onClick={onClose}>Cancel</Button><Button type="submit" danger disabled={busy || name !== target.name}>Delete permanently</Button></div>
    </form>
  </Dialog>;
}

export default function Settings({ fc }) {
  const [deletion, setDeletion] = useState(null);
  const control = async (api, path, body, method = 'POST') => {
    const result = await api.request(path, { method, body });
    const all = (await api.request('/api/v3/workspaces')).data; fc.setWorkspaces(all);
    const current = all.find((item) => item.id === fc.workspace.id);
    if (!current || current.status === 'quarantined') { await fc.bootstrap(); }
    else if (current) fc.setWorkspace(current);
    return result;
  };
  const undo = () => fc.run(async (api) => {
    const result = await api.request('/api/v3/undo', { method: 'POST', body: { undoToken: fc.controlUndo.undoToken } });
    fc.setControlUndo(null); await fc.bootstrap(); return result;
  }, 'Workspace operation undone.', { write: false, reload: false });
  const active = fc.workspaces.filter((item) => item.status === 'active').map((item) => ({ value: item.id, label: item.displayName }));
  return <>
    <Setup fc={fc} compact/>
    <ReaderAccess fc={fc}/>
    <Backup fc={fc}/>
    <Panel title="Workspaces" description="Each Vault owns one complete finance database. Archive for read-only access or move files to recoverable quarantine." notice="Permanent deletion is available only after quarantine, requires the exact name, and has no undo.">
      <ResourceForm fc={{ ...fc, readonly: false }} fields={[
        ['displayName', 'Workspace name'], ['kind', 'Kind', 'text', options(['personal', 'sandbox'])],
      ]} submitLabel="Create workspace" onSave={(values) => fc.run((api) => control(api, '/api/v3/workspaces', values), 'Workspace created.', { write: false })}/>
      {fc.controlUndo && <div className="notice">Undo available for {fc.controlUndo.operationType}. <Button disabled={fc.busy} onClick={undo}>Undo workspace operation</Button></div>}
      <Table rows={fc.workspaces} columns={[['displayName', 'Name'], ['kind', 'Kind'], ['status', 'Status'], ['actions', 'Actions', (item) => <div className="actions">{item.status !== 'quarantined' ? <><Button disabled={fc.busy} onClick={() => fc.run((api) => control(api, `/api/v3/workspaces/${item.id}`, { status: item.status === 'active' ? 'archived' : 'active' }, 'PATCH'), 'Workspace status updated.', { write: false })}>{item.status === 'active' ? 'Archive' : 'Restore'}</Button><Button danger disabled={fc.busy} onClick={() => { if (confirm('Move this Vault into recoverable quarantine? Files will be preserved.')) fc.run((api) => control(api, `/api/v3/workspaces/${item.id}`, undefined, 'DELETE'), 'Vault quarantined.', { write: false, reload: false }); }}>Quarantine</Button></> : <Button danger disabled={fc.busy} onClick={() => setDeletion({ kind: 'Vault', id: item.id, name: item.displayName })}>Delete permanently</Button>}</div>]]}/>
    </Panel>
    <Panel title="API access" description="Issue a token for a local backend client. Access tokens stay out of browser storage and source code." notice="For non-FRAG clients and sandbox HTTP tests. FRAG connections use the separate read-only form above; Write and Both tokens are not FRAG configurations.">
      <ResourceForm fc={{ ...fc, readonly: false }} fields={[
        ['name', 'Token name'], ['workspaceId', 'Workspace', 'text', active], ['scope', 'Access mode', 'text', [{ value: 'read', label: 'Read · read only' }, { value: 'write', label: 'Write · write only' }, { value: 'both', label: 'Both · read and write' }]],
      ]} submitLabel="Create token" onSave={(values) => fc.run(async (api) => {
        const result = await api.request('/api/v3/access-tokens', { method: 'POST', body: { name: values.name, workspaceIds: [values.workspaceId], scopes: accessScopes(values.scope) } });
        fc.setOneTimeToken(result.token); return result;
      }, 'Token created. Copy it now; it is displayed once.', { write: false })}/>
      {typeof fc.oneTimeToken === 'string' && fc.oneTimeToken && <div className="token-once"><strong>Shown once</strong><code>{fc.oneTimeToken}</code><Button onClick={() => fc.setOneTimeToken('')}>Dismiss token</Button></div>}
    </Panel>
    <Panel title="Issued access" notice="Revoke active tokens before permanent deletion. Revoked or expired token records can be deleted after name confirmation."><Table rows={fc.data.tokens} columns={[['name', 'Name'], ['scopes', 'Access', item=>item.readGrant ? `Financial read · ${item.readGrant.mode}` : item.scopes.join(', ')], ['revokedAt', 'Status', tokenStatus], ['actions', 'Actions', item=>tokenStatus(item) === 'Active' ? <Button danger disabled={fc.busy} onClick={()=>{if(confirm('Revoke this token permanently?')) fc.run(api=>api.request(`/api/v3/access-tokens/${item.id}/revoke`,{method:'POST'}),'Token revoked.',{write:false});}}>Revoke</Button> : <Button danger disabled={fc.busy} onClick={() => setDeletion({ kind: 'token', id: item.id, name: item.name })}>Delete permanently</Button>]]}/></Panel>
    {deletion && <PermanentDeleteConfirmation key={`${deletion.kind}/${deletion.id}`} target={deletion} busy={fc.busy} onClose={() => setDeletion(null)} onDelete={confirmName => fc.run(async api => {
      const isVault = deletion.kind === 'Vault';
      try {
        const result = await api.request(isVault ? `/api/v3/workspaces/${deletion.id}/purge` : `/api/v3/access-tokens/${deletion.id}`, { method: isVault ? 'POST' : 'DELETE', body: { confirmName } });
        setDeletion(null); if (isVault && fc.controlUndo?.workspaceId === deletion.id) fc.setControlUndo(null);
        if (isVault) { const all = (await api.request('/api/v3/workspaces')).data; fc.setWorkspaces(all); }
        return result;
      } catch (error) {
        setDeletion(current => current ? { ...current, error: error.message } : current);
        throw error;
      }
    }, 'Permanently deleted. Audit history is retained.', { write: false })}/>}
    <Panel title="About Finance Core"><dl className="version-list"><dt>Product</dt><dd>{SERVICE_VERSION}</dd><dt>API contract</dt><dd>{API_VERSION}</dd><dt>Ledger schema</dt><dd>{fc.health?.ledgerSchemaVersion}</dd><dt>Registry schema</dt><dd>{fc.health?.registrySchemaVersion}</dd><dt>Session</dt><dd>Local owner · HttpOnly cookie</dd></dl><p>Finance Core owns financial records and deterministic calculations. It does not connect to banks, brokers, live prices or language models.</p><Button disabled={fc.busy} onClick={fc.signOut}>Sign out</Button></Panel>
  </>;
}
