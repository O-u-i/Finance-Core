import React from 'react';
import { Button, Field, Panel, Table } from '../components.jsx';
import SnapshotHistory from '../SnapshotHistory.jsx';
import MonthlyPlans from './MonthlyPlans.jsx';
import { pageTabs } from '../navigation.js';

function Balance({ fc, item }) {
  const [balance, setBalance] = React.useState(item.balance);
  return <form className="balance-form" onSubmit={async (event) => { event.preventDefault(); if (await fc.ledger(`/living-accounts/${encodeURIComponent(item.id)}/record-balance`, { method: 'POST', body: { balance } }, 'Balance and snapshot recorded.')) fc.clean(`balance:${item.id}`); }}><Field label={`New balance for ${item.name}`} inputMode="decimal" disabled={fc.busy || fc.readonly} value={balance} onChange={(e) => { setBalance(e.target.value); fc.markDirty(`balance:${item.id}`); }}/><Button disabled={fc.busy || fc.readonly}>Record</Button></form>;
}
export default function Planning({ fc }) {
  const items = fc.route.view === 'plans' ? [['plans','Cash-flow plans (not actuals)']] : fc.route.view === 'livingreview' ? [['summary','Summary']] : pageTabs(fc.route.view,fc.migrationRequired);
  const tab = items.some(([key]) => key === fc.route.tab) ? fc.route.tab : items[0][0];
  return <>
    {tab === 'accounts' && <Panel title="Living accounts" description="Capture balances explicitly and keep a history of snapshots.">
      <Button onClick={() => fc.navigate('master', 'accounts', 'living')}>Register accounts in Master data</Button>
      <Table rows={fc.data.living} columns={[["name", "Name"], ["balance", "Balance"], ["commodityCode", "Currency"], ["record", "Record balance", item => <Balance key={item.updatedAt} fc={fc} item={item}/>]]}/>
    </Panel>}
    {tab === 'snapshots' && <Panel title="Balance snapshots"><SnapshotHistory records={fc.data.snapshots} accounts={fc.data.living} legacy/></Panel>}
    {tab === 'plans' && <MonthlyPlans fc={fc}/>}
    {tab === 'summary' && <Panel title="Living balance summary" description="Backend calculations retain separate currencies."><p>Legacy balance snapshots and forecasts only. This is not a dated monthly review or an immutable month close.</p><Summary value={fc.data.world}/></Panel>}
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
