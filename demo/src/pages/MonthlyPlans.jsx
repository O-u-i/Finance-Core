import React, { useState } from 'react';
import { id, localDate } from '../api.js';
import { selectedRecordedMonth } from '../navigation.js';
import { orderedRecords } from '../records.js';
import { Button, Field, ListControls, MonthPicker, Panel, Select, Table } from '../components.jsx';

function PlanForm({ fc, item, categories, onSaved }) {
  const initial = item || { amount: '', kind: 'income', dayOfMonth: 1, startDate: localDate(), recurringMonthly: true, category: '' };
  const [category, setCategory] = useState(categories.includes(initial.category) ? initial.category : '');
  const [interval, setInterval] = useState(initial.recurringMonthly ? String(initial.repeatEveryMonths || 1) : 'once');
  const currencies = (fc.data.commodities || []).filter(value => value.kind === 'currency' && value.status === 'active');
  return <form className="resource-form monthly-plan-form" onChangeCapture={event => fc.markDirty(event.currentTarget)} onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget, values = Object.fromEntries(new FormData(form));
    const body = { ...values, category: values.category.trim(), id: item?.id || id('plan'), dayOfMonth: Number(values.dayOfMonth || initial.dayOfMonth), recurringMonthly: interval !== 'once', repeatEveryMonths: interval === 'once' ? 1 : Number(interval) };
    if (!body.category) { fc.setNotice({ error: true, text: 'Enter a category name.' }); return; }
    const result = await fc.ledger(`/monthly-plans${item ? '/' + encodeURIComponent(item.id) : ''}`, { method: item ? 'PUT' : 'POST', body }, item ? 'Monthly plan updated.' : 'Monthly plan added.');
    if (result) { fc.clean(form); onSaved(); }
  }}><fieldset disabled={fc.busy || fc.readonly}><div className="form-grid">
    <Field label="Name"><input name="name" required defaultValue={initial.name || ''}/></Field>
    <Select label="Cash flow" name="kind" defaultValue={initial.kind} options={[{ value: 'income', label: 'CF inflow' }, { value: 'expense', label: 'CF outflow' }]}/>
    <Field label="Planned amount"><input name="amount" required inputMode="decimal" defaultValue={initial.amount}/></Field>
    <Select label="Currency" name="commodityCode" defaultValue={initial.commodityCode || currencies[0]?.code} options={currencies.map(value => ({ value: value.code, label: value.code }))}/>
    <Select label="Category" name={category ? 'category' : undefined} value={category} onChange={setCategory} options={[{ value: '', label: 'New category…' }, ...categories.map(value => ({ value, label: value }))]}/>
    {!category && <Field label="New category"><input name="category" required defaultValue={initial.category} placeholder="e.g. Salary or Housing"/></Field>}
    <Select label="Repeat interval" help="One occurrence every 1, 3, 6 or 12 months, anchored to the start month. One time uses only the start date. No actual payment or Journal entry is created." value={interval} onChange={setInterval} options={[{ value:'1',label:'Monthly' },{ value:'3',label:'Quarterly' },{ value:'6',label:'Semi-annual' },{ value:'12',label:'Annual' },{ value:'once',label:'One time' }]}/>
    {interval !== 'once' && <Field label="Due day (1–31)" help="The calendar day of each scheduled month, not a number of occurrences. Days 29–31 use the last valid day in shorter months. The first due date must be on or after the start date."><input name="dayOfMonth" type="number" min="1" max="31" required defaultValue={initial.dayOfMonth}/></Field>}
    <Field label="Start date"><input name="startDate" type="date" required defaultValue={initial.startDate}/></Field>
    <Field label="Note"><textarea name="note" rows={2} maxLength={4000} defaultValue={initial.note || ''}/></Field>
  </div><p className="form-boundary">Forecast only. Plans never record actual cash flows or post Journal entries.</p>
    <div className="actions"><Button type="submit" primary>{item ? 'Save plan' : 'Add plan'}</Button></div>
  </fieldset></form>;
}

