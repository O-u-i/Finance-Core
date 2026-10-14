import React from 'react';
import { id, localDate } from '../api.js';
import { Button, Field, Panel, ResourceForm, Table, Tabs, options } from '../components.jsx';
import SnapshotHistory from '../SnapshotHistory.jsx';

function Balance({ fc, item }) {
  const [balance, setBalance] = React.useState(item.balance);
  return <form className="balance-form" onSubmit={async (event) => { event.preventDefault(); if (await fc.ledger(`/living-accounts/${encodeURIComponent(item.id)}/record-balance`, { method: 'POST', body: { balance } }, 'Balance and snapshot recorded.')) fc.clean(`balance:${item.id}`); }}><Field label={`New balance for ${item.name}`} inputMode="decimal" disabled={fc.busy || fc.readonly} value={balance} onChange={(e) => { setBalance(e.target.value); fc.markDirty(`balance:${item.id}`); }}/><Button disabled={fc.busy || fc.readonly}>Record</Button></form>;
}
export default function Planning({ fc }) {
  const items = fc.route.view === 'plans' ? [['plans','Monthly plans (not actuals)']] : [['accounts', 'Living accounts'], ['snapshots', 'Snapshots'], ['plans', 'Monthly plans'], ['summary', 'Summary']];
  const tab = items.some(([key]) => key === fc.route.tab) ? fc.route.tab : items[0][0];
  const commodityOptions = (fc.data.commodities || []).filter((item) => item.kind === 'currency' && item.status === 'active').map((item) => ({ value: item.code, label: item.code }));
  return <><Tabs items={items} value={tab} onChange={(value) => fc.navigate(fc.route.view === 'plans' ? 'plans' : 'planning', value)}/>
    {tab === 'accounts' && <Panel title="Living accounts" description="Capture balances explicitly and keep a history of snapshots.">
      <Button onClick={() => fc.navigate('master', 'accounts', 'living')}>Register accounts in Master data</Button>
      <Table rows={fc.data.living} columns={[["name", "Name"], ["balance", "Balance"], ["commodityCode", "Currency"], ["record", "Record balance", item => <Balance key={item.updatedAt} fc={fc} item={item}/>]]}/>
    </Panel>}
    {tab === 'snapshots' && <Panel title="Balance snapshots"><SnapshotHistory records={fc.data.snapshots} accounts={fc.data.living} legacy/></Panel>}
    {tab === 'plans' && <Panel title="Monthly plans"><ResourceForm fc={fc} initial={{ amount: '0', category: 'other', dayOfMonth: 1, startDate: localDate() }} fields={[
      ['kind', 'Kind', 'text', options(['income', 'expense'])], ['name', 'Name'], ['amount', 'Amount'], ['commodityCode', 'Currency', 'text', commodityOptions], ['category', 'Category'], ['dayOfMonth', 'Day of month', 'number'], ['startDate', 'Start date', 'date'],
      ['note', 'Note', 'textarea'],
    ]} submitLabel="Add plan" onSave={(values) => fc.ledger('/monthly-plans', { method: 'POST', body: { ...values, id: id('plan'), recurringMonthly: true, dayOfMonth: Number(values.dayOfMonth) } }, 'Monthly plan added.')}/>
      <Table rows={fc.data.plans} columns={[['name', 'Name'], ['kind', 'Kind'], ['amount', 'Amount'], ['commodityCode', 'Currency'], ['dayOfMonth', 'Day'], ['note', 'Note', item => item.note ? <details><summary>Note</summary><p className="note-text">{item.note}</p></details> : '—'], ['actions', 'Actions', (item) => <Button danger disabled={fc.busy || fc.readonly} onClick={() => { if (confirm('Delete this monthly plan?')) fc.ledger(`/monthly-plans/${encodeURIComponent(item.id)}`, { method: 'DELETE' }, 'Plan deleted.'); }}>Delete</Button>]]}/>
    </Panel>}
    {tab === 'summary' && <Panel title="Living & plans summary" description="Backend calculations retain separate currencies."><Summary value={fc.data.world}/></Panel>}
  </>;
}
function Summary({ value }) {
  if (!value) return <p>Loading summary…</p>;
  const snapshots = (value.balanceSeries || []).flatMap((series) => series.points.map((point) => ({ ...point, commodityCode: series.commodityCode })));
  return <div className="summary-grid"><div><h3>Summary by currency</h3><Table rows={value.commoditySummaries} columns={[
    ['commodityCode', 'Currency'], ['livingBalance', 'Living balance'], ['investmentMarketValue', 'Investment value'], ['combinedValue', 'Combined value'], ['expectedIncome', 'Planned income'], ['expectedExpense', 'Planned expense'], ['expectedNet', 'Planned net'],
  ]}/></div><div><h3>Recorded balance history</h3><Table rows={snapshots} columns={[
    ['commodityCode', 'Currency'], ['recordedAt', 'Recorded'], ['value', 'Balance'], ['delta', 'Recorded change'],
  ]}/></div></div>;
}
