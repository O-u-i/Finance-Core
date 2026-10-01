import React, { useState } from 'react';
import { id } from '../api.js';
import { Button, Panel, ResourceForm, Table, Tabs } from '../components.jsx';

export const options = (values) => values.map((value) => ({ value, label: value }));
export default function Master({ fc }) {
  const [editing, setEditing] = useState(null);
  const items = [['commodities', 'Commodities'], ['accounts', 'Accounts'], ['prices', 'Prices']];
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
    {tab === 'accounts' && <Panel title={editing ? 'Edit account' : 'Financial accounts'} description="A finance account belongs to this Vault. Allow one or more registered commodity codes, separated by commas, such as CNY, MYR.">
      <ResourceForm key={editing?.id || 'new'} fc={fc} initial={editing ? { ...editing, commodityCodes: editing.allowedCommodityCodes.join(', ') } : { type: 'asset', commodityCodes: commodityOptions[0]?.value || '' }} fields={[
        ['code', 'Account code'], ['name', 'Account name'], ['type', 'Type', 'text', options(['asset', 'liability', 'equity', 'income', 'expense'])], ['subtype', 'Subtype'], ['commodityCodes', 'Allowed commodity codes (comma separated)'],
      ]} submitLabel={editing ? 'Save account' : 'Add account'} onSave={async ({ commodityCodes, ...values }) => {
        const allowed = [...new Set(commodityCodes.split(',').map(code => code.trim()).filter(Boolean))];
        if (!allowed.length || allowed.some(code => !commodityOptions.some(option => option.value === code))) { fc.setNotice({ error: true, text: 'Register and activate each allowed commodity code before assigning it to an account.' }); return false; }
        const result = await fc.ledger(`/accounts${editing ? '/' + encodeURIComponent(editing.id) : ''}`, { method: editing ? 'PUT' : 'POST', body: { ...values, id: editing?.id || id('account'), allowedCommodityCodes: allowed, status: editing?.status || 'active' } }, 'Account saved.');
        if (result) setEditing(null); return result;
      }}/><Table rows={fc.data.accounts} columns={[
        ['code', 'Code'], ['name', 'Name'], ['type', 'Type'], ['subtype', 'Subtype'], ['allowedCommodityCodes', 'Commodities', (item) => item.allowedCommodityCodes.join(', ')], ['status', 'Status'], ['actions', 'Actions', (item) => <div className="actions"><Button disabled={fc.busy || fc.readonly} onClick={() => edit(item)}>Edit</Button><Button disabled={fc.busy || fc.readonly || item.status === 'inactive'} onClick={() => deactivate('accounts', item, 'id')}>Deactivate</Button></div>],
      ]}/>
    </Panel>}
    {tab === 'prices' && <Panel title="Explicit prices" description="Record prices deliberately. Finance Core does not connect to live markets.">
      <ResourceForm fc={fc} initial={{ source: 'manual' }} fields={[
        ['commodityCode', 'Commodity', 'text', commodityOptions], ['quoteCommodityCode', 'Quote commodity', 'text', commodityOptions], ['price', 'Price'], ['asOf', 'As of', 'datetime-local'], ['source', 'Source'],
      ]} submitLabel="Add price" onSave={(values) => fc.ledger('/price-quotes', { method: 'POST', body: { ...values, id: id('quote'), asOf: new Date(values.asOf).toISOString() } }, 'Price recorded.')}/>
      <Table rows={fc.data.quotes} columns={[['commodityCode', 'Commodity'], ['quoteCommodityCode', 'Quote'], ['price', 'Price'], ['asOf', 'Time'], ['source', 'Source'], ['actions', 'Actions', (item) => <Button danger disabled={fc.busy || fc.readonly} onClick={() => { if (confirm('Delete this price quote?')) fc.ledger(`/price-quotes/${encodeURIComponent(item.id)}`, { method: 'DELETE' }, 'Price deleted.'); }}>Delete</Button>]]}/>
    </Panel>}
  </>;
}
