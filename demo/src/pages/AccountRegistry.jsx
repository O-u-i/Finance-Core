import React, { useEffect, useRef, useState } from 'react';
import { id } from '../api.js';
import { selectedMonth } from '../navigation.js';
import { Button, Empty, Field, ListControls, Panel, Select, Table } from '../components.jsx';
import { orderedRecords } from '../records.js';

const types = ['asset', 'liability', 'equity', 'income', 'expense'];
const segments = [{ value: 'investment', label: 'Investment' }, { value: 'living', label: 'Living' }];
const emptyFilters = { query: '', type: '', commodity: '', status: '' };

function AccountForm({ fc, editing, onSaved, segment, setSegment }) {
  const legacy = !!fc.migrationRequired;
  const legacyLiving = legacy && segment === 'living';
  const initial = editing || {};
  const currencies = (fc.data.commodities || []).filter(item => item.kind === 'currency' && item.status === 'active').map(item => ({ value: item.code, label: item.code }));
  return <form className="resource-form" onChangeCapture={event => { if (event.target.name !== 'segment') fc.markDirty(event.currentTarget); }} onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget, values = Object.fromEntries(new FormData(form));
    let path, body;
    if (legacyLiving) {
      path = '/living-accounts';
      body = { id: initial.id || id('living'), name: values.name, commodityCode: values.currency, balance: values.balance, note: values.note, updatedAt: initial.updatedAt || new Date().toISOString() };
    } else {
      const allowed = [...new Set((segment === 'living' ? values.currency : values.commodityCodes).split(',').map(value => value.trim()).filter(Boolean))];
      if (!allowed.length || allowed.some(code => !fc.data.commodities?.some(item => item.code === code && item.status === 'active'))) {
        fc.setNotice({ error: true, text: 'Register and activate every allowed commodity before assigning it.' }); return;
      }
      path = legacy ? '/accounts' : '/financial-accounts';
      body = { id: initial.id || id('account'), code: values.code, name: values.name, type: values.type, subtype: values.subtype, allowedCommodityCodes: allowed, status: initial.status || 'active' };
      if (!legacy) Object.assign(body, { segment, note: values.note, balanceSource: segment === 'living' ? 'monthly_snapshot' : 'ledger', classificationConfirmed: true,
        ownerPartyId: segment === 'living' ? values.ownerPartyId : null,
        ...Object.fromEntries(['startMonth', 'endMonth', 'successorOf', 'legacyLivingId'].map(key => [key, values[key] || null])) });
    }
    if (editing) path += '/' + encodeURIComponent(initial.id);
    const result = await fc.ledger(path, { method: editing ? 'PUT' : 'POST', body }, legacy ? 'Account saved in its original registry. No migration performed.' : 'Unified account saved.');
    if (result) { fc.clean(form); form.reset(); onSaved(); }
  }}><fieldset disabled={fc.busy || fc.readonly}>
    <Select label="Ledger segment" name="segment" value={segment} onChange={setSegment} disabled={legacy && !!editing} options={segments}/>
    <p>{segment === 'living' ? 'Living records balances, not detailed spending transactions.' : 'Investment uses the Journal and double-entry ledger.'}</p>
    <div className="form-grid">
      {!legacyLiving && <Field key="code" label="Account code"><input name="code" defaultValue={initial.code || ''} required/></Field>}
      <Field key="name" label="Account name"><input name="name" defaultValue={initial.name || ''} required/></Field>
      {!legacyLiving && <Field key="type" label="Account type"><select name="type" defaultValue={initial.type || 'asset'}>{(segment === 'living' ? types.slice(0, 2) : types).map(value => <option key={value} value={value}>{value}</option>)}</select></Field>}
      {!legacyLiving && <Field key="subtype" label="Subtype"><input name="subtype" defaultValue={initial.subtype ?? (segment === 'living' ? 'cash' : '')}/></Field>}
      {segment === 'living' ? <Select key="currency" label="Currency" name="currency" defaultValue={initial.commodityCode || initial.allowedCommodityCodes?.[0]} options={currencies}/> : <Field key="commodities" label="Allowed commodity codes (comma separated)"><input name="commodityCodes" defaultValue={initial.allowedCommodityCodes?.join(', ') || currencies[0]?.value || ''} required/></Field>}
      {!legacy && segment === 'living' && <Select label="Beneficiary (register in Ownership first)" name="ownerPartyId" defaultValue={initial.ownerPartyId || ''} options={[{ value: '', label: 'Choose beneficiary' }, ...(fc.data.parties || []).map(item => ({ value: item.id, label: item.name }))]}/>}
      {legacyLiving && <><Field label={editing ? 'Current recorded balance (record changes in Living)' : 'Initial recorded balance'}><input name="balance" inputMode="decimal" defaultValue={initial.balance || '0'} readOnly={!!editing} required/></Field><Field label="Note"><input name="note" defaultValue={initial.note || ''}/></Field></>}
      {!legacy && <Field label="Note"><textarea name="note" rows={2} maxLength={4000} defaultValue={initial.note || ''}/></Field>}
    </div>
    {!legacy && <details className="account-advanced"><summary>Dates, successor & legacy mapping</summary><div className="form-grid">
      {['startMonth', 'endMonth'].map(name => <Field key={name} label={name === 'startMonth' ? 'Start month (optional)' : 'End month (optional)'}><input name={name} type="month" defaultValue={initial[name] || ''}/></Field>)}
      <Field label="Predecessor account ID (optional)"><input name="successorOf" defaultValue={initial.successorOf || ''}/></Field>
      <Field label="Legacy Living ID (optional)"><input name="legacyLivingId" defaultValue={initial.legacyLivingId || ''}/></Field>
    </div></details>}
    <Button primary type="submit">{editing ? 'Save account' : 'Add account'}</Button>
  </fieldset></form>;
}

