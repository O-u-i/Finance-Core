import React, { useEffect, useState } from 'react';
import { Button, Field, Help, Panel } from './components.jsx';

export function connectionConfiguration(created, apiUrl, uiUrl) {
  const local = value => {
    const url = new URL(value);
    if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname) || !url.port || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error('Use a local HTTP address with an explicit port.');
    return url.origin;
  };
  const { workspaceIds, scopes, readGrant } = created.data;
  if (!readGrant || workspaceIds.length !== 1 || scopes.length !== 1 || scopes[0] !== 'ledger:read' || typeof created.token !== 'string' || /\s/.test(created.token)) throw new Error('A dedicated read-only connection is required.');
  return `FINANCE_CORE_PLUGIN_API_URL=${local(apiUrl)}\nFINANCE_CORE_PLUGIN_UI_URL=${local(uiUrl)}\nFINANCE_CORE_PLUGIN_READ_TOKEN=${created.token}\nFINANCE_CORE_PLUGIN_RECORDS_JSON=${JSON.stringify({[workspaceIds[0]]:[]})}\n`;
}

export default function ReaderAccess({ fc }) {
  const [wid, setWid] = useState(fc.workspace?.id || '');
  const [mode, setMode] = useState('all');
  const [name, setName] = useState('FRAG read access');
  const [items, setItems] = useState([]), [selected, setSelected] = useState([]);
  const [error, setError] = useState(''), [loading, setLoading] = useState(false), [copied, setCopied] = useState(false);
  const apiUrl = typeof __FC_API_URL__ === 'string' ? __FC_API_URL__ : 'http://127.0.0.1:8788';
  useEffect(() => {
    setItems([]); setSelected([]); setError(''); setLoading(false);
    if (mode !== 'selected' || !wid) return;
    const controller = new AbortController(); setLoading(true);
    fc.client.ledger(wid, '/reader/catalog', {signal:controller.signal}).then(value => {
      if (!controller.signal.aborted) setItems(value.data.items);
    }).catch(() => { if (!controller.signal.aborted) setError('Cannot load financial items. Check this Vault and retry.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [wid, mode, fc.client]);
  const once = fc.oneTimeToken && typeof fc.oneTimeToken === 'object' ? fc.oneTimeToken : null;
  async function create(event) {
    event.preventDefault(); setError(''); setCopied(false);
    await fc.run(async api => {
      const result = await api.request('/api/v3/access-tokens', {method:'POST',body:{name,
        workspaceIds:[wid],scopes:['ledger:read'],readGrant:{mode,itemIds:mode === 'selected' ? selected : []}}});
      // Retain the one-time result before the ordinary post-write list refresh can fail.
      try {
        const configuration = connectionConfiguration(result, apiUrl, window.location.origin);
        fc.setOneTimeToken({configuration,workspaceId:result.data.workspaceIds[0],readGrant:result.data.readGrant});
      } catch {
        fc.setOneTimeToken(result.token); setError('Token created, but local connection addresses need review. The token is shown in Advanced API access below.');
      }
      return result;
    }, 'Read-only connection created. Copy its configuration now.', {write:false});
  }
  return <Panel title="Connect FRAG" description="FC sets the maximum readable range. FRAG can select a smaller subset. All includes future financial items inside this Vault, never other Vaults, management or writes.">
    <form onSubmit={create}>
      <Field label="Vault"><select required value={wid} disabled={fc.busy} onChange={e=>setWid(e.target.value)}>
        <option value="">Choose a Vault</option>{fc.workspaces.filter(w=>w.status==='active').map(w=><option key={w.id} value={w.id}>{w.displayName} · {w.kind}</option>)}
      </select></Field>
      <Field label="Connection name"><input required value={name} maxLength={120} disabled={fc.busy} onChange={e=>setName(e.target.value)}/></Field>
      <Field label="Readable range"><select value={mode} disabled={fc.busy} onChange={e=>setMode(e.target.value)}>
        <option value="all">All financial data in this Vault · including future items</option>
        <option value="living">Living · including future items</option><option value="investment">Investment · including future items</option>
        <option value="selected">Specific accounts or data items</option>
      </select></Field>
      {mode==='selected' && <fieldset><legend>Accounts and data items<Help>Only checked items are authorized. Whole-Journal or whole-Vault reports explicitly include their full aggregate scope. Notes, source text and management data are excluded.</Help></legend>
        {loading && <p role="status">Loading item names…</p>}{items.map(item=><label className="check" key={item.id}><input type="checkbox" disabled={fc.busy} checked={selected.includes(item.id)} onChange={e=>setSelected(e.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id))}/>{item.label} · {item.segment || 'whole Vault'} · {item.kind}</label>)}
      </fieldset>}
      <p>Read only. No financial records are read when this connection is created.</p>
      <Button primary disabled={fc.busy || loading || !wid || (mode==='selected' && !selected.length)}>Create FRAG connection</Button>
    </form>
    {error && <p role="alert" className="notice">{error}</p>}
    {once && <section className="token-once"><strong>Connection configuration · shown once</strong>
      <p className="notice">Contains a secret token. Copy locally; never share it in chat, screenshots or Git.</p>
      <textarea aria-label="FRAG connection configuration" readOnly rows={7} value={once.configuration}/>
      <div className="actions"><Button onClick={async()=>{try{await navigator.clipboard.writeText(once.configuration);setCopied(true);}catch{setError('Copy unavailable. Select the configuration text and copy it manually.');}}}>Copy FRAG configuration</Button>
        <Button onClick={()=>fc.setOneTimeToken('')}>Dismiss configuration</Button></div>
      {copied && <p role="status">Copied. In VS Code, run FRAG: Connect Finance Core.</p>}
    </section>}
  </Panel>;
}
