import React from 'react';
import { Button, Empty, ListControls, MonthPicker, Panel, Table } from '../components.jsx';
import { orderedRecords } from '../records.js';
import { selectedRecordedMonth } from '../navigation.js';

export function Reports({ fc }) {
  const tab = { positions: 'holdings', statements: 'statements', cashflow: 'cash-flow', taccounts: 'accounts' }[fc.route.view];
  if (tab === 'holdings') return <Panel title="Securities & positions" className="integration-placeholder"><p>Reserved for future API integration.</p></Panel>;
  return <><div className="report-context"><p>Posted Journal entries → T-accounts · Cash flow → Statements</p><div className="actions"><Button disabled={fc.busy || fc.loading} onClick={() => fc.refresh()}>Refresh reports</Button><Button onClick={() => fc.navigate('journal')}>Open Journal</Button><Button onClick={() => fc.navigate('data', 'backup')}>Export records</Button></div></div>
    {tab === 'statements' && <Panel title="Financial statements" description="Stock includes opening balances. Amounts are grouped by balancing commodity; opening stock is not income or expense."><Table rows={fc.data.statements} columns={[
      ['commodityCode', 'Commodity'], ['assets', 'Assets'], ['liabilities', 'Liabilities'], ['equity', 'Equity'], ['income', 'Income'], ['expenses', 'Expenses'], ['netIncome', 'Net income'],
    ]}/></Panel>}
    {tab === 'cash-flow' && <Panel title="Current-period cash flow" description="Posted cash activity for the selected calendar month. Classified opening balances and their linked reversals are excluded; old unclassified Journal records keep their original meaning.">
      <MonthPicker fc={fc} value={selectedRecordedMonth(fc.route)} label="Activity month"/>
      <Table caption="Period cash activity" rows={fc.data.activityCashFlow?.activity} columns={[[ 'commodityCode','Commodity'],['category','Category'],['amount','Amount']]}/>
      <details className="opening-effects"><summary>Opening stock effects · excluded from period activity</summary><Table caption="Opening cash effects" rows={fc.data.activityCashFlow?.openingEffects} columns={[[ 'commodityCode','Commodity'],['category','Category'],['amount','Stock change']]}/></details>
      <small>{fc.data.activityCashFlow?.calculationVersion} · External completeness unknown.</small>
    </Panel>}
    {tab === 'accounts' && <TAccounts rows={fc.data.tAccounts || []}/>}
  </>;
}

function TAccounts({ rows }) {
  const [sort, setSort] = React.useState('accountCode'), [descending, setDescending] = React.useState(false), [query, setQuery] = React.useState('');
  const columns = [['accountCode', 'Account code'], ['accountName', 'Account name']];
  const groups = new Map();
  for (const row of orderedRecords(rows, columns, sort, descending, query)) {
    if (!groups.has(row.accountId)) groups.set(row.accountId, { ...row, rows: [] });
    groups.get(row.accountId).rows.push(row);
  }
  return <Panel title="T-accounts" description="One account per container. Credit is on the left and Debit on the right; normal balances retain the accounting type's sign convention.">
    <ListControls label="T-accounts" columns={columns} sort={sort} setSort={setSort} descending={descending} setDescending={setDescending} query={query} setQuery={setQuery}/>
    <div className="account-stack">{[...groups.values()].map(account => <section className="t-account-card" key={account.accountId}>
      <h3>{account.accountCode} · {account.accountName}</h3>
      <Table controls={false} caption={`${account.accountCode} balances`} rows={account.rows} columns={[
        ['commodityCode', 'Currency'], ['credit', 'Credit'], ['debit', 'Debit'], ['balance', 'Normal balance'], ['count', 'Posting count'],
      ]}/>
    </section>)}</div>{!groups.size && <Empty>No posted account balances match.</Empty>}
  </Panel>;
}
