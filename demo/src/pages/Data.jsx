import React, { useState } from 'react';
import { id, localDate } from '../api.js';
import { Button, Field, Panel, ResourceForm, Select, Steps, Table, Tabs } from '../components.jsx';

function Import({ fc }) {
  const [format, setFormat] = useState('json'), [input, setInput] = useState(''), [checked, setChecked] = useState(null), [step, setStep] = useState(0);
  const [confirmed, setConfirmed] = useState(false), [result, setResult] = useState(null);
  const change = (value) => { setInput(value); setChecked(null); setStep(0); setConfirmed(false); setResult(null); fc.markDirty(); };
  const check = () => {
    try {
      if (format === 'json') {
        const payload = JSON.parse(input);
        if (!Array.isArray(payload.drafts) || !payload.drafts.length) throw new Error('JSON must contain a non-empty drafts array.');
        if (payload.drafts.some((draft) => !draft.id || !draft.description || !Array.isArray(draft.postings) || draft.postings.length < 2)) throw new Error('Each draft needs an ID, description and at least two postings.');
        setChecked({ payload, count: payload.drafts.length });
      } else {
        const header = input.split(/\r?\n/)[0].split(',');
        if (!['entryId', 'postingId', 'accountId', 'side', 'units'].every((name) => header.includes(name))) throw new Error('CSV header must include entryId, postingId, accountId, side and units.');
        if (input.trim().split(/\r?\n/).length < 2) throw new Error('CSV has no data rows.');
        setChecked({ payload: input, count: null });
      }
      setStep(2); setConfirmed(false); fc.setNotice(null);
    } catch (error) { fc.setNotice({ error: true, text: error instanceof SyntaxError ? 'Enter valid JSON before checking the draft structure.' : error.message }); setChecked(null); setStep(1); }
  };
  const submit = async () => {
    if (!checked || !confirmed) return;
    const payload = await fc.ledger(format === 'json' ? '/import/drafts' : '/import/drafts.csv', { method: 'POST', body: checked.payload, ...(format === 'csv' ? { headers: { 'Content-Type': 'text/csv' } } : {}) }, 'Drafts validated and imported atomically.');
    if (payload) { fc.clean(); setResult(payload); setStep(3); setConfirmed(false); }
  };
  return <Panel title="Import drafts" description="Import creates unposted drafts. It never posts entries automatically.">
    <Steps labels={['Select input', 'Check structure', 'Confirm import', 'Result']} current={step}/>
    <fieldset disabled={fc.busy || fc.readonly}>
      <Select label="Format" value={format} onChange={(value) => { setFormat(value); change(''); }} options={[{ value: 'json', label: 'JSON' }, { value: 'csv', label: 'CSV' }]}/>
      <Field label="Choose file"><input key={format} type="file" accept={format === 'json' ? '.json,application/json' : '.csv,text/csv'} onChange={async (e) => { const file = e.target.files[0]; if (file) { try { change(await file.text()); } catch { fc.setNotice({ error: true, text: 'Cannot read this file.' }); } } }}/></Field>
      <Field label={format === 'json' ? 'JSON drafts' : 'CSV input'}><textarea rows={9} value={input} onChange={(e) => change(e.target.value)} placeholder={format === 'json' ? '{"drafts": [...]}' : 'entryId,postingId,accountId,side,units,…'}/></Field>
      <Button onClick={check} disabled={!input.trim()}>Check structure</Button>
      {checked && !result && <div className="confirmation"><p>Structure checked{checked.count !== null ? `: ${checked.count} drafts` : ''}. The backend will validate financial rules and import the entire batch atomically.</p><label><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)}/> Import these drafts into {fc.workspace.displayName}.</label><Button primary disabled={!confirmed} onClick={submit}>Validate and import</Button></div>}
      {result && <div className="notice success" role="status">Import completed: {result.imported ?? 'all'} drafts. Review them in Journal before posting.</div>}
    </fieldset>
  </Panel>;
}

function Backup({ fc }) {
  const [backup, setBackup] = useState(null), [name, setName] = useState('');
  const href = (path) => `/api/v3/workspaces/${encodeURIComponent(fc.workspace.id)}${path}`;
  return <><Panel title="Export & backup" description="Exports are private. Store downloaded files safely and outside Git."><div className="actions"><a className="button" href={href('/export')} target="_blank" rel="noreferrer">Open JSON export</a><a className="button" href={href('/export/journal-entries.csv')}>Download postings CSV</a><a className="button primary" href={href('/backup')} target="_blank" rel="noreferrer">Open SHA-256 backup</a></div></Panel>
    <Panel title="Restore an empty ledger" description="Restore checks the backup format, schema, hash and foreign keys. Undo is available afterward."><fieldset disabled={fc.busy || fc.readonly}><Field label="JSON backup"><input type="file" accept=".json,application/json" onChange={async (event) => { try { const file = event.target.files[0]; if (!file) return; const payload = JSON.parse(await file.text()); setBackup(payload.data || payload); setName(file.name); fc.markDirty(); } catch { setBackup(null); fc.setNotice({ error: true, text: 'Select a valid JSON backup.' }); } }}/></Field>{backup && <p>Selected: {name}</p>}<Button primary disabled={!backup} onClick={async () => { if (!confirm('Restore this backup into the empty ledger?')) return; if (await fc.ledger('/backup/restore', { method: 'POST', body: backup }, 'Backup validated and restored.')) { fc.clean(); setBackup(null); setName(''); } }}>Validate and restore</Button></fieldset></Panel></>;
}