function EndPurpose({ fc, account, onClose }) {
  const dialog = useRef(null), legacy = !!fc.migrationRequired;
  useEffect(() => { const node = dialog.current; node.showModal(); return () => { if (node.open) node.close(); }; }, []);
  const cancel = () => { if (fc.canLeave()) { fc.discardChanges(); onClose(); } };
  return <dialog ref={dialog} className="account-dialog" aria-label="End account purpose" onCancel={event => { event.preventDefault(); cancel(); }}>
    <h2>End purpose · {account.name}</h2><p>Stop new use without deleting balances or history. {legacy ? 'This legacy ledger account becomes inactive; no historical date is inferred.' : 'The end month is inclusive. Resolve remaining balances or register a dated successor; ending is not a write-off.'}</p>
    <form onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
      event.preventDefault(); const form = event.currentTarget;
      const original = legacy ? fc.data.accounts.find(item => item.id === account.id) : account;
      const body = { ...original, status: 'inactive', ...(!legacy ? { endMonth: new FormData(form).get('endMonth') } : {}) };
      const result = await fc.ledger(`/${legacy ? 'accounts' : 'financial-accounts'}/${encodeURIComponent(account.id)}`, { method: 'PUT', body }, 'Account purpose ended. History retained.');
      if (result) { fc.clean(form); onClose(); }
    }}><fieldset disabled={fc.busy || fc.readonly}>
      {!legacy && <Field label="Final month"><input name="endMonth" type="month" defaultValue={account.endMonth || selectedMonth(fc.route)} required/></Field>}
      <div className="actions"><Button danger type="submit">End purpose</Button><Button type="button" onClick={cancel}>Cancel</Button></div>
    </fieldset></form>
  </dialog>;
}

