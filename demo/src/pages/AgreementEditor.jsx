import React, { useState } from 'react';
import { id } from '../api.js';
import { Button, Field, Select } from '../components.jsx';

export default function AgreementEditor({ fc, initial, onSaved }) {
  const [value, setValue] = useState(initial);
  const parties = (fc.data.parties || []).map(item => ({ value: item.id, label: item.name }));
  const accounts = (fc.data.financialAccounts || []).filter(item => item.segment === 'investment' && item.allowedCommodityCodes.includes(value.currency));
  const accountOptions = type => [{ value: '', label: 'Choose an account' }, ...accounts.filter(item => !type || item.type === type).map(item => ({ value: item.id, label: `${item.code} · ${item.name}` }))];
  const update = (key, next) => setValue(current => ({ ...current, [key]: next }));
  const row = (key, index, field, next) => setValue(current => ({ ...current, [key]: current[key].map((item, i) => i === index ? { ...item, [field]: next } : item) }));
  const add = (key, next) => { update(key, [...value[key], next]); fc.markDirty('agreement-rows'); };
  const remove = (key, index) => { update(key, value[key].filter((_, i) => i !== index)); fc.markDirty('agreement-rows'); };
  const partyField = (key, item, index) => <Select label="Beneficiary" value={item.partyId} onChange={next => row(key, index, 'partyId', next)} options={parties}/>;
  const accountField = (key, item, index, field, label, type) => <Select label={label} value={item[field]} onChange={next => row(key, index, field, next)} options={accountOptions(type)}/>;
  return <form className="resource-form agreement-editor" onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget;
    const body = { ...value, toMonth: value.toMonth || null, distributionEquityAccountId: value.distributionEquityAccountId || null,
      interestAgreements: value.interestAgreements.map(item => ({ ...item, toMonth: item.toMonth || null })) };
    const result = await fc.ledger('/investment-arrangements', { method: 'POST', body }, 'Agreement version validated and appended.');
    if (result) { fc.clean(form); fc.clean('agreement-rows'); onSaved(); }
  }}><fieldset disabled={fc.busy || fc.readonly}>
    <h3>Agreement version {value.version}</h3><div className="form-grid">
      <Select label="Agreement currency" value={value.currency} onChange={next => update('currency', next)} options={(fc.data.commodities || []).filter(item => item.kind === 'currency' && item.status === 'active').map(item => ({ value: item.code, label: item.code }))}/>
      <Field label="Effective from"><input type="month" required value={value.fromMonth} onChange={event => update('fromMonth', event.target.value)}/></Field>
      <Field label="Effective until (optional)"><input type="month" value={value.toMonth || ''} onChange={event => update('toMonth', event.target.value)}/></Field>
      <Select label="Distribution equity account (optional)" value={value.distributionEquityAccountId || ''} onChange={next => update('distributionEquityAccountId', next)} options={[{ value: '', label: 'Not mapped' }, ...accountOptions('equity').slice(1)]}/>
    </div>
    <h3>Residual ownership</h3><p>Enter fractions, such as 0.5 for 50%. FC validates that shares sum exactly to 1; the form never adjusts them automatically.</p>
    {value.residualShares.map((item, index) => <section className="builder-row" key={index}><div className="form-grid">
      {partyField('residualShares', item, index)}<Field label="Residual share (0–1)"><input required inputMode="decimal" value={item.share} onChange={event => row('residualShares', index, 'share', event.target.value)}/></Field>
    </div><Button type="button" danger disabled={value.residualShares.length <= 1} onClick={() => remove('residualShares', index)}>Remove beneficiary</Button></section>)}
    <div className="actions"><Button type="button" disabled={!parties.length} onClick={() => add('residualShares', { partyId: parties[0]?.value || '', share: '' })}>Add beneficiary share</Button></div>
    <details className="builder-section" open={value.claims.length > 0}><summary>Beneficiary claims</summary><p>Map each liability account once. Loans, member funding and accrued claims do not change residual ownership.</p>
      {value.claims.map((item, index) => <section className="builder-row" key={index}><div className="form-grid">
        {partyField('claims', item, index)}{accountField('claims', item, index, 'accountId', 'Claim liability account', 'liability')}
        <Select label="Claim kind" value={item.kind} onChange={next => row('claims', index, 'kind', next)} options={['loan', 'member', 'interest', 'distribution', 'external'].map(value => ({ value, label: value }))}/>
      </div><Button type="button" danger onClick={() => remove('claims', index)}>Remove claim mapping</Button></section>)}
      <div className="actions"><Button type="button" disabled={!parties.length} onClick={() => add('claims', { partyId: parties[0]?.value || '', accountId: '', kind: 'loan' })}>Add claim mapping</Button></div>
    </details>
    <details className="builder-section" open={value.interestAgreements.length > 0}><summary>Fixed monthly interest schedules (optional)</summary>
      {value.interestAgreements.map((item, index) => <section className="builder-row" key={item.id}><div className="form-grid">
        {partyField('interestAgreements', item, index)}{accountField('interestAgreements', item, index, 'principalAccountId', 'Principal liability', 'liability')}
        {accountField('interestAgreements', item, index, 'payableAccountId', 'Interest payable', 'liability')}{accountField('interestAgreements', item, index, 'expenseAccountId', 'Interest expense', 'expense')}
        <Field label="Agreed monthly interest"><input required inputMode="decimal" value={item.monthlyAmount} onChange={event => row('interestAgreements', index, 'monthlyAmount', event.target.value)}/></Field>
        <Field label="Interest effective from"><input type="month" required value={item.fromMonth} onChange={event => row('interestAgreements', index, 'fromMonth', event.target.value)}/></Field>
        <Field label="Interest effective until (optional)"><input type="month" value={item.toMonth || ''} onChange={event => row('interestAgreements', index, 'toMonth', event.target.value)}/></Field>
      </div><Button type="button" danger onClick={() => remove('interestAgreements', index)}>Remove interest schedule</Button></section>)}
      <div className="actions"><Button type="button" disabled={!parties.length} onClick={() => add('interestAgreements', { id: id('interest'), partyId: parties[0]?.value || '', principalAccountId: '', payableAccountId: '', expenseAccountId: '', monthlyAmount: '', fromMonth: value.fromMonth, toMonth: null })}>Add fixed interest schedule</Button></div>
    </details>
    <Field label="Agreement / version reason"><textarea required value={value.reason} onChange={event => update('reason', event.target.value)}/></Field>
    <div className="actions"><Button primary type="submit" disabled={!parties.length}>Validate and append agreement</Button></div>
  </fieldset></form>;
}
