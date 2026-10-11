import React, { useState } from 'react';
import { SegmentExport } from './SegmentData.jsx';
import { downloadPrivate, id, localDate } from '../api.js';
import { checkImportCSV, mapAccountingCSV, csvCommodityIssues, isSingleCurrencyCSV } from '../csv.js';
import { Button, Field, Panel, ResourceForm, RejectDialog, Select, StepContent, Steps, Table, Tabs } from '../components.jsx';

function Import({ fc }) {
  const [format, setFormat] = useState('csv'), [input, setInput] = useState(''), [checked, setChecked] = useState(null), [step, setStep] = useState(0);
  const [confirmed, setConfirmed] = useState(false), [result, setResult] = useState(null);
  const [profile, setProfile] = useState(null), [grouping, setGrouping] = useState(false), [accountMap, setAccountMap] = useState({});
  const [sourceCurrency, setSourceCurrency] = useState('');
  const [groupingRule, setGroupingRule] = useState('balanced'), [datePolicy, setDatePolicy] = useState('same-date');
  const [rejection, setRejection] = useState(null);
  const fileGeneration = React.useRef(0);
  React.useEffect(() => () => { fileGeneration.current++; }, []);
  const change = (value) => { fileGeneration.current++; setInput(value); setProfile(null); setGrouping(false); setSourceCurrency(''); setAccountMap({}); setChecked(null); setStep(0); setConfirmed(false); setResult(null); fc.markDirty(); };
  const check = async () => {
    try {
      if (format === 'json') {
        const payload = JSON.parse(input);
        if (!Array.isArray(payload.drafts) || !payload.drafts.length) throw new Error('JSON must contain a non-empty drafts array.');
        if (payload.drafts.some((draft) => !draft.id || !draft.description || !Array.isArray(draft.postings) || draft.postings.length < 2)) throw new Error('Each draft needs an ID, description and at least two postings.');
        setChecked({ payload, count: payload.drafts.length });
      } else {
        const inspected = checkImportCSV(input);
        if (inspected.kind === 'accounting') {
          setProfile(inspected);
          if (!profile) setAccountMap(Object.fromEntries(inspected.codes.map((code) => [code, fc.data.accounts?.find((item) => item.code === code && item.status === 'active')?.id || ''])));
        }
        const issues = csvCommodityIssues(inspected, fc.data.commodities || [], fc.data.accounts || [], sourceCurrency);
        if (issues.length && !(inspected.kind === 'accounting' && isSingleCurrencyCSV(inspected.source) && !sourceCurrency)) throw Object.assign(new Error('CSV commodity configuration is invalid.'), { code: 'CSV_COMMODITY', reasons: issues });
        if (inspected.kind === 'accounting') {
          let payload = mapAccountingCSV(inspected.source, { groupingConfirmed: grouping, accountMap, accounts: fc.data.accounts || [], commodities: fc.data.commodities || [], prefix: id('csv'), sourceCurrency, groupingRule });
          if (groupingRule === 'balanced') {
            const preview = await fc.run((api, wid) => api.ledger(wid, '/import/accounting-rows/validate', { method: 'POST', body: { rows: payload.rows, groupingConfirmed: true, datePolicy } }), 'Balanced-row preview validated; nothing imported.', { write: false, reload: false });
            if (!preview) { setChecked(null); setStep(1); return; }
            payload = { drafts: preview.drafts };
          }
          setChecked({ payload, count: payload.drafts.length, mapped: true });
        } else setChecked({ payload: input, count: inspected.count });
      }
      setStep(2); setConfirmed(false); fc.setNotice(null);
    } catch (error) { if (error.code === 'CSV_COMMODITY') setRejection(error.reasons || [error.message]); fc.setNotice({ error: true, text: error instanceof SyntaxError ? 'Enter valid JSON before checking the draft structure.' : error.message }); setChecked(null); setStep(1); }
  };
  const submit = async () => {
    if (!checked || !confirmed) return;
    const csv = format === 'csv' && !checked.mapped;
    const payload = await fc.run(async (api, wid) => {
      try { return await api.ledger(wid, csv ? '/import/drafts.csv' : '/import/drafts', { method: 'POST', body: checked.payload, ...(csv ? { headers: { 'Content-Type': 'text/csv' } } : {}) }); }
      catch (error) { if (format === 'csv') setRejection([error.message, ...(error.issues || []).map(issue => `${issue.path || 'Posting'}: ${issue.message || issue.code || 'Invalid configuration'}`)]); throw error; }
    }, 'Drafts validated and imported atomically.');
    if (payload) { fc.clean(); setResult(payload); setStep(3); setConfirmed(false); }
  };
  return <Panel title="Import drafts" description="Import creates unposted drafts. It never posts entries automatically.">
    <Steps labels={['Select input', 'Check structure', 'Confirm import', 'Result']} current={step}/>
    <fieldset disabled={fc.busy || fc.readonly}>
      <StepContent step={step}>
      <div hidden={step >= 2}>
      <Select label="Format" value={format} onChange={(value) => { setFormat(value); change(''); }} options={[{ value: 'json', label: 'JSON' }, { value: 'csv', label: 'CSV' }]}/>
      <Field label="Choose file"><input key={format} type="file" accept={format === 'json' ? '.json,application/json' : '.csv,text/csv'} onChange={async (e) => { const file = e.target.files[0], generation = ++fileGeneration.current; if (file) { fc.markDirty(); try { const content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()); if (generation === fileGeneration.current) change(content); } catch { if (generation === fileGeneration.current) fc.setNotice({ error: true, text: 'Cannot read this file. Use a valid UTF-8 file.' }); } } }}/></Field>
      <Field label={format === 'json' ? 'JSON drafts' : 'CSV input'}><textarea rows={9} value={input} onChange={(e) => change(e.target.value)} placeholder={format === 'json' ? '{"drafts": [...]}' : 'entryId,postingId,accountId,side,units,…'}/></Field>
      {profile && <div className="csv-mapping"><h3>Accounting journal mapping</h3><p>Choose and confirm a row grouping rule. FC validates balanced grouping; parent and reference captions do not determine its boundaries. Source context stays in posting memos. Mixed-currency drafts require explicit rates in the standard FC format.</p>{isSingleCurrencyCSV(profile.source) && <Select label="Source currency (not inferred)" value={sourceCurrency} options={[{ value: '', label: 'Choose a currency' }, ...(fc.data.commodities || []).filter(item => item.kind === 'currency' && item.status === 'active').map(item => ({ value: item.code, label: item.code }))]} onChange={value => { setSourceCurrency(value); fc.markDirty(); }}/>}<label><input type="checkbox" checked={grouping} onChange={(e) => { setGrouping(e.target.checked); fc.markDirty(); }}/> Use this explicit row grouping rule.</label>{<Select label="Row grouping" value={groupingRule} options={[{ value: 'balanced', label: 'FC: consecutive rows until debit equals credit' }, ...(!isSingleCurrencyCSV(profile.source) ? [{ value: 'parent', label: 'A row without a parent begins a draft' }] : []), { value: 'description', label: 'A non-empty description starts a draft' }, { value: 'date', label: 'Consecutive rows with the same date and reference' }, { value: 'same-key', label: 'Consecutive rows with the same date, reference and description' }]} onChange={value => { setGroupingRule(value); setGrouping(false); fc.markDirty(); }}/>} {groupingRule === 'balanced' && <Select label="Date policy" value={datePolicy} options={[{ value: 'same-date', label: 'Require the same date throughout a group' }, { value: 'first-row', label: 'Use first row date; retain source dates in memos' }]} onChange={value => { setDatePolicy(value); setGrouping(false); fc.markDirty(); }}/>}<div className="form-grid">{profile.codes.map((code) => <Select key={code} label={`Source account ${code}`} value={accountMap[code] || ''} options={[{ value: '', label: 'Choose an account' }, ...(fc.data.accounts || []).filter((item) => item.status === 'active').map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` }))]} onChange={(value) => { setAccountMap({ ...accountMap, [code]: value }); fc.markDirty(); }}/>)}</div></div>}
      <Button onClick={check} disabled={!input.trim()}>Check structure</Button>
      </div>
      {step === 2 && <Button onClick={() => { setStep(0); setChecked(null); setConfirmed(false); }}>Edit input</Button>}
      {checked && !result && <div className="confirmation"><p>Structure checked{checked.count !== null ? `: ${checked.count} drafts` : ''}. The backend will validate financial rules and import the entire batch atomically.</p>{checked.mapped && <Table caption="Mapped draft preview" rows={checked.payload.drafts} columns={[["date",'Date'],['description','Description'],['balancingCommodityCode','Currency'],['postings','Postings',(draft)=>draft.postings.length]]}/>}<label><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)}/> Import these drafts into {fc.workspace.displayName}.</label><Button primary disabled={!confirmed} onClick={submit}>Validate and import</Button></div>}
      {result && <div className="notice success" role="status">Import completed: {result.imported ?? 'all'} drafts. Review them in Journal before posting.</div>}
      {result && <Button onClick={() => change('')}>Import another file</Button>}
      </StepContent>
    </fieldset>
    {rejection && <RejectDialog reasons={rejection} onClose={() => setRejection(null)}/>}
  </Panel>;
}

export function Backup({ fc }) {
  const [backup, setBackup] = useState(null), [name, setName] = useState('');
  return <><Panel title="Export & backup" description="Exports are private. Store downloaded files safely and outside Git."><p>Postings CSV includes posted entries only. Unposted imported drafts are included in JSON exports and backups.</p><div className="actions"><Button disabled={fc.busy} onClick={() => downloadPrivate(fc, '/export', 'finance-core-export.json')}>Download JSON export</Button><Button disabled={fc.busy} onClick={() => downloadPrivate(fc, '/export/journal-entries.csv', 'journal-entries-v3.csv', true)}>Download postings CSV</Button><Button primary disabled={fc.busy} onClick={() => downloadPrivate(fc, fc.migrationRequired ? '/backup' : '/vault-backup', fc.migrationRequired ? 'finance-core-legacy-backup-v2.json' : 'finance-core-vault-backup-v3.json')}>{fc.migrationRequired ? 'Download legacy backup (format 2)' : 'Download unified Vault backup (format 3)'}</Button></div></Panel>
    <Panel title="Restore an empty ledger" description="Restore checks the backup format, schema, hash and foreign keys. Format 3 retains immutable histories and has no ordinary undo. Restore only into a new empty Vault. Format 2 is legacy."><fieldset disabled={fc.busy || fc.readonly}><Field label="JSON backup"><input type="file" accept=".json,application/json" onChange={async (event) => { try { const file = event.target.files[0]; if (!file) return; const payload = JSON.parse(await file.text()); setBackup(payload.data || payload); setName(file.name); fc.markDirty(); } catch { setBackup(null); fc.setNotice({ error: true, text: 'Select a valid JSON backup.' }); } }}/></Field>{backup && <p>Selected: {name}</p>}<Button primary disabled={!backup} onClick={async () => { if (!confirm('Restore this backup into the empty ledger?')) return; if (await fc.ledger(fc.migrationRequired ? '/backup/restore' : '/vault-backup/restore', { method: 'POST', body: backup }, 'Backup validated and restored.')) { fc.clean(); setBackup(null); setName(''); } }}>Validate and restore</Button></fieldset></Panel></>;
}

export default function Data({ fc }) {
  const items = [['import', 'Import'], ['backup', 'Segment export'], ['recurring', 'Recurring drafts'], ['batch', 'Atomic batch']];
  const tab = items.some(([key]) => key === fc.route.tab) ? fc.route.tab : 'import';
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
    {tab === 'backup' && <SegmentExport fc={fc} segment="investment"/>}
  </>;
}
