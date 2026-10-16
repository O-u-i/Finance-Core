import React, { useState } from 'react';
import { id } from '../api.js';
import AccountRegistry from './AccountRegistry.jsx';
import { Button, Panel, ResourceForm, Table, options } from '../components.jsx';
import Arrangements from './Arrangements.jsx';
import OpeningBalances from './OpeningBalances.jsx';
import { masterSections } from '../navigation.js';

export default function Master({ fc }) {
  const [editing, setEditing] = useState(null);
  const [formVersion, setFormVersion] = useState(0);
  const legacy = !!fc.migrationRequired;
  const items = masterSections(legacy);
  const tab = items.some(([key]) => key === fc.route.tab) ? fc.route.tab : 'commodities';
  React.useEffect(() => { setEditing(null); }, [tab]);
  const commodityOptions = (fc.data.commodities || []).filter((item) => item.status === 'active').map((item) => ({ value: item.code, label: `${item.code} · ${item.name}` }));
  const deactivate = item => fc.ledger(`/commodities/${encodeURIComponent(item.code)}`, { method: 'PUT', body: { code: item.code, name: item.name, kind: item.kind, scale: item.scale, status: 'inactive' } }, 'Commodity deactivated; existing references and history are retained.');
  const remove = async item => {
    if (!fc.canLeave() || !confirm(`Delete unused commodity "${item.code}"? Referenced commodities and financial history cannot be deleted.`)) return;
    const result = await fc.ledger(`/commodities/${encodeURIComponent(item.code)}`, { method: 'DELETE' }, 'Unused commodity deleted.');
    if (result) { setEditing(null); setFormVersion(value => value + 1); fc.discardChanges(); }
  };
  const edit = (item) => { if (fc.canLeave()) { setEditing(item); fc.discardChanges(); } };
  return <>
    {tab === 'commodities' && <Panel title={editing ? 'Edit commodity' : 'Commodity registry'} description="Currencies, securities and other units used by this ledger." action={editing && <Button onClick={() => { if (fc.canLeave()) { setEditing(null); fc.discardChanges(); } }}>Cancel edit</Button>}>
      <ResourceForm key={`${editing?.code || 'new'}/${formVersion}`} fc={fc} immutable={editing ? ['code'] : []} initial={editing || { kind: 'currency', scale: 2 }} fields={[
        ['code', 'Code'], ['name', 'Name'], ['kind', 'Kind', 'text', options(['currency', 'security', 'other'])], ['scale', 'Decimal scale', 'number'],
      ]} submitLabel={editing ? 'Save commodity' : 'Add commodity'} onSave={async (values) => {
        const result = await fc.ledger(`/commodities${editing ? '/' + encodeURIComponent(editing.code) : ''}`, { method: editing ? 'PUT' : 'POST', body: { ...values, code: editing?.code || values.code, scale: Number(values.scale), status: editing?.status || 'active' } }, 'Commodity saved.');
        if (result) setEditing(null); return result;
      }}/><p>Delete only unused commodities. Referenced codes can be deactivated; their history remains available.</p><Table caption="Commodity registry" rows={fc.data.commodities} columns={[
        ['code', 'Code'], ['name', 'Name'], ['kind', 'Kind'], ['scale', 'Scale'], ['status', 'Status'], ['inUse', 'Usage', item => item.inUse === true ? 'Referenced' : item.inUse === false ? 'Unused' : 'Unknown'], ['actions', 'Actions', (item) => <div className="actions"><Button disabled={fc.busy || fc.readonly} onClick={() => edit(item)}>Edit</Button><Button disabled={fc.busy || fc.readonly || item.status === 'inactive'} onClick={() => deactivate(item)}>Deactivate</Button><Button danger disabled={fc.busy || fc.readonly || item.inUse !== false} title={item.inUse !== false ? 'References or financial history must be retained.' : 'Delete this unused registry entry.'} onClick={() => remove(item)}>Delete unused</Button></div>],
      ]}/>
    </Panel>}
    {tab === 'accounts' && <AccountRegistry fc={fc}/> }
    {tab === 'ownership' && <Arrangements fc={fc}/>}
    {tab === 'opening' && <OpeningBalances fc={fc}/>}
    {tab === 'prices' && <Panel title="Explicit prices" description="Record prices deliberately. Finance Core does not connect to live markets.">
      <ResourceForm fc={fc} initial={{ source: 'manual' }} fields={[
        ['commodityCode', 'Commodity', 'text', commodityOptions], ['quoteCommodityCode', 'Quote commodity', 'text', commodityOptions], ['price', 'Price'], ['asOf', 'As of', 'datetime-local'], ['source', 'Source'],
      ]} submitLabel="Add price" onSave={(values) => fc.ledger('/price-quotes', { method: 'POST', body: { ...values, id: id('quote'), asOf: new Date(values.asOf).toISOString() } }, 'Price recorded.')}/>
      <Table rows={fc.data.quotes} columns={[['commodityCode', 'Commodity'], ['quoteCommodityCode', 'Quote'], ['price', 'Price'], ['asOf', 'Time'], ['source', 'Source'], ['actions', 'Actions', (item) => <Button danger disabled={fc.busy || fc.readonly} onClick={() => { if (confirm('Delete this price quote?')) fc.ledger(`/price-quotes/${encodeURIComponent(item.id)}`, { method: 'DELETE' }, 'Price deleted.'); }}>Delete</Button>]]}/>
    </Panel>}
  </>;
}
