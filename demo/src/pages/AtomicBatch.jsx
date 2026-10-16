import React, { useState } from 'react';
import { id, localDate } from '../api.js';
import { Button, Field, Panel, Select, Table } from '../components.jsx';

const types = [
  { value: 'commodities', label: 'New commodity' }, { value: 'accounts', label: 'New Investment account' },
  { value: 'priceQuotes', label: 'New explicit price' }, { value: 'drafts', label: 'New draft from a saved template' },
];

export default function AtomicBatch({ fc }) {
  const [type, setType] = useState('commodities'), [version, setVersion] = useState(0);
  const [entryDirty, setEntryDirty] = useState(false), [changes, setChanges] = useState([]);
  const commodities = [...(fc.data.commodities || []), ...changes.filter(item => item.type === 'commodities').map(item => item.payload)];
  const codes = [...new Set(commodities.map(item => item.code))].map(value => ({ value, label: value }));
  const drafts = (fc.data.drafts || []).map(item => item.draft);
  const stage = event => {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget));
    let payload;
    if (type === 'commodities') payload = { ...values, code: values.code.trim().toUpperCase(), scale: Number(values.scale), status: 'active' };
    if (type === 'accounts') payload = { ...values, id: id('account'), allowedCommodityCodes: values.allowedCommodityCodes.split(',').map(code => code.trim()).filter(Boolean), status: 'active' };
    if (type === 'priceQuotes') payload = { ...values, id: id('quote'), asOf: new Date(values.asOf).toISOString() };
    if (type === 'drafts') {
      const template = drafts.find(item => item.id === values.draftId);
      if (!template) return;
      payload = { ...structuredClone(template), id: id('draft'), description: values.description, date: values.date };
      payload.postings = payload.postings.map((item, index) => ({ ...item, id: `${payload.id}-${index}` }));
    }
    const key = `${type}/${payload.code || payload.id}`;
    if (changes.some(item => item.key === key)) { fc.setNotice({ error: true, text: 'This new code is already staged. Remove it before restaging.' }); return; }
    setChanges(current => [...current, { key, type, label: payload.name || payload.description || `${payload.commodityCode} / ${payload.quoteCommodityCode}`, payload }]);
    fc.clean('batch-entry'); fc.markDirty('atomic-batch'); setEntryDirty(false); setVersion(value => value + 1);
  };
  return <Panel title="Atomic batch creation" description="Stage new records without writing JSON. FC creates all staged records together or none. This endpoint cannot edit existing records; use Master data or Journal for edits. Living accounts are registered in Master data.">
    <Select label="New record type" value={type} options={types} disabled={fc.busy || fc.readonly} onChange={next => {
      if (entryDirty && !confirm('Discard these unstaged fields? Already staged records will be kept.')) return;
      fc.clean('batch-entry'); setEntryDirty(false); setType(next); setVersion(value => value + 1);
    }}/>
    <form className="resource-form" key={`${type}/${version}`} onChangeCapture={() => { fc.markDirty('batch-entry'); setEntryDirty(true); }} onSubmit={stage}>
      <fieldset disabled={fc.busy || fc.readonly}><div className="form-grid">
        {['commodities', 'accounts'].includes(type) && <><Field label="New code"><input name="code" required/></Field><Field label="Name"><input name="name" required/></Field></>}
        {type === 'commodities' && <><Select label="Kind" name="kind" options={['currency', 'security', 'other'].map(value => ({ value, label: value }))}/><Field label="Decimal scale"><input name="scale" type="number" min="0" max="12" defaultValue="2" required/></Field></>}
        {type === 'accounts' && <><Select label="Account type" name="type" options={['asset', 'liability', 'equity', 'income', 'expense'].map(value => ({ value, label: value }))}/><Field label="Subtype"><input name="subtype"/></Field><Field label="Allowed commodity codes (comma separated)"><input name="allowedCommodityCodes" required defaultValue={codes[0]?.value || ''}/></Field></>}
        {type === 'priceQuotes' && <><Select label="Commodity" name="commodityCode" required options={codes}/><Select label="Quote commodity" name="quoteCommodityCode" required options={codes}/><Field label="Explicit price"><input name="price" inputMode="decimal" required/></Field><Field label="As of"><input name="asOf" type="datetime-local" required/></Field><Field label="Source"><input name="source" defaultValue="manual" required/></Field></>}
        {type === 'drafts' && <><Select label="Saved unposted template" name="draftId" options={drafts.map(item => ({ value: item.id, label: item.description }))}/><Field label="New draft description"><input name="description" required/></Field><Field label="Date"><input name="date" type="date" required defaultValue={localDate()}/></Field></>}
      </div>{type === 'drafts' && !drafts.length && <p>Save a Journal draft first. Batch creation never posts it.</p>}
        <div className="actions"><Button type="submit" disabled={type === 'drafts' && !drafts.length}>Stage new record</Button></div>
      </fieldset>
    </form>
    <Table caption="Staged new records" rows={changes} rowKey="key" columns={[[ 'type', 'Resource' ], ['label', 'New record'], ['actions', 'Actions', item => <Button type="button" danger disabled={fc.busy || fc.readonly} onClick={() => { const next = changes.filter(value => value.key !== item.key); setChanges(next); if (!next.length) fc.clean('atomic-batch'); }}>Remove</Button>]]}/>
    <div className="actions"><Button primary type="button" disabled={fc.busy || fc.readonly || !changes.length} onClick={async () => {
      if (!confirm('Validate and create all staged new records atomically? Existing codes or invalid references reject the entire batch.')) return;
      const body = Object.fromEntries(types.map(({ value }) => [value, changes.filter(item => item.type === value).map(item => item.payload)]));
      if (await fc.ledger('/batch', { method: 'POST', body }, 'Staged records created atomically. No Journal entries were posted.')) { setChanges([]); fc.clean('atomic-batch'); }
    }}>Validate and create batch</Button></div>
  </Panel>;
}
