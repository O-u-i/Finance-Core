import React, { useState } from 'react';
import { id, localDate, validationMatches } from '../api.js';
import { Button, Dialog, Empty, Field, Help, ListControls, Panel, RecordRow, Status, StepContent, Steps, Table } from '../components.jsx';
import { orderedRecords } from '../records.js';

const blankPosting = (accounts = [], commodity = 'USD', index = 0) => ({ id: id('posting'), accountId: accounts[index]?.id || accounts[0]?.id || '', side: index ? 'credit' : 'debit', units: '1', commodityCode: commodity, memo: '', cashFlowCategory: 'other', lotAllocations: [] });
const blankDraft = (data) => {
  const commodity = data.commodities?.find((item) => item.status === 'active')?.code || 'USD';
  return { id: id('draft'), date: localDate(), description: '', payee: '', source: 'manual', reference: '', tags: [], balancingCommodityCode: commodity, postings: [0, 1].map((i) => blankPosting(data.accounts, commodity, i)) };
};
const active = (items = []) => items.filter((item) => item.status === 'active');
const pathId = (value) => encodeURIComponent(value);

function JournalRecords({ label, records = [], children }) {
  const [sort, setSort] = useState('date'), [descending, setDescending] = useState(true), [query, setQuery] = useState('');
  const columns = [['date', 'Date'], ['description', 'Description'], ['balancingCommodityCode', 'Currency']];
  const visible = orderedRecords(records, columns, sort, descending, query);
  return <><ListControls label={label} columns={columns} sort={sort} setSort={setSort} descending={descending} setDescending={setDescending} query={query} setQuery={setQuery}/>
    {visible.length ? <div className="record-list">{visible.map(children)}</div> : <Empty>{records.length ? 'No records match these filters.' : `No ${label.toLowerCase()}.`}</Empty>}
  </>;
}

