import React from 'react';
import { Button, Dialog, Empty, Help, ListControls, MonthPicker, Panel, Status, Table } from '../components.jsx';
import { orderedRecords } from '../records.js';
import { selectedRecordedMonth } from '../navigation.js';

export function Reports({ fc }) {
  const tab = { positions: 'holdings', statements: 'statements', cashflow: 'cash-flow', taccounts: 'accounts' }[fc.route.view];
  if (tab === 'holdings') return <Panel title="Securities & positions" className="integration-placeholder"><p>Reserved for future API integration.</p></Panel>;
  return <><div className="report-actions actions"><Button disabled={fc.busy || fc.loading} onClick={() => fc.refresh()}>Refresh reports</Button><Button onClick={() => fc.navigate('journal')}>Open Journal</Button><Button onClick={() => fc.navigate('data', 'backup')}>Export records</Button></div>
    {tab === 'statements' && <Panel title="Financial statements" description="Stock includes opening balances. Amounts are grouped by balancing commodity; opening stock is not income or expense."><Table rows={fc.data.statements} columns={[
      ['commodityCode', 'Commodity'], ['assets', 'Assets'], ['liabilities', 'Liabilities'], ['equity', 'Equity'], ['income', 'Income'], ['expenses', 'Expenses'], ['netIncome', 'Net income'],
    ]}/></Panel>}
    {tab === 'cash-flow' && <Panel title="Current-period cash flow" description="Posted cash activity for the selected calendar month. Classified opening balances and their linked reversals are excluded; old unclassified Journal records keep their original meaning.">
      <MonthPicker fc={fc} value={selectedRecordedMonth(fc.route)} label="Activity month"/>
      <Table caption="Period cash activity" rows={fc.data.activityCashFlow?.activity} columns={[[ 'commodityCode','Commodity'],['category','Category'],['amount','Amount']]}/>
      <details className="opening-effects"><summary>Opening stock effects · excluded from period activity</summary><Table caption="Opening cash effects" rows={fc.data.activityCashFlow?.openingEffects} columns={[[ 'commodityCode','Commodity'],['category','Category'],['amount','Stock change']]}/></details>
      <small>{fc.data.activityCashFlow?.calculationVersion} · External completeness unknown.</small>
    </Panel>}
    {tab === 'accounts' && <TAccounts fc={fc} rows={fc.data.tAccounts || []}/>}
  </>;
}

export function TAccountDetails({ fc, account, onClose }) {
  const [offset, setOffset] = React.useState(0), [result, setResult] = React.useState(null), [error, setError] = React.useState('');
  React.useEffect(() => {
    const controller = new AbortController();
    setResult(null); setError('');
    fc.client.ledger(fc.workspace.id, `/t-accounts/${encodeURIComponent(account.accountId)}/postings?commodityCode=${encodeURIComponent(account.commodityCode)}&offset=${offset}&limit=50`, { signal: controller.signal })
      .then(payload => { if (!controller.signal.aborted) setResult(payload); })
      .catch(error => { if (!controller.signal.aborted) setError(error.message); });
    return () => controller.abort();
  }, [fc.client, fc.workspace.id, account.accountId, account.commodityCode, offset]);
  return <Dialog title={`${account.accountCode} · ${account.accountName}`} onClose={onClose}>
    <div className="detail-context"><Status>Read only</Status><span>{account.commodityCode}</span><Help label="Posting date">Posting date is the immutable Journal entry date, not the time the entry was submitted.</Help></div>
    {error ? <p className="notice error" role="alert">{error}</p> : result ? <>
      <p className="detail-count">{result.count} postings</p><Table controls={false} caption="Account postings" rowKey="postingId" rows={result.data} columns={[[ 'postingDate', 'Posting date'], ['debit', 'Debit'], ['credit', 'Credit']]}/>
      <div className="snapshot-pager"><Button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</Button><span>Page {Math.floor(offset / 50) + 1}</span><Button disabled={!result.hasMore} onClick={() => setOffset(offset + 50)}>Next</Button></div>
    </> : <p role="status">Loading postings…</p>}
  </Dialog>;
}

function TAccounts({ fc, rows }) {
  const [sort, setSort] = React.useState('accountCode'), [descending, setDescending] = React.useState(false), [query, setQuery] = React.useState('');
  const [selected, setSelected] = React.useState(null);
  React.useEffect(() => { setSelected(null); }, [rows]);
  const columns = [['accountCode', 'Account code'], ['accountName', 'Account name']];
  const visible = orderedRecords(rows, columns, sort, descending, query);
  return <Panel title="Account balances" className="t-accounts-panel" description="Asset and expense balances are Debit minus Credit. Liability, equity and income balances are Credit minus Debit. Currencies remain separate; all amounts are calculated by Finance Core.">
    <ListControls label="T-accounts" columns={columns} sort={sort} setSort={setSort} descending={descending} setDescending={setDescending} query={query} setQuery={setQuery}/>
    <div className="t-account-grid">{visible.map(account => <button className="t-account-card" type="button" key={`${account.accountId}/${account.commodityCode}`} disabled={fc.loading || fc.busy} onClick={() => setSelected(account)} aria-label={`View postings for ${account.accountCode} ${account.accountName}, ${account.commodityCode}`}>
      <span className="t-account-identity"><span>{account.accountCode}</span><strong>{account.accountName}</strong></span><span className="t-account-currency">{account.commodityCode}</span>
      <span className="t-account-dates">{account.firstPostingDate || 'Date unavailable'}{account.lastPostingDate && account.lastPostingDate !== account.firstPostingDate ? ` – ${account.lastPostingDate}` : ''}</span>
      <span className="t-account-sides"><span><span>Debit</span><strong>{account.debit}</strong></span><span><span>Credit</span><strong>{account.credit}</strong></span></span>
      <span className="t-account-balance"><span>Balance</span><strong>{account.balance}</strong><Help label="Posting count">{`${account.count ?? 'Unknown'} postings. Click to open read-only details.`}</Help></span>
    </button>)}</div>{!visible.length && <Empty>No posted account balances match.</Empty>}
    {selected && <TAccountDetails key={`${selected.accountId}/${selected.commodityCode}`} fc={fc} account={selected} onClose={() => setSelected(null)}/>}
  </Panel>;
}
