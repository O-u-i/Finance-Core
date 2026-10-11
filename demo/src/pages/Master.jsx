import React, { useState } from 'react';
import { id } from '../api.js';
import AccountRegistry from './AccountRegistry.jsx';
import { Button, Panel, ResourceForm, Table, Tabs, options } from '../components.jsx';
import Arrangements from './Arrangements.jsx';

export default function Master({ fc }) {
  const [editing, setEditing] = useState(null);
  const legacy = !!fc.migrationRequired;
  const items = [['commodities', 'Commodities'], ['accounts', 'Accounts'], ['prices', 'Prices'], ...(!legacy ? [['ownership','Ownership & agreements']] : [])];
  const tab = items.some(([key]) => key === fc.route.tab) ? fc.route.tab : 'commodities';
  React.useEffect(() => { setEditing(null); }, [tab]);
  const commodityOptions = (fc.data.commodities || []).filter((item) => item.status === 'active').map((item) => ({ value: item.code, label: `${item.code} · ${item.name}` }));
  const deactivate = (resource, item, key) => fc.ledger(`/${resource}/${encodeURIComponent(item[key])}`, { method: 'PUT', body: { ...item, status: 'inactive' } }, 'Record deactivated.');
  const edit = (item) => { if (fc.canLeave()) { setEditing(item); fc.discardChanges(); } };
  return <><Tabs items={items} value={tab} onChange={(value) => fc.navigate('master', value)}/>
    {tab === 'commodities' && <Panel title={editing ? 'Edit commodity' : 'Commodity registry'} description="Currencies, securities and other units used by this ledger." action={editing && <Button onClick={() => { if (fc.canLeave()) { setEditing(null); fc.discardChanges(); } }}>Cancel edit</Button>}>
      <ResourceForm key={editing?.code || 'new'} fc={fc} immutable={editing ? ['code'] : []} initial={editing || { kind: 'currency', scale: 2 }} fields={[
        ['code', 'Code'], ['name', 'Name'], ['kind', 'Kind', 'text', options(['currency', 'security', 'other'])], ['scale', 'Decimal scale', 'number'],
      ]} submitLabel={editing ? 'Save commodity' : 'Add commodity'} onSave={async (values) => {
        const result = await fc.ledger(`/commodities${editing ? '/' + encodeURIComponent(editing.code) : ''}`, { method: editing ? 'PUT' : 'POST', body: { ...values, code: editing?.code || values.code, scale: Number(values.scale), status: editing?.status || 'active' } }, 'Commodity saved.');
        if (result) setEditing(null); return result;
      }}/><Table rows={fc.data.commodities} columns={[
        ['code', 'Code'], ['name', 'Name'], ['kind', 'Kind'], ['scale', 'Scale'], ['status', 'Status'], ['actions', 'Actions', (item) => <div className="actions"><Button disabled={fc.busy || fc.readonly} onClick={() => edit(item)}>Edit</Button><Button disabled={fc.busy || fc.readonly || item.status === 'inactive'} onClick={() => deactivate('commodities', item, 'code')}>Deactivate</Button></div>],
      ]}/>
    </Panel>}
    {tab === 'accounts' && <AccountRegistry fc={fc}/> }
    {tab === 'ownership' && <Arrangements fc={fc}/>}
    {tab === 'prices' && <Panel title="Explicit prices" description="Record prices deliberately. Finance Core does not connect to live markets.">
      <ResourceForm fc={fc} initial={{ source: 'manual' }} fields={[
        ['commodityCode', 'Commodity', 'text', commodityOptions], ['quoteCommodityCode', 'Quote commodity', 'text', commodityOptions], ['price', 'Price'], ['asOf', 'As of', 'datetime-local'], ['source', 'Source'],
      ]} submitLabel="Add price" onSave={(values) => fc.ledger('/price-quotes', { method: 'POST', body: { ...values, id: id('quote'), asOf: new Date(values.asOf).toISOString() } }, 'Price recorded.')}/>
      <Table rows={fc.data.quotes} columns={[['commodityCode', 'Commodity'], ['quoteCommodityCode', 'Quote'], ['price', 'Price'], ['asOf', 'Time'], ['source', 'Source'], ['actions', 'Actions', (item) => <Button danger disabled={fc.busy || fc.readonly} onClick={() => { if (confirm('Delete this price quote?')) fc.ledger(`/price-quotes/${encodeURIComponent(item.id)}`, { method: 'DELETE' }, 'Price deleted.'); }}>Delete</Button>]]}/>
    </Panel>}
  </>;
}
