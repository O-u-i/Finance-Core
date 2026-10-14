import React, { useState } from 'react';
import { Button, Select, Table } from './components.jsx';

const pageSize = 10;
const dateLabel = value => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown date' : new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', day: '2-digit', month: 'short', year: 'numeric' }).format(date);
};
const newestFirst = (left, right) => (right.observedDate || right.month || '').localeCompare(left.observedDate || left.month || '')
  || (Date.parse(right.recordedAt) - Date.parse(left.recordedAt))
  || (right.recordedAt || '').localeCompare(left.recordedAt || '')
  || ((left.id || '') === (right.id || '') ? 0 : (left.id || '') < (right.id || '') ? 1 : -1);

function Pager({ page, pages, onChange }) {
  if (pages <= 1) return null;
  return <div className="snapshot-pager"><Button type="button" disabled={!page} onClick={() => onChange(page - 1)}>Previous</Button><span aria-live="polite">Page {page + 1} of {pages}</span><Button type="button" disabled={page + 1 >= pages} onClick={() => onChange(page + 1)}>Next</Button></div>;
}

function HistoryRows({ records, columns }) {
  const [requestedPage, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(records.length / pageSize)), page = Math.min(requestedPage, pages - 1);
  return <><Table caption="Snapshot history" rows={records.slice(page * pageSize, (page + 1) * pageSize)} rowKey="id" columns={[
    ...columns,
    ['details', 'Details', item => <details className="snapshot-metadata"><summary>Details</summary><dl>
      <dt>Account ID</dt><dd>{item.subjectId || item.accountId}</dd>
      <dt>Recorded timestamp</dt><dd>{item.recordedAt}</dd>
      {item.source && <><dt>Source</dt><dd>{item.source}</dd></>}
      {item.supersedes && <><dt>Corrects</dt><dd>{item.supersedes}</dd></>}
      {item.reason && <><dt>Reason</dt><dd>{item.reason}</dd></>}
      {item.note && <><dt>Note</dt><dd className="note-text">{item.note}</dd></>}
    </dl></details>],
  ]}/><Pager page={page} pages={pages} onChange={setPage}/></>;
}

export default function SnapshotHistory({ records = [], accounts = [], legacy = false, dated = false }) {
  const [filter, setFilter] = useState(''), [requestedPage, setPage] = useState(0);
  const byId = new Map(accounts.map(item => [item.id, item]));
  const names = new Map(accounts.map(item => [item.id, item.name]));
  const superseded = new Set(records.map(item => item.supersedes).filter(Boolean));
  const groups = new Map();
  for (const item of [...records].sort(newestFirst)) {
    if (superseded.has(item.id)) continue;
    const identity = item.subjectId || item.accountId;
    const current = byId.get(identity), latest = groups.get(identity);
    // Legacy clocks can repeat timestamps. Resolve ties against the recorded account,
    // never a random UUID; monthly corrections instead have explicit supersedes IDs.
    if (!latest || (legacy && item.recordedAt === latest.recordedAt && item.recordedAt === current?.updatedAt && item.balance === current?.balance)) {
      groups.set(identity, { ...item, identity });
    }
  }
  const latest = [...groups.values()].sort((a, b) => (names.get(a.identity) || '').localeCompare(names.get(b.identity) || ''));
  const visible = latest.filter(item => !filter || item.identity === filter);
  const history = [...records].filter(item => !filter || (item.subjectId || item.accountId) === filter).sort(newestFirst);
  const pages = Math.max(1, Math.ceil(visible.length / pageSize)), page = Math.min(requestedPage, pages - 1);
  const columns = [
    ['account', 'Account', item => names.get(item.subjectId || item.accountId) || 'Archived / unregistered account'],
    ['amount', 'Balance', item => item.amount ?? item.balance],
    ['currency', 'Currency', item => item.currency || item.commodityCode],
    ['period', dated ? 'Balance date' : legacy ? 'Recorded date' : 'Legacy month (actual date unknown)', item => dated ? item.observedDate : legacy ? dateLabel(item.recordedAt) : item.month],
    ...(!legacy ? [['confirmed', 'Status', item => item.confirmed ? 'Confirmed' : 'Pending']] : []),
  ];
  return <div className="snapshot-list">
    <div className="snapshot-toolbar"><Select label="Account filter" value={filter} onChange={value => { setFilter(value); setPage(0); }} options={[
      { value: '', label: 'All accounts' }, ...latest.map(item => ({ value: item.identity, label: names.get(item.identity) || 'Archived / unregistered account' })),
    ]}/><p>{groups.size} accounts · {records.length} recorded snapshots. Latest record per account shown; {dated ? 'balance dates are actual dates, not month ends.' : legacy ? 'submission dates are not balance dates.' : 'actual balance dates are unknown.'}</p></div>
    <Table caption="Latest balance snapshots" rows={visible.slice(page * pageSize, (page + 1) * pageSize)} rowKey="id" columns={columns}/>
    <Pager page={page} pages={pages} onChange={setPage}/>
    {!!records.length && <details className="snapshot-history"><summary>Snapshot history · {history.length} records</summary><HistoryRows key={filter} records={history} columns={columns}/></details>}
  </div>;
}
