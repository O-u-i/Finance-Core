import React, { useState } from 'react';
import { id } from '../api.js';
import { shanghaiDate } from '../navigation.js';
import { Button, Field, Panel, Select, Table } from '../components.jsx';

export default function DebtRepayments({ fc }) {
  const accounts = (fc.data.financialAccounts || []).filter(item => item.type === 'liability');
  const records = fc.data.debtRepayments || [];
  const [accountId, setAccount] = useState(''), [currency, setCurrency] = useState(''), [asOf, setDate] = useState(shanghaiDate());
  const [quote, setQuote] = useState(null), [selected, setSelected] = useState(null), [confirmed, setConfirmed] = useState(false);
  const [payments, setPayments] = useState([{ dueDate: '', amount: '' }]);
  const account = accounts.find(item => item.id === accountId) || accounts[0];
  const currencies = (account?.allowedCommodityCodes || []).filter(code => fc.data.commodities?.some(item => item.code === code && item.kind === 'currency'));
  const code = currencies.includes(currency) ? currency : currencies[0];
  const superseded = new Set(records.filter(item => item.status === 'confirmed').map(item => item.supersedes));
  const current = records.find(item => item.status === 'confirmed' && !superseded.has(item.id) && item.accountId === quote?.accountId && item.currency === quote?.currency);
  const select = item => { if (fc.canLeave()) { fc.discardChanges(); setSelected(item); setConfirmed(false); } };
  return <>
    <Panel title="Debt repayment arrangements" description="Review a recorded liability balance, enter sourced repayment dates and amounts, then explicitly confirm the saved draft. This records timing only: it never pays money or posts a Journal entry. Corrections append a new arrangement and retain earlier confirmations.">
      <p className="form-boundary">Missing historical due dates stay unknown, pending input. Future charges remain unknown; these arrangements cover only the current recorded balance.</p>
      <Table caption="Liability timing coverage" rows={accounts} columns={[
        ['name', 'Liability'], ['segment', 'Segment'], ['allowedCommodityCodes', 'Currencies'],
        ['timing', 'Timing', item => records.some(record => record.accountId === item.id && record.status === 'confirmed' && !superseded.has(record.id)) ? 'Confirmed arrangement exists; recheck balance basis' : 'Unknown — pending input'],
      ]}/>
      <form onChangeCapture={event => { fc.markDirty(event.currentTarget); setQuote(null); }} onSubmit={async event => {
        event.preventDefault(); const form = event.currentTarget;
        const query = new URLSearchParams({ accountId: account.id, currency: code, asOf });
        const result = await fc.run((api, wid) => api.ledger(wid, `/debt-repayment-balance?${query}`), 'Recorded debt balance reviewed.', { write: false, reload: false });
        if (result) { setQuote(result.data); fc.clean(form); }
      }}><fieldset disabled={fc.busy || fc.readonly || !account || !code}><div className="form-grid">
        <Select label="Liability account" value={account?.id || ''} onChange={value => { setAccount(value); setCurrency(''); }} options={accounts.map(item => ({ value: item.id, label: `${item.code} · ${item.name}` }))}/>
        <Select label="Currency" value={code || ''} onChange={setCurrency} options={currencies.map(value => ({ value, label: value }))}/>
        <Field label="Recorded balance as of"><input type="date" required max={shanghaiDate()} value={asOf} onChange={event => setDate(event.target.value)}/></Field>
      </div><Button type="submit">Review balance</Button></fieldset></form>
      {quote && <p role="status">Recorded balance: {quote.known ? `${quote.balance} ${quote.currency}` : 'Unknown — confirm baseline, classification and an actual-date balance first.'} · {quote.asOf}</p>}
      {quote?.known && <form onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
        event.preventDefault(); const form = event.currentTarget, values = Object.fromEntries(new FormData(form));
        const result = await fc.ledger('/debt-repayment-arrangements', { method: 'POST', body: {
          id: id('debt-timing'), accountId: quote.accountId, currency: quote.currency, asOf: quote.asOf,
          balanceRevision: quote.balanceRevision, payments, source: values.source, reason: values.reason,
          ...(current ? { supersedes: current.id } : {}),
        } }, 'Repayment draft saved; it is not confirmed yet.');
        if (result) { fc.clean(form); fc.clean('debt-payments'); setSelected(result.data); setConfirmed(false); }
      }}><fieldset disabled={fc.busy || fc.readonly}>
        {payments.map((payment, index) => <div className="form-grid" key={index}>
          <Field label={`Payment ${index + 1} due date`}><input type="date" required value={payment.dueDate} onChange={event => setPayments(items => items.map((item, at) => at === index ? { ...item, dueDate: event.target.value } : item))}/></Field>
          <Field label={`Payment ${index + 1} amount · ${quote.currency}`}><input required inputMode="decimal" value={payment.amount} onChange={event => setPayments(items => items.map((item, at) => at === index ? { ...item, amount: event.target.value } : item))}/></Field>
          <Button type="button" disabled={payments.length === 1} onClick={() => { setPayments(items => items.filter((_, at) => at !== index)); fc.markDirty('debt-payments'); }}>Remove payment {index + 1}</Button>
        </div>)}
        <Button type="button" disabled={payments.length >= 100} onClick={() => { setPayments(items => [...items, { dueDate: '', amount: '' }]); fc.markDirty('debt-payments'); }}>Add payment</Button>
        <div className="form-grid"><Field label="Agreement / evidence source"><input name="source" required maxLength={500}/></Field><Field label="Review / correction reason"><input name="reason" required maxLength={500}/></Field></div>
        {current && <label><input type="checkbox" required/> Replace the current confirmed arrangement with this new version after confirmation; retain its history.</label>}
        <Button primary type="submit">Save repayment draft</Button>
      </fieldset></form>}
    </Panel>
    <Panel title="Repayment history" description="Confirmed versions cannot be edited or deleted. A changed balance, date or classification invalidates the old evidence basis; review the balance and append a corrected arrangement.">
      <Table caption="Repayment arrangements" rows={records} columns={[
        ['accountId', 'Liability', item => accounts.find(value => value.id === item.accountId)?.name || 'Unknown liability'],
        ['asOf', 'Balance date'], ['balance', 'Recorded balance'], ['currency', 'Currency'], ['status', 'State'], ['supersedes', 'Corrects'],
        ['actions', 'Actions', item => <Button disabled={fc.busy} onClick={() => select(item)}>Review arrangement</Button>],
      ]}/>
      {selected && <div className="opening-line"><h3>Review saved arrangement · {selected.status}</h3>
        <p>{selected.balance} {selected.currency} · balance as of {selected.asOf}</p>
        <Table controls={false} caption="Saved repayment dates" rows={selected.payments} columns={[[ 'dueDate', 'Due date' ], [ 'amount', 'Amount' ]]}/>
        <dl><dt>Evidence source</dt><dd>{selected.source}</dd><dt>Review reason</dt><dd>{selected.reason}</dd></dl>
        {selected.status === 'draft' && <form onSubmit={async event => {
          event.preventDefault();
          const result = await fc.ledger(`/debt-repayment-arrangements/${encodeURIComponent(selected.id)}/confirm`, { method: 'POST', body: {
            expectedRevision: selected.revision, expectedBalanceRevision: selected.balanceRevision, confirmed: true,
          } }, 'Repayment arrangement confirmed. Financial balances and Journal entries are unchanged.');
          if (result) { setSelected(result.data); setConfirmed(false); }
        }}><fieldset disabled={fc.busy || fc.readonly}>
          <label><input type="checkbox" required checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/> I reviewed these exact dates, amounts, evidence and recorded balance. No unknown date has been invented.</label>
          <Button primary type="submit" disabled={!confirmed}>Confirm reviewed arrangement</Button>
        </fieldset></form>}
      </div>}
    </Panel>
  </>;
}