export default function Journal({ fc }) {
  const [editing, setEditing] = useState(false), [detail, setDetail] = useState(null);
  const [editor, setEditor] = useState(() => blankDraft(fc.data));
  const [validation, setValidation] = useState(null);
  const [validated, setValidated] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [step, setStep] = useState(0);
  const [saved, setSaved] = useState(false);
  const edited = React.useRef(false);
  const update = (next) => { edited.current = true; setEditor(next); setValidation(null); setValidated(''); setConfirmed(false); setStep(0); fc.markDirty(); };
  const set = (name, value) => update({ ...editor, [name]: value });
  const posting = (index, name, value) => update({ ...editor, postings: editor.postings.map((item, i) => i === index ? { ...item, [name]: value } : item) });
  const commodities = active(fc.data.commodities), accounts = active(fc.data.accounts);
  // The initial page may mount before its first query resolves. Re-seed only an untouched blank editor.
  React.useEffect(() => { if (!edited.current && !editor.description && !editor.postings[0].accountId && accounts.length) setEditor(blankDraft(fc.data)); }, [accounts.length]);
  const store = async (api, wid) => {
    const exists = saved || fc.data.drafts?.some((item) => item.draft.id === editor.id);
    const result = await api.ledger(wid, `/journal-entry-drafts${exists ? '/' + pathId(editor.id) : ''}`, { method: exists ? 'PUT' : 'POST', body: editor });
    setSaved(true); fc.clean(); return result;
  };
  const save = () => fc.run(store, 'Draft saved.');
  const validate = async () => {
    setStep(1);
    const result = await fc.run(async (api, wid) => {
      await store(api, wid);
      return api.ledger(wid, `/journal-entry-drafts/${pathId(editor.id)}/validate`, { method: 'POST' });
    }, 'Draft checked on the backend.');
    if (result) { setValidation(result); setValidated(JSON.stringify(editor)); setStep(result.valid ? 2 : 1); setConfirmed(false); }
  };
  const canPost = validation?.valid && validationMatches(editor, validated) && confirmed;
  const post = async () => {
    if (!canPost) return;
    const result = await fc.run(async (api, wid) => {
      // Posting revalidates the saved aggregate on the backend. Do not retry automatically.
      return api.ledger(wid, `/journal-entry-drafts/${pathId(editor.id)}/post`, { method: 'POST' });
    }, 'Entry posted. It is now immutable.');
    if (result) { fc.clean(); setStep(3); setValidation(null); setValidated(''); setConfirmed(false); setSaved(false); setEditor(blankDraft(fc.data)); }
  };
  const openDraft = (draft) => { if (!fc.canLeave()) return; edited.current = true; setEditor(structuredClone(draft)); setSaved(true); setValidation(null); setValidated(''); setConfirmed(false); setStep(0); fc.clean(); setEditing(true); };
  const closeEditor = () => { if (fc.canLeave()) { fc.clean(); setEditing(false); } };
  return <>
    <div className="journal-tools actions"><Button primary disabled={fc.busy || fc.readonly} onClick={() => { if (fc.canLeave()) { setEditor(blankDraft(fc.data)); setSaved(false); setValidation(null); setValidated(''); setConfirmed(false); setStep(0); fc.clean(); setEditing(true); } }}>New draft</Button>{!fc.migrationRequired && <Button disabled={fc.busy} onClick={() => fc.navigate('master', 'opening', 'investment')}>Opening balances</Button>}<Button disabled={fc.busy} onClick={() => fc.navigate('data', 'import')}>Import CSV / JSON</Button><Button disabled={fc.busy} onClick={() => fc.navigate('data', 'backup')}>Export records</Button><Button disabled={fc.busy} onClick={() => fc.navigate('taccounts')}>View T-accounts</Button></div>
    {editing && <Dialog title="Journal draft" dismissible={!fc.busy} onClose={closeEditor}>
    <Steps labels={['Edit draft', 'Validate', 'Confirm', 'Posted']} current={step}/>
      <form id="journal-editor" onSubmit={(event) => { event.preventDefault(); save(); }}>
        <fieldset disabled={fc.busy || fc.readonly}>
          <StepContent step={step}>
          <div hidden={step >= 2}>
          <div className="form-grid">
            <Field label="Date" type="date" value={editor.date} required onChange={(e) => set('date', e.target.value)}/>
            <Field label="Description" value={editor.description} required onChange={(e) => set('description', e.target.value)}/>
            <Field label="Payee" value={editor.payee} onChange={(e) => set('payee', e.target.value)}/>
            <Field label="Balancing commodity"><select value={editor.balancingCommodityCode} onChange={(e) => set('balancingCommodityCode', e.target.value)}>{commodities.map((item) => <option key={item.code}>{item.code}</option>)}</select></Field>
            <Field label="Source" value={editor.source} onChange={(e) => set('source', e.target.value)}/>
            <Field label="Reference" value={editor.reference} onChange={(e) => set('reference', e.target.value)}/>
            <Field label={<>Tags <Help label="Tags">Comma separated. Living reconciliation uses personal-transfer:in:CNY or personal-transfer:out:CNY.</Help></>} value={editor.tags.join(', ')} onChange={e => set('tags',e.target.value.split(',').map(value => value.trim()).filter(Boolean))}/>
          </div>
          {!accounts.length && <p className="notice">Add active accounts and commodities in Master data before creating a draft.</p>}
          <div className="postings">{editor.postings.map((item, index) => <div className="posting" key={item.id}>
            <div className="posting-title"><h3>Posting {index + 1}</h3><Button type="button" disabled={editor.postings.length <= 2} onClick={() => update({ ...editor, postings: editor.postings.filter((_, i) => i !== index) })}>Remove</Button></div>
            <div className="form-grid">
              <Field label="Account"><select value={item.accountId} onChange={(e) => posting(index, 'accountId', e.target.value)}><option value="">Select account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.code} · {account.name}</option>)}</select></Field>
              <Field label="Side"><select value={item.side} onChange={(e) => posting(index, 'side', e.target.value)}><option value="debit">Debit</option><option value="credit">Credit</option></select></Field>
              <Field label="Units" value={item.units} inputMode="decimal" required onChange={(e) => posting(index, 'units', e.target.value)}/>
              <Field label="Commodity"><select value={item.commodityCode} onChange={(e) => posting(index, 'commodityCode', e.target.value)}>{commodities.map((commodity) => <option key={commodity.code}>{commodity.code}</option>)}</select></Field>
              <Field label="Valuation rate" inputMode="decimal" value={item.valuationRate || ''} placeholder="1 for base commodity" onChange={(e) => posting(index, 'valuationRate', e.target.value || undefined)}/>
              <Field label="Rate type"><select value={item.rateType || ''} onChange={(e) => posting(index, 'rateType', e.target.value || undefined)}><option value="">Automatic</option>{['exchange', 'price', 'cost'].map((value) => <option key={value}>{value}</option>)}</select></Field>
              <Field label="Cash flow category"><select value={item.cashFlowCategory} onChange={(e) => posting(index, 'cashFlowCategory', e.target.value)}>{['income', 'expense', 'investment', 'financing', 'transfer', 'other'].map((value) => <option key={value}>{value}</option>)}</select></Field>
              <Field label="Note" value={item.memo || ''} onChange={(e) => posting(index, 'memo', e.target.value)}/>
              <Field label="Lot action"><select value={item.lotAction || ''} onChange={(e) => update({ ...editor, postings: editor.postings.map((p, i) => i === index ? { ...p, lotAction: e.target.value || undefined, lotId: undefined, lotAllocations: [] } : p) })}><option value="">None</option><option value="acquire">Acquire</option><option value="dispose">Dispose</option></select></Field>
              {item.lotAction === 'acquire' && <Field label="New lot ID" value={item.lotId || ''} required onChange={(e) => posting(index, 'lotId', e.target.value)}/>}
              {item.lotAction === 'dispose' && <Field label="Allocations (lotId:units, …)" value={(item.lotAllocations || []).map((p) => `${p.lotId}:${p.units}`).join(',')} required onChange={(e) => posting(index, 'lotAllocations', e.target.value.split(',').filter(Boolean).map((part) => { const [lotId, units = ''] = part.split(':'); return { lotId: lotId.trim(), units: units.trim() }; }))}/>}
            </div>
          </div>)}</div>
          <div className="actions"><Button type="button" onClick={() => update({ ...editor, postings: [...editor.postings, blankPosting(accounts, editor.balancingCommodityCode)] })}>Add posting</Button><Button type="submit">Save draft</Button><Button type="button" primary onClick={validate} disabled={!accounts.length || !editor.description.trim()}>Validate draft</Button></div>
          </div>
          {step === 2 && <div className="review-summary"><h3>{editor.description}</h3><p>{editor.date} · {editor.postings.length} postings · {editor.balancingCommodityCode}</p><Table rows={editor.postings} columns={[["accountId", 'Account', (p) => accounts.find((a) => a.id === p.accountId)?.name || p.accountId], ['side', 'Side'], ['units', 'Units'], ['commodityCode', 'Commodity']]}/><Button type="button" onClick={() => { setStep(0); setValidation(null); setValidated(''); setConfirmed(false); }}>Edit draft</Button></div>}
          {validation && <div className={`validation ${validation.valid ? 'success' : 'error'}`} role="status"><h3>{validation.valid ? 'Validation passed' : 'Validation failed'}</h3>{validation.preview && <p>Debit {validation.preview.debitTotal} · Credit {validation.preview.creditTotal} · Difference {validation.preview.difference} <Help label="Difference">Debit total minus Credit total.</Help></p>}{validation.issues?.map((issue, index) => <p key={index}>{issue.path}: {issue.message}</p>)}</div>}
          {validation?.valid && <div className="confirmation"><label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}/> I reviewed this entry. Posting is permanent; corrections require a linked reversal.</label><Button type="button" primary disabled={!canPost} onClick={post}>Confirm and post</Button></div>}
          {step === 3 && <div className="step-result" role="status"><span aria-hidden="true">✓</span><h3>Entry posted</h3><p>The entry is immutable. Find it in the posted journal below.</p><Button type="button" primary onClick={() => setStep(0)}>Record another entry</Button></div>}
          </StepContent>
        </fieldset>
      </form>
    </Dialog>}
    <Panel title="Unposted drafts">
      <JournalRecords label="Unposted drafts" records={fc.data.drafts?.map(item => item.draft)}>{draft => <RecordRow key={draft.id} title={draft.description} meta={<>{draft.date} · {draft.balancingCommodityCode} <Help label="Postings">{`${draft.postings.length} postings. Not included in the posted ledger.`}</Help></>} status={<Status state="warning">Draft</Status>} actions={<><Button disabled={fc.busy} onClick={() => openDraft(draft)}>Review</Button><Button danger disabled={fc.busy || fc.readonly} onClick={() => { if (confirm('Delete this unposted draft?')) fc.ledger(`/journal-entry-drafts/${pathId(draft.id)}`, { method: 'DELETE' }, 'Draft deleted.'); }}>Delete</Button></>}/>}</JournalRecords>
    </Panel>
    <Panel title="Posted journal">
      <JournalRecords label="Posted journal" records={fc.data.entries}>{entry => <RecordRow key={entry.id} title={entry.description} meta={<>{entry.date} · {entry.balancingCommodityCode} · Immutable</>} status={<Status state={entry.reversalOf ? 'warning' : 'success'}>{entry.reversalOf ? 'Linked reversal' : 'Posted'}</Status>} actions={<><Button disabled={fc.busy} onClick={() => setDetail(entry)}>Details</Button>{!entry.reversalOf && <Button danger disabled={fc.busy || fc.readonly} onClick={() => { if (confirm('Create a linked reversal? The original entry will remain.')) fc.ledger(`/journal-entries/${pathId(entry.id)}/reverse`, { method: 'POST' }, 'Linked reversal created.'); }}>Reverse</Button>}</>}/>}</JournalRecords>
    </Panel>
    {detail && <Dialog title={detail.description} onClose={() => setDetail(null)}><div className="detail-context"><Status>Read only · Immutable</Status><span>{detail.date}</span></div><Table caption="Journal postings" rows={detail.postings} columns={[["accountId", 'Account', posting => accounts.find(account => account.id === posting.accountId)?.name || posting.accountId], ['side', 'Side'], ['units', 'Units'], ['commodityCode', 'Commodity'], ['valuationAmount', 'Valuation'], ['memo', 'Note']]}/></Dialog>}
  </>;
}
