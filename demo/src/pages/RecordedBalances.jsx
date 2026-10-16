import React, { useState } from 'react';
import { id } from '../api.js';
import { selectedRecordedMonth, shanghaiDate } from '../navigation.js';
import { Button, Dialog, Empty, Field, MonthPicker, Panel, Select, Table } from '../components.jsx';
import SnapshotHistory from '../SnapshotHistory.jsx';
import { PersonalMonthlyReview, PersonalOverview } from './PersonalFinance.jsx';

const codeOrder = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });
const livingAccounts = fc => (fc.data.financialAccounts || []).filter(item => item.segment === 'living').sort((a, b) => codeOrder.compare(a.code, b.code));

export function BalanceForm({ fc, accounts, opening = false }) {
  const [subjectId, setSubject] = useState(accounts[0]?.id || '');
  const [observedDate, setDate] = useState(shanghaiDate());
  const [amount, setAmount] = useState(''), [source, setSource] = useState('');
  const [note, setNote] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const month = observedDate.slice(0, 7);
  const available = accounts.filter(item => (!item.startMonth || month >= item.startMonth) && (!item.endMonth || month <= item.endMonth) && (item.status === 'active' || item.endMonth));
  const account = available.find(item => item.id === subjectId) || available[0];
  return <form className="resource-form recorded-balance-form" onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget;
    const result = await fc.ledger(opening ? '/opening-living-balances' : '/balance-records', { method: 'POST', body: {
      id: id('balance'), subjectId: account.id, observedDate, amount, currency: account.allowedCommodityCodes[0], source, note, confirmed: true,
    } }, 'Balance recorded on its actual date. Earlier records are retained; no Journal entry was created.');
    if (result) { fc.clean(form); setConfirmed(false); setAmount(''); setNote(''); }
  }}><fieldset disabled={fc.busy || fc.readonly}><div className="form-grid">
    <Select name="subjectId" label="Account" value={account?.id || ''} onChange={value => { setSubject(value); setAmount(''); setConfirmed(false); }} options={available.map(item => ({ value: item.id, label: `${item.code} · ${item.name}` }))}/>
    <Field label="Balance date"><input name="observedDate" type="date" required max={shanghaiDate()} value={observedDate} onChange={event => { setDate(event.target.value); setConfirmed(false); }}/></Field>
    <Field label={`Observed balance · ${account?.allowedCommodityCodes[0] || ''}`}><input name="amount" inputMode="decimal" required value={amount} onChange={event => { setAmount(event.target.value); setConfirmed(false); }}/></Field>
    <Field label="Statement / observation source"><input name="source" required maxLength={500} value={source} onChange={event => { setSource(event.target.value); setConfirmed(false); }}/></Field>
    <Field label="Note"><textarea name="note" rows={2} maxLength={4000} value={note} onChange={event => { setNote(event.target.value); setConfirmed(false); }}/></Field>
  </div>{!account && <p role="status">No accounts are available for this balance date. Check the account purpose period in Master data.</p>}<div className="actions"><label className="balance-confirmation"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/> I observed this balance on {observedDate || 'the selected date'}.</label>
    <Button type="submit" primary disabled={!confirmed || !account}>{opening ? 'Record opening balance' : 'Record balance'}</Button>
  </div></fieldset></form>;
}

export function RecordedBalances({ fc }) {
  const accounts = livingAccounts(fc);
  const legacy = (fc.data.observations || []).filter(item => item.kind === 'balance' && !item.observedDate);
  return <>
    <Panel title="Record a balance" description="Use the actual balance date, any day. Multiple records on the same day are retained; no detailed spending transactions are required." action={<Button onClick={() => fc.navigate('master', 'accounts', 'living')}>Manage accounts</Button>}>
      {accounts.length ? <BalanceForm fc={fc} accounts={accounts}/> : <Empty>No Living accounts registered.</Empty>}
    </Panel>
    <Panel title="Latest balances" description="One latest actual-date record per account. This is not a month-end balance sheet; missing values are unknown.">
      <SnapshotHistory dated records={fc.data.balanceRecords || []} accounts={accounts}/>
    </Panel>
    {!!legacy.length && <details className="legacy-reconciliation"><summary>Legacy monthly records · actual dates unknown</summary>
      <Panel title="Retained monthly observations" description="Original monthly records are preserved separately. Submission timestamps do not establish the actual balance dates."><SnapshotHistory records={legacy} accounts={accounts}/></Panel>
    </details>}
  </>;
}