function CategoryTotals({ report }) {
  const [query, setQuery] = useState(''), [sort, setSort] = useState('category'), [descending, setDescending] = useState(false);
  const categories = [...new Set((report?.categories || []).map(item => item.category))].map(category => ({ category }));
  return <Panel title="Scheduled category totals" description="Backend-calculated forecasts for the selected month, not income received or spending incurred. Plan-list filters do not change these totals; currencies are never combined.">
    {!report ? <p>Plan totals are not available.</p> : <>
      <Table caption="All scheduled plans by currency" rows={report.currencies} columns={[[ 'currency', 'Currency' ], ['inflow', 'CF inflow'], ['outflow', 'CF outflow'], ['net', 'Planned net'], ['count', 'Occurrences']]}/>
      <ListControls label="Categories" columns={[[ 'category', 'Category' ]]} sort={sort} setSort={setSort} descending={descending} setDescending={setDescending} query={query} setQuery={setQuery}/>
      <div className="account-stack">{orderedRecords(categories, [[ 'category', 'Category' ]], sort, descending, query).map(({ category }) => <section className="t-account-card" key={category}>
        <h3>{category || 'Uncategorized'}</h3><Table controls={false} caption={`${category || 'Uncategorized'} forecast`} rows={report.categories.filter(item => item.category === category)} columns={[[ 'currency', 'Currency' ], ['inflow', 'CF inflow'], ['outflow', 'CF outflow'], ['net', 'Planned net'], ['count', 'Occurrences']]}/>
      </section>)}</div>
    </>}
  </Panel>;
}

export default function MonthlyPlans({ fc }) {
  const plans = fc.data.plans || [], report = fc.data.planReport;
  const categories = [...new Set(plans.map(item => item.category).filter(Boolean))].sort();
  const [editing, setEditing] = useState(null), [version, setVersion] = useState(0), [category, setCategory] = useState(''), [kind, setKind] = useState('');
  const reset = () => { setEditing(null); setVersion(value => value + 1); };
  const rows = plans.filter(item => (!category || item.category === category) && (!kind || item.kind === kind)).map(item => ({ ...item, dueDate: report?.occurrences.find(value => value.planId === item.id)?.dueDate }));
  return <>
    <Panel sectionKey="plan-editor" title={editing ? 'Edit cash-flow plan' : 'Cash-flow plans'} description="Plan expected inflows and outflows on a monthly, quarterly, semi-annual, annual or one-time schedule. A plan is not a transaction." action={editing && <Button type="button" onClick={() => { if (fc.canLeave()) { fc.discardChanges(); reset(); } }}>Cancel edit</Button>}>
      <PlanForm key={`${editing?.id || 'new'}/${version}`} fc={fc} item={editing} categories={categories} onSaved={reset}/>
    </Panel>
    <Panel title="Manage plans"><MonthPicker fc={fc} value={selectedRecordedMonth(fc.route)} label="Forecast month"/>
      <div className="plan-filters"><Select label="Category filter" value={category} onChange={setCategory} options={[{ value: '', label: 'All categories' }, ...categories.map(value => ({ value, label: value }))]}/><Select label="Cash flow filter" value={kind} onChange={setKind} options={[{ value: '', label: 'All flows' }, { value: 'income', label: 'CF inflow' }, { value: 'expense', label: 'CF outflow' }]}/></div>
      <Table caption="Cash-flow plans" rows={rows} rowKey="id" columns={[
        ['name', 'Name'], ['category', 'Category'], ['kind', 'Cash flow', item => item.kind === 'income' ? 'CF inflow' : 'CF outflow'], ['amount', 'Planned amount'], ['commodityCode', 'Currency'],
        ['repeatEveryMonths', 'Repeat interval', item => item.recurringMonthly ? ({1:'Monthly',3:'Quarterly',6:'Semi-annual',12:'Annual'})[item.repeatEveryMonths || 1] : 'One time'],
        ['dayOfMonth', 'Due day', item => item.recurringMonthly ? item.dayOfMonth : 'Start date'], ['startDate', 'Start date'], ['dueDate', 'Scheduled this month', item => item.dueDate || 'Not scheduled'],
        ['note', 'Note', item => item.note ? <details><summary>Note</summary><p className="note-text">{item.note}</p></details> : '—'],
        ['actions', 'Actions', item => <div className="actions"><Button type="button" disabled={fc.busy || fc.readonly} onClick={() => { if (fc.canLeave()) { fc.discardChanges(); setEditing(item); setVersion(value => value + 1); } }}>Edit</Button><Button type="button" danger disabled={fc.busy || fc.readonly} onClick={async () => { if (!fc.canLeave() || !confirm(`Delete plan "${item.name}"? This removes its forecast, not any financial history.`)) return; const result = await fc.ledger(`/monthly-plans/${encodeURIComponent(item.id)}`, { method: 'DELETE' }, 'Plan deleted.'); if (result && editing?.id === item.id) { fc.discardChanges(); reset(); } }}>Delete</Button></div>],
      ]}/>
    </Panel>
    <CategoryTotals report={report}/>
  </>;
}