export default function Data({ fc }) {
  const items = [['recurring', 'Recurring drafts'], ['import', 'Import'], ['batch', 'Atomic batch'], ['backup', 'Export & backup']];
  const tab = items.some(([key]) => key === fc.route.tab) ? fc.route.tab : 'recurring';
  const drafts = (fc.data.drafts || []).map(({ draft }) => ({ value: draft.id, label: draft.description }));
  const [batch, setBatch] = useState('');
  return <><Tabs items={items} value={tab} onChange={(value) => fc.navigate('data', value)}/>
    {tab === 'recurring' && <Panel title="Recurring draft templates" description="Choose a saved Journal draft as the template. Due dates generate drafts, never posted facts." action={<Button disabled={fc.busy || fc.readonly} onClick={() => fc.ledger('/recurring-entry-rules/generate-due', { method: 'POST', body: { asOf: localDate() } }, 'Due drafts generated.')}>Generate due drafts</Button>}>
      {!drafts.length && <p>Save a draft in Journal to create your first template.</p>}
      <ResourceForm fc={fc} initial={{ dayOfMonth: 1, startDate: localDate() }} fields={[
        ['name', 'Name'], ['draftId', 'Saved draft', 'text', drafts], ['dayOfMonth', 'Day of month', 'number'], ['startDate', 'Start date', 'date'],
      ]} submitLabel="Save template" onSave={(values) => {
        const original = fc.data.drafts?.find(({ draft }) => draft.id === values.draftId)?.draft;
        if (!original) { fc.setNotice({ error: true, text: 'Choose a saved draft first.' }); return false; }
        const ruleId = id('rule'), template = structuredClone(original); template.id = `${ruleId}-template`;
        template.postings = template.postings.map((posting, index) => ({ ...posting, id: `${template.id}-${index}` }));
        return fc.ledger('/recurring-entry-rules', { method: 'POST', body: { id: ruleId, name: values.name, enabled: true, frequency: 'monthly', dayOfMonth: Number(values.dayOfMonth), startDate: values.startDate, template, generatedPeriods: [] } }, 'Recurring template saved.');
      }}/><Table rows={fc.data.recurring} columns={[['name', 'Name'], ['dayOfMonth', 'Day'], ['startDate', 'Start date'], ['enabled', 'Status', (item) => item.enabled ? 'Enabled' : 'Disabled'], ['actions', 'Actions', (item) => <div className="actions"><Button disabled={fc.busy || fc.readonly} onClick={() => fc.ledger(`/recurring-entry-rules/${encodeURIComponent(item.id)}`, { method: 'PUT', body: { ...item, enabled: !item.enabled } }, 'Rule updated.')}>{item.enabled ? 'Disable' : 'Enable'}</Button><Button danger disabled={fc.busy || fc.readonly} onClick={() => { if (confirm('Delete this recurring rule?')) fc.ledger(`/recurring-entry-rules/${encodeURIComponent(item.id)}`, { method: 'DELETE' }, 'Rule deleted.'); }}>Delete</Button></div>]]}/>
    </Panel>}
    {tab === 'import' && <Import fc={fc}/>}
    {tab === 'batch' && <Panel title="Atomic mutable batch" description="Only commodities, accounts, price quotes and drafts. Posting and reversal remain separate operations."><fieldset disabled={fc.busy || fc.readonly}><Field label="Batch JSON"><textarea rows={10} value={batch} onChange={(e) => { setBatch(e.target.value); fc.markDirty(); }} placeholder='{"commodities":[],"accounts":[],"drafts":[]}'/></Field><Button primary disabled={!batch.trim()} onClick={async () => { try { const body = JSON.parse(batch); if (confirm('Validate and execute this mutable batch atomically?')) { if (await fc.ledger('/batch', { method: 'POST', body }, 'Mutable batch completed atomically.')) { fc.clean(); setBatch(''); } } } catch { fc.setNotice({ error: true, text: 'Batch must be valid JSON.' }); } }}>Validate and execute</Button></fieldset></Panel>}
    {tab === 'backup' && <Backup fc={fc}/>}
  </>;
}