export default function AccountRegistry({ fc }) {
  const [segment, setSegment] = useState(fc.route.segment || 'investment');
  const [filters, setFilters] = useState(emptyFilters);
  const [sort, setSort] = useState('code'), [descending, setDescending] = useState(false);
  const [editing, setEditing] = useState(null);
  const [ending, setEnding] = useState(null);
  const [formVersion, setFormVersion] = useState(0);
  const legacy = !!fc.migrationRequired;
  const accounts = legacy ? [
    ...(fc.data.accounts || []).map(item => ({ ...item, segment: 'investment', balanceSource: 'ledger' })),
    ...(fc.data.living || []).map(item => ({ ...item, segment: 'living', balanceSource: 'legacy_snapshot', allowedCommodityCodes: [item.commodityCode], legacyLiving: true })),
  ] : fc.data.financialAccounts || [];
  const scopedAccounts = accounts.filter(item => item.segment === segment);
  const query = filters.query.trim().toLowerCase();
  const orderColumns = [['code', 'Code'], ['name', 'Name'], ['type', 'Type'], ['allowedCommodityCodes', 'Commodities'], ['status', 'Status']];
  const visibleAccounts = orderedRecords(scopedAccounts.filter(item =>
    `${item.code || ''} ${item.name}`.toLowerCase().includes(query) &&
    (!filters.type || (item.type || 'recorded_balance') === filters.type) &&
    (!filters.commodity || item.allowedCommodityCodes.includes(filters.commodity)) &&
    (!filters.status || (item.status || 'legacy') === filters.status)), orderColumns, sort, descending);
  const clearFilters = () => { setFilters(emptyFilters); setSort('code'); setDescending(false); };
  const filter = (key, value) => setFilters(current => ({ ...current, [key]: value }));
  const resetForm = (item = null) => { fc.discardChanges(); setEditing(item); if (item) setSegment(item.segment); setFormVersion(value => value + 1); };
  const edit = item => { if (fc.canLeave()) resetForm(item); };
  const remove = item => {
    if (!fc.canLeave() || !confirm(`Delete unused account "${item.name}"? Accounts with history or references must be retained.`)) return;
    const resource = item.legacyLiving ? 'living-accounts' : legacy ? 'accounts' : 'financial-accounts';
    fc.ledger(`/${resource}/${encodeURIComponent(item.id)}${item.legacyLiving ? '?preserveHistory=true' : ''}`, { method: 'DELETE' }, 'Unused account deleted.').then(result => {
      if (result) resetForm();
    });
  };
  return <Panel title={editing ? 'Edit account' : 'Financial accounts'} description="Register Investment and Living accounts here. Segment is independent of accounting type and beneficiary." action={editing && <Button onClick={() => { if (fc.canLeave()) resetForm(); }}>Cancel edit</Button>}>
    <AccountForm key={`${editing?.id || 'new'}/${formVersion}`} fc={fc} editing={editing} segment={segment} setSegment={value => { setSegment(value); clearFilters(); }} onSaved={() => setEditing(null)}/>
    <p>{legacy ? 'Legacy storage is retained. This selector chooses the original ledger or Living registry; full ownership and dated lifecycle require an explicitly migrated or new Schema 3 Vault.' : 'Classification is confirmed when saved. Used accounts lock segment, measurement and ownership; a change requires a dated successor.'}</p>
    <div className="account-filters" role="group" aria-label="Account filters"><div className="form-grid">
      <Field label="Search accounts"><input name="accountSearch" type="search" value={filters.query} placeholder="Code or name" disabled={fc.busy} onChange={event => filter('query', event.target.value)}/></Field>
      <Select label="Account type" name="accountTypeFilter" value={filters.type} disabled={fc.busy} onChange={value => filter('type', value)} options={[{ value: '', label: 'All types' }, ...types.map(value => ({ value, label: value })), ...(legacy ? [{ value: 'recorded_balance', label: 'Recorded balance' }] : [])]}/>
      <Select label="Commodity" name="accountCommodityFilter" value={filters.commodity} disabled={fc.busy} onChange={value => filter('commodity', value)} options={[{ value: '', label: 'All commodities' }, ...(fc.data.commodities || []).map(item => ({ value: item.code, label: item.code }))]}/>
      <Select label="Status" name="accountStatusFilter" value={filters.status} disabled={fc.busy} onChange={value => filter('status', value)} options={[{ value: '', label: 'All statuses' }, { value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }, ...(legacy ? [{ value: 'legacy', label: 'Legacy' }] : [])]}/>
    </div><ListControls label="Account order" columns={orderColumns} sort={sort} setSort={setSort} descending={descending} setDescending={setDescending}/><div className="actions"><p role="status">{visibleAccounts.length} of {scopedAccounts.length} {segment === 'living' ? 'Living' : 'Investment'} accounts</p><Button type="button" disabled={fc.busy} onClick={clearFilters}>Clear filters</Button></div></div>
    {visibleAccounts.length ? <Table controls={false} caption="Financial account registry" rows={visibleAccounts} rowKey="id" columns={[
      ['code', 'Code'], ['name', 'Name'], ['segment', 'Segment'], ['type', 'Type', item => item.type || 'Recorded balance'],
      ['allowedCommodityCodes', 'Commodities', item => item.allowedCommodityCodes.join(', ')], ['status', 'Status', item => item.status || 'Legacy'],
      ['actions', 'Actions', item => <div className="actions">
        <Button disabled={fc.busy || fc.readonly} onClick={() => edit(item)}>Edit</Button>
        {!item.legacyLiving && item.status !== 'inactive' && <Button data-action="end-purpose" disabled={fc.busy || fc.readonly} onClick={() => { if (fc.canLeave()) { resetForm(); setEnding(item); } }}>End purpose</Button>}
        <Button danger disabled={fc.busy || fc.readonly} onClick={() => remove(item)}>Delete unused</Button>
      </div>],
    ]}/> : <Empty>{scopedAccounts.length ? 'No accounts match these filters.' : 'No accounts registered in this segment.'}</Empty>}
    {ending && <EndPurpose fc={fc} account={ending} onClose={() => setEnding(null)}/>}
  </Panel>;
}