export function RecordedBalanceReadout({ report, parties = [], filterable = false }) {
  const [accountFilter, setAccountFilter] = useState('');
  const [details, setDetails] = useState(null);
  if (!report) return <Empty>Dated balance review is not available.</Empty>;
  const rows = report.accounts.filter(item => !accountFilter || item.accountId === accountFilter);
  return <>
    <p role="status">{report.month} · latest record within this month, not a month-end balance. Missing months remain Unknown; balance change is not income or spending.</p>
    {filterable && <div className="snapshot-toolbar"><Select name="reviewAccountFilter" label="Account filter" value={accountFilter} onChange={setAccountFilter} options={[
      { value: '', label: 'All accounts' }, ...report.accounts.map(item => ({ value: item.accountId, label: `${item.code} · ${item.name}` })),
    ]}/></div>}
    <Table caption="Dated monthly balance review" rows={rows} rowKey="accountId" columns={[
      ['code', 'Account', item => <><strong>{item.code} · {item.name}</strong><small>{item.type} · {parties.find(party => party.id === item.ownerPartyId)?.name || 'Unknown beneficiary'}</small></>, item => `${item.code} ${item.name}`],
      ['currency', 'Currency'], ['observedDate', 'Latest record date', item => item.observedDate || 'Unknown'],
      ['amount', 'Recorded balance', item => item.amount ?? 'Unknown'],
      ['change', 'Balance change only', item => item.change ?? 'Unknown'],
      ['status', 'Status', item => item.status === 'unknown' ? 'Unknown' : item.status === 'pending' ? 'Pending' : 'Confirmed'],
      ['details', 'Details', item => <Button type="button" onClick={() => setDetails(item)}>Details</Button>],
    ]}/>
    {details && <Dialog title={`${details.code} · balance comparison`} onClose={() => setDetails(null)}>
      <dl className="record-details"><dt>Account</dt><dd>{details.name}</dd><dt>Currency</dt><dd>{details.currency}</dd>
        <dt>Latest actual record date</dt><dd>{details.observedDate || 'Unknown'}</dd><dt>Recorded balance</dt><dd>{details.amount ?? 'Unknown'}</dd>
        <dt>Previous record date</dt><dd>{details.previousDate || 'Unknown'}</dd><dt>Previous recorded balance</dt><dd>{details.previousAmount ?? 'Unknown'}</dd>
        <dt>Balance change only</dt><dd>{details.change ?? 'Unknown'}</dd>
      </dl><p>A confirmed balance means the observation was confirmed, not that a monthly close is complete. With no previous record, the change is unknown. A difference is never inferred to be income or spending.</p>
    </Dialog>}
  </>;
}

export function FinanceOverview({ fc }) {
  return <><PersonalOverview fc={fc}/>{!fc.migrationRequired && <Panel className="recorded-review" title="Living · dated balance readout" description="These recorded balances are separate from the formal month-end net-worth calculation above.">
    <RecordedBalanceReadout report={fc.data.recordedReport} parties={fc.data.parties}/>
  </Panel>}</>;
}

export function RecordedLivingReview({ fc }) {
  const month = selectedRecordedMonth(fc.route);
  return <>
    <Panel className="recorded-review" title="Dated monthly balance review" description="Compare two recorded balances and their actual dates. Gaps and pending values are not estimated.">
      <MonthPicker fc={fc} value={month} label="Review month (latest record within month)"/>
      <RecordedBalanceReadout filterable report={fc.data.recordedReport} parties={fc.data.parties}/>
    </Panel>
    <details className="legacy-reconciliation"><summary>Legacy month-end reconciliation & confirmed closes</summary>
      <p>These formal reports retain their original month-end basis. Dated balances above never replace their inputs or confirmed results.</p>
      <PersonalMonthlyReview fc={fc} month={month}/>
    </details>
  </>;
}
