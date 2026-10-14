import React, { useState } from 'react';
import { id } from '../api.js';
import { shanghaiDate } from '../navigation.js';
import { Button, Empty, Field, Panel, Select, Table, Tabs } from '../components.jsx';
import { BalanceForm } from './RecordedBalances.jsx';
import SnapshotHistory from '../SnapshotHistory.jsx';

const accountOptions = accounts => accounts.map(item => ({ value: item.id, label: `${item.code} · ${item.name}` }));
const newLine = () => ({ key: id('opening-line'), accountId: '', commodityCode: '', amount: '', unitCost: '', lotId: '', note: '' });

function InvestmentOpening({ fc }) {
  const currencies = (fc.data.commodities || []).filter(item => item.kind === 'currency' && item.status === 'active');
  const accounts = (fc.data.accounts || []).filter(item => item.status === 'active' && ['asset','liability','equity'].includes(item.type));
  const [currency, setCurrency] = useState(currencies[0]?.code || '');
  const [equityId, setEquity] = useState(''), [date, setDate] = useState(shanghaiDate());
  const [source, setSource] = useState(''), [lines, setLines] = useState(() => [newLine()]);
  const [stored, setStored] = useState(null), [validation, setValidation] = useState(null), [confirmed, setConfirmed] = useState(false);
  const [expectedUpdatedAt, setExpectedUpdatedAt] = useState('');
  const equities = accounts.filter(item => item.type === 'equity' && item.allowedCommodityCodes.includes(currency));
  const equity = equities.find(item => item.id === equityId) || equities[0];
  const stock = accounts.filter(item => item.id !== equity?.id && item.allowedCommodityCodes.some(code => code === currency || fc.data.commodities.some(c => c.code === code && c.kind === 'security' && c.status === 'active')));
  const resolveLine = line => {
    const account = stock.find(item => item.id === line.accountId) || stock[0];
    const commodities = fc.data.commodities.filter(item => item.status === 'active' && account?.allowedCommodityCodes.includes(item.code) && (item.code === currency || (item.kind === 'security' && account.type === 'asset')));
    const commodity = commodities.find(item => item.code === line.commodityCode) || commodities[0];
    return { account, commodities, commodity };
  };
  const changed = () => { setStored(null); setValidation(null); setConfirmed(false); };
  const update = (key, values) => setLines(current => current.map(line => line.key === key ? { ...line, ...values } : line));
  const records = fc.data.openingRecords || { drafts: [], entries: [] };
  return <>
    <Panel title="Investment opening balances" description="Establish stock on the actual activation date. The server builds the equity counterpart; this is not current-period income, spending or a capital flow.">
      <form className="resource-form opening-form" onChangeCapture={event => { fc.markDirty(event.currentTarget); changed(); }} onSubmit={async event => {
        event.preventDefault(); const form = event.currentTarget;
        const result = await fc.ledger('/opening-balance-drafts', { method: 'POST', body: {
          id: id('opening'), date, balancingCommodityCode: currency, equityAccountId: equity.id, source,
          balances: lines.map(line => { const { account, commodity } = resolveLine(line); return {
            accountId: account.id, commodityCode: commodity.code, amount: line.amount, note: line.note,
            ...(commodity.kind === 'security' ? { unitCost: line.unitCost, lotId: line.lotId } : {}),
          }; }),
        } }, 'Opening draft saved outside the ledger. Validate and confirm before posting.');
        if (result) { fc.clean(form); fc.clean('opening-lines'); setStored(result.data.draft); setExpectedUpdatedAt(result.data.updatedAt); setValidation(null); setConfirmed(false); }
      }}><fieldset disabled={fc.busy || fc.readonly}>
        <div className="form-grid">
          <Field label="Activation / baseline date"><input name="date" type="date" max={shanghaiDate()} required value={date} onChange={event => setDate(event.target.value)}/></Field>
          <Select label="Opening currency" name="balancingCommodityCode" value={currency} onChange={value => { setCurrency(value); setEquity(''); }} options={currencies.map(item => ({ value: item.code, label: item.code }))}/>
          <Select label="Explicit equity counterpart" name="equityAccountId" value={equity?.id || ''} onChange={setEquity} options={accountOptions(equities)}/>
          <Field label="Opening statement / evidence source"><input name="source" required maxLength={500} value={source} onChange={event => setSource(event.target.value)}/></Field>
        </div>
        {lines.map((line, index) => { const { account, commodity, commodities } = resolveLine(line); return <section className="opening-line" key={line.key}>
          <div className="posting-title"><h3>Stock {index + 1}</h3><Button type="button" disabled={lines.length === 1} onClick={() => { changed(); setLines(current => current.filter(item => item.key !== line.key)); fc.markDirty('opening-lines'); }}>Remove</Button></div>
          <div className="form-grid">
            <Select label="Stock account" name="accountId" value={account?.id || ''} onChange={value => update(line.key, { accountId: value, commodityCode: '', unitCost: '', lotId: '' })} options={accountOptions(stock)}/>
            <Select label="Commodity" name="commodityCode" value={commodity?.code || ''} onChange={value => update(line.key, { commodityCode: value, unitCost: '', lotId: '' })} options={commodities.map(item => ({ value: item.code, label: item.code }))}/>
            <Field label={commodity?.kind === 'security' ? 'Security units' : 'Opening balance (normal sign)'}><input name="amount" inputMode="decimal" required value={line.amount} onChange={event => update(line.key, { amount: event.target.value })}/></Field>
            {commodity?.kind === 'security' && <><Field label={`Book cost per unit · ${currency}`}><input name="unitCost" inputMode="decimal" required value={line.unitCost} onChange={event => update(line.key, { unitCost: event.target.value })}/></Field><Field label="Opening lot ID"><input name="lotId" required value={line.lotId} onChange={event => update(line.key, { lotId: event.target.value })}/></Field></>}
            <Field label="Note"><textarea name="note" rows={2} maxLength={4000} value={line.note} onChange={event => update(line.key, { note: event.target.value })}/></Field>
          </div>
        </section>; })}
        <p>Positive assets are debits; positive liabilities and equity are credits. Use separate drafts per currency. Security cost is not its market price; the opening lot date is the activation date, not an inferred original purchase date.</p>
        <details><summary>Zero balances, existing history & corrections</summary><p>Do not create a Journal entry for zero stock. Zero-cost securities are not supported by the existing lot model. Opening cannot follow earlier facts or overlap an existing baseline. A later-date reversal cannot rewrite an earlier opening: use an actual-date adjustment in Journal. Beneficial ownership and reconciliation remain separate; opening equity does not confirm who owns the pool.</p></details>
        <div className="actions"><Button type="button" onClick={() => { changed(); setLines(current => [...current, newLine()]); fc.markDirty('opening-lines'); }}>Add stock line</Button><Button primary type="submit" disabled={!equity || !stock.length || lines.some(line => !resolveLine(line).commodity)}>Save opening draft</Button></div>
        {(!equity || !stock.length) && <p role="status">Register stock accounts and a matching equity account in Master data first.</p>}
      </fieldset></form>
    </Panel>
    {stored && <Panel className="opening-preview" title="Review opening draft" description={`${stored.date} · ${stored.balancingCommodityCode} · not posted until separately confirmed.`}>
      <Table caption="Opening postings" rows={validation?.preview?.postings || stored.postings} columns={[
        ['accountId','Account', posting => fc.data.accounts.find(item => item.id === posting.accountId)?.name || posting.accountId], ['side','Side'], ['units','Units'], ['commodityCode','Commodity'], ['valuationRate','Cost / rate'], ['memo','Note'],
      ]}/>
      <Button disabled={fc.busy || fc.readonly} onClick={async () => {
        const result = await fc.run((api, wid) => api.ledger(wid, `/journal-entry-drafts/${encodeURIComponent(stored.id)}/validate`, { method: 'POST' }), 'Opening draft checked against current facts.', { write: false, reload: false });
        setValidation(result || null); setConfirmed(false);
      }}>Validate opening draft</Button>
      {validation?.issues?.length > 0 && <ul role="alert">{validation.issues.map((issue, i) => <li key={i}>{issue.code} · {issue.message}</li>)}</ul>}
      {validation?.valid && <p role="status">Balanced preview: debit {validation.preview.debitTotal} · credit {validation.preview.creditTotal}. Posting rechecks this baseline atomically.</p>}
      <form onSubmit={async event => {
        event.preventDefault();
        const result = await fc.ledger(`/opening-balances/${encodeURIComponent(stored.id)}/post`, { method: 'POST', body: { confirmed: true, expectedUpdatedAt } }, 'Opening balances posted; stock and activity remain separate.');
        if (result) { setStored(null); setValidation(null); setConfirmed(false); setLines([newLine()]); }
      }}><fieldset disabled={fc.busy || fc.readonly}><label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/> I reviewed the date, stock, explicit cost and equity counterpart. Posted facts are immutable.</label><Button type="submit" primary disabled={!validation?.valid || !confirmed}>Post opening balances</Button></fieldset></form>
    </Panel>}
    <Panel title="Retained opening history" description="Classified opening drafts, posted stock and linked reversals remain traceable. Earlier ordinary Journal entries are not reclassified automatically.">
      {!!records.drafts.length && <Table caption="Unposted opening drafts" rows={records.drafts.map(item => ({ ...item, id: item.draft.id }))} rowKey="id" columns={[
        ['id','Draft', item => item.draft.id], ['date','Date', item => item.draft.date], ['actions','Actions', item => <Button disabled={fc.busy || fc.readonly} onClick={() => { if (fc.canLeave()) { fc.discardChanges(); setStored(item.draft); setExpectedUpdatedAt(item.updatedAt); setValidation(null); setConfirmed(false); } }}>Review draft</Button>],
      ]}/>}
      {!!records.entries.length && <Table caption="Posted opening history" rows={records.entries} columns={[
        ['date','Effective date'], ['description','Description'], ['source','Source'], ['reversalOf','Reverses', item => item.reversalOf || '—'],
        ['details','Details', item => <details><summary>Postings & notes</summary><Table rows={item.postings} columns={[[ 'accountId','Account'],['side','Side'],['units','Units'],['commodityCode','Commodity'],['memo','Note']]}/></details>],
      ]}/>}
      {!records.drafts.length && !records.entries.length && <Empty>No opening records yet.</Empty>}
    </Panel>
  </>;
}

export default function OpeningBalances({ fc }) {
  const [segment, setSegment] = useState(fc.route.segment || 'investment');
  const accounts = (fc.data.financialAccounts || []).filter(item => item.segment === 'living');
  if (!fc.data.accounts || !fc.data.commodities) return <p role="status">Loading opening records…</p>;
  return <div className="opening-balances"><Tabs items={[[ 'investment','Investment'],['living','Living']]} value={segment} onChange={value => { if (fc.canLeave()) { fc.discardChanges(); setSegment(value); } }}/>
    {segment === 'investment' ? <InvestmentOpening fc={fc}/> : <>
      <Panel title="Living opening balance" description="Record the first observed balance on its actual date. If dated records already exist, this baseline must precede them; later records belong in Accounts & balances. No Journal or period flow is generated.">
        {accounts.length ? <BalanceForm fc={fc} accounts={accounts} opening/> : <Empty>Register a Living account and beneficiary in Master data first.</Empty>}
      </Panel><Panel title="Retained dated balances"><SnapshotHistory dated records={fc.data.balanceRecords || []} accounts={accounts}/></Panel>
    </>}
  </div>;
}
